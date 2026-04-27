"""Entrypoint: `python -m mcp_server` runs the stdio server."""
from mcp_server.server import build_server


def main() -> None:
    server = build_server()
    server.run()  # FastMCP defaults to stdio.


if __name__ == "__main__":
    main()
