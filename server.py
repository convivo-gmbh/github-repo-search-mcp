"""
GitHub Repo Search MCP
======================
A FastMCP 2.0 server that searches code across your company's GitHub
organization — so any AI assistant can find prior art, snippets and
usages from past projects.

Configuration (environment variables):
    GITHUB_ORG    GitHub organization to search (default: "modelcontextprotocol")
    GITHUB_TOKEN  GitHub Personal Access Token (required for code search)

Run:
    python server.py                  # stdio (for VS Code / Claude Desktop)
    fastmcp run server.py --transport http --port 8000
"""

import base64
import os
from typing import Annotated

import httpx
from dotenv import load_dotenv
from pydantic import Field

from fastmcp import FastMCP

# Load .env from the project directory (works regardless of cwd)
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))

GITHUB_API = "https://api.github.com"

ORG = os.environ.get("GITHUB_ORG") or "modelcontextprotocol"
TOKEN = os.environ.get("GITHUB_TOKEN") or ""

mcp = FastMCP(
    name="GitHub Repo Search",
    instructions=(
        f"Searches code across the '{ORG}' GitHub organization. "
        "Use search_code to find snippets, find_usages to locate symbols, "
        "get_file_content to read whole files, and list_org_repos to browse repos."
    ),
)


def _headers(text_match: bool = False) -> dict:
    headers = {
        "Accept": "application/vnd.github.text-match+json"
        if text_match
        else "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if TOKEN:
        headers["Authorization"] = f"Bearer {TOKEN}"
    return headers


async def _github_get(path: str, params: dict | None = None, text_match: bool = False) -> dict | list:
    async with httpx.AsyncClient(base_url=GITHUB_API, timeout=30) as client:
        resp = await client.get(path, params=params, headers=_headers(text_match))
        if resp.status_code == 401:
            raise ValueError(
                "GitHub authentication failed. Set a valid GITHUB_TOKEN "
                "environment variable (code search requires authentication)."
            )
        if resp.status_code == 403:
            raise ValueError(
                "GitHub rate limit exceeded or access forbidden. "
                "Set GITHUB_TOKEN or wait a moment."
            )
        resp.raise_for_status()
        return resp.json()


# --------------------------------------------------------------------------
# Tools
# --------------------------------------------------------------------------

@mcp.tool
async def search_code(
    query: Annotated[str, Field(description="Code or text to search for, e.g. 'JwtDecoder' or 'keycloak sso'")],
    language: Annotated[str | None, Field(description="Filter by language, e.g. 'java', 'python', 'typescript'")] = None,
    repo: Annotated[str | None, Field(description="Limit to one repo (name only, without org prefix)")] = None,
    max_results: Annotated[int, Field(ge=1, le=30, description="Maximum results to return")] = 10,
) -> list[dict]:
    """Search for code snippets across the whole GitHub organization.

    Returns matching files with repo, path, URL and the matched text fragments.
    """
    q = f"{query} org:{ORG}"
    if language:
        q += f" language:{language}"
    if repo:
        q = f"{query} repo:{ORG}/{repo}" + (f" language:{language}" if language else "")

    data = await _github_get(
        "/search/code",
        params={"q": q, "per_page": max_results},
        text_match=True,
    )
    results = []
    for item in data.get("items", []):
        results.append(
            {
                "repo": item["repository"]["full_name"],
                "path": item["path"],
                "url": item["html_url"],
                "snippets": [m.get("fragment", "") for m in item.get("text_matches", [])],
            }
        )
    return results or [{"info": f"No matches for '{query}' in org '{ORG}'."}]


@mcp.tool
async def find_usages(
    symbol: Annotated[str, Field(description="Function, class or constant name, e.g. 'validateToken'")],
    language: Annotated[str | None, Field(description="Optional language filter")] = None,
) -> list[dict]:
    """Find where a symbol (function/class/constant) is used across all org repos."""
    return await search_code(query=f'"{symbol}"', language=language, max_results=20)


@mcp.tool
async def get_file_content(
    repo: Annotated[str, Field(description="Repository name (without org prefix)")],
    path: Annotated[str, Field(description="File path within the repo, e.g. 'src/main/App.java'")],
    ref: Annotated[str | None, Field(description="Branch, tag or commit SHA (default: default branch)")] = None,
) -> dict:
    """Fetch the full content of a file from a repository in the organization."""
    params = {"ref": ref} if ref else None
    data = await _github_get(f"/repos/{ORG}/{repo}/contents/{path}", params=params)
    if isinstance(data, list):
        return {"directory": path, "entries": [e["name"] for e in data]}
    content = base64.b64decode(data.get("content", "")).decode("utf-8", errors="replace")
    return {"repo": f"{ORG}/{repo}", "path": path, "url": data["html_url"], "content": content}


@mcp.tool
async def list_org_repos(
    language: Annotated[str | None, Field(description="Filter repos by primary language")] = None,
    limit: Annotated[int, Field(ge=1, le=100)] = 30,
) -> list[dict]:
    """List repositories in the organization with language, description and last update."""
    data = await _github_get(
        f"/orgs/{ORG}/repos",
        params={"per_page": limit, "sort": "updated"},
    )
    repos = [
        {
            "name": r["name"],
            "description": r.get("description"),
            "language": r.get("language"),
            "updated": r.get("updated_at"),
            "url": r["html_url"],
        }
        for r in data
    ]
    if language:
        repos = [r for r in repos if (r["language"] or "").lower() == language.lower()]
    return repos


@mcp.tool
async def search_commits(
    query: Annotated[str, Field(description="Search term in commit messages, e.g. 'fix memory leak'")],
    repo: Annotated[str | None, Field(description="Limit to one repo (name only)")] = None,
    max_results: Annotated[int, Field(ge=1, le=20)] = 10,
) -> list[dict]:
    """Search commit messages across the organization — find who solved a problem before."""
    q = f"{query} {'repo:' + ORG + '/' + repo if repo else 'org:' + ORG}"
    data = await _github_get("/search/commits", params={"q": q, "per_page": max_results})
    return [
        {
            "repo": item["repository"]["full_name"],
            "message": item["commit"]["message"].split("\n")[0],
            "author": item["commit"]["author"]["name"],
            "date": item["commit"]["author"]["date"],
            "url": item["html_url"],
        }
        for item in data.get("items", [])
    ] or [{"info": f"No commits matching '{query}'."}]


# --------------------------------------------------------------------------
# Resources — live context the LLM can read
# --------------------------------------------------------------------------

@mcp.resource("org://repos")
async def org_repo_catalog() -> str:
    """Catalog of all repositories in the organization."""
    repos = await list_org_repos.fn(limit=100)
    lines = [f"# Repositories in '{ORG}'\n"]
    for r in repos:
        lines.append(f"- **{r['name']}** ({r['language'] or 'n/a'}): {r['description'] or 'no description'}")
    return "\n".join(lines)


@mcp.resource("org://tech-stack")
async def org_tech_stack() -> str:
    """Overview of programming languages used across the organization."""
    repos = await list_org_repos.fn(limit=100)
    counts: dict[str, int] = {}
    for r in repos:
        lang = r["language"] or "Other"
        counts[lang] = counts.get(lang, 0) + 1
    lines = [f"# Tech stack of '{ORG}'\n"]
    for lang, n in sorted(counts.items(), key=lambda kv: -kv[1]):
        lines.append(f"- {lang}: {n} repo(s)")
    return "\n".join(lines)


# --------------------------------------------------------------------------
# Prompts — reusable templates
# --------------------------------------------------------------------------

@mcp.prompt
def find_prior_art(topic: str) -> str:
    """Ask whether the company has solved a problem before."""
    return (
        f"Search our GitHub organization for prior implementations of: {topic}.\n"
        "Use search_code and search_commits. Summarize which repos contain "
        "relevant code, show the best snippet, and name who worked on it."
    )


@mcp.prompt
def explain_snippet(repo: str, path: str) -> str:
    """Fetch a file and explain what it does."""
    return (
        f"Fetch the file '{path}' from repo '{repo}' using get_file_content, "
        "then explain what it does, its key design decisions, and any risks."
    )


if __name__ == "__main__":
    mcp.run()  # stdio transport by default
