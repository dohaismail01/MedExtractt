"""FastAPI-side MCP client for icd10_mcp (Plan §9.5).

Spawns the standalone server over stdio, discovers its tools, and routes one
`icd10_lookup_code` call per diagnosis. The `icd10_codes` map is assembled in
code from the tool results — never from model prose — so a code from memory
cannot reach the response.

Exposes synchronous wrappers (the endpoints are sync) that drive the async MCP
session via asyncio.run. If the server can't start, callers degrade gracefully.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from typing import Optional

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from . import config

# Force the child process to emit UTF-8 on stdout. Without this, Python on
# Windows encodes piped stdout as cp1252, and the MCP client's strict UTF-8
# reader chokes on the first non-ASCII byte (e.g. an em-dash in a code name).
_CHILD_ENV = {**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"}

_SERVER_PARAMS = StdioServerParameters(
    command=sys.executable,
    args=["-m", "mcp_servers.icd10_mcp.server"],
    cwd=str(config.PROJECT_ROOT),
    env=_CHILD_ENV,
)


def _result_to_dict(result) -> dict:
    """Extract the tool's dict payload from a CallToolResult."""
    structured = getattr(result, "structuredContent", None)
    if isinstance(structured, dict):
        # FastMCP wraps a dict return under a "result" key when structured.
        return structured.get("result", structured)
    for block in getattr(result, "content", []) or []:
        text = getattr(block, "text", None)
        if text:
            try:
                return json.loads(text)
            except (json.JSONDecodeError, TypeError):
                continue
    return {}


async def _lookup_all(diagnoses: list[str]) -> dict[str, Optional[dict]]:
    out: dict[str, Optional[dict]] = {}
    async with stdio_client(_SERVER_PARAMS) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            await session.list_tools()  # discovery (Plan §9.5 step 1)
            for dx in diagnoses:
                res = await session.call_tool("icd10_lookup_code", {"diagnosis": dx})
                payload = _result_to_dict(res)
                out[dx] = payload if payload.get("code") else None
    return out


_SPAWN_TIMEOUT_S = 20.0


def code_diagnoses_mcp(diagnoses: list[str]) -> dict[str, Optional[dict]]:
    """Sync wrapper: {diagnosis: {code, name, ...} | None}. {} if none given.

    A broken/absent server surfaces as an exception (timeout) rather than a
    hang, so the caller can fall back to function calling.
    """
    if not diagnoses:
        return {}

    async def _runner():
        return await asyncio.wait_for(
            _lookup_all(diagnoses), timeout=_SPAWN_TIMEOUT_S + 8 * len(diagnoses)
        )

    return asyncio.run(_runner())


async def _ping() -> bool:
    async with stdio_client(_SERVER_PARAMS) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            return len(tools.tools) > 0


def mcp_reachable() -> bool:
    """Whether the icd10_mcp server starts and lists tools, for /health."""
    try:
        return asyncio.run(asyncio.wait_for(_ping(), timeout=_SPAWN_TIMEOUT_S))
    except Exception:  # noqa: BLE001 - health check reports any failure
        return False
