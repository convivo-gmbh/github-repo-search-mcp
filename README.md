# GitHub Repo Search MCP

FastMCP 2.0 server that searches code across your GitHub organization,
so AI assistants (Copilot, Claude) can find prior art from past projects.

## Quick start

```bash
python3 -m venv .venv && .venv/bin/pip install "fastmcp>=2,<3" python-dotenv
# put GITHUB_ORG and GITHUB_TOKEN into .env (see .env.example)

.venv/bin/python client_demo.py     # end-to-end demo, no IDE needed
.venv/bin/python server.py          # run as stdio MCP server
```

## IDE integration

Copy `mcp.json` to `.vscode/mcp.json` (or merge into Claude Desktop's
config), set your org and PAT, then chat:
> "Have we ever implemented a svg utility? Show me examples from our repos."

## Files

- `server.py` — the MCP server (tools, resources, prompts)
- `client_demo.py` — scripted demo using FastMCP's in-memory client
- `mcp.json` — VS Code configuration template
- `.env.example` — environment variable template

Notes: GitHub code/commit search requires authentication; `list_org_repos`
works unauthenticated for public orgs. Without `GITHUB_ORG` set, it demos
against the public `modelcontextprotocol` org.
