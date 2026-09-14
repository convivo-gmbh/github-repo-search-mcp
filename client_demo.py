"""
Client demo — proves the MCP server works end-to-end without any IDE.
Uses FastMCP 2.0's in-memory transport: client and server in one process.

Run:  python client_demo.py
"""

import asyncio
import json

from fastmcp import Client

from server import ORG, TOKEN, mcp


def show(title: str, data) -> None:
    print(f"\n{'=' * 60}\n  {title}\n{'=' * 60}")
    print(json.dumps(data, indent=2, ensure_ascii=False, default=str)[:2000])


def plain(result):
    """Extract plain JSON data from a CallToolResult."""
    sc = result.structured_content or {}
    return sc.get("result", sc)


async def main() -> None:
    print(f"Demo against GitHub org: '{ORG}'  (token set: {bool(TOKEN)})")

    async with Client(mcp) as client:
        # 1. What can this server do?
        tools = await client.list_tools()
        show("Available MCP tools", [t.name for t in tools])

        # 2. Browse the org
        repos = plain(await client.call_tool("list_org_repos", {"limit": 10}))
        show(f"Repositories in '{ORG}'", repos)

        # 3. Read a resource (live org context for the LLM)
        stack = await client.read_resource("org://tech-stack")
        show("Resource org://tech-stack", stack[0].text)

        # 4. Code search (requires GITHUB_TOKEN)
        try:
            hits = plain(await client.call_tool(
                "search_code", {"query": "def run", "language": "python", "max_results": 3}
            ))
            show("search_code: 'def run' (python)", hits)
        except Exception as exc:
            show("search_code", f"Skipped: {exc}")

        # 5. Fetch a whole file
        if repos:
            name = repos[0]["name"]
            try:
                file = plain(await client.call_tool(
                    "get_file_content", {"repo": name, "path": "README.md"}
                ))
                file["content"] = file.get("content", "")[:300] + "..."
                show(f"get_file_content: {name}/README.md", file)
            except Exception as exc:
                show("get_file_content", f"Skipped: {exc}")

    print("\nDemo finished.")


if __name__ == "__main__":
    asyncio.run(main())
