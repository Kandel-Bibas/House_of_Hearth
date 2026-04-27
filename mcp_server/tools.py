"""Tool registration stub.

The real tool implementations land in Task 2. Task 1's build_server() invokes
`register(...)` here as part of its setup, so this module must exist with at
least a no-op `register` callable for the scaffold to import cleanly.
"""
from typing import Any


def register(server: Any, *, session_factory: Any, schema_ok: bool, schema_msg: str) -> None:
    """No-op for Task 1. Task 2 replaces this with real tool registration."""
    return None
