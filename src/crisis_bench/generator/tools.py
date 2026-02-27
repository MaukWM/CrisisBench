"""Tool definitions catalog — static tool metadata for scenario packages.

Defines the tools an agent sees during benchmark execution.  Each tool
maps to a handler in the runner (Epic 3).  Tool definitions are tier-aware:
higher tiers expose more tools.

MCP tool definitions are loaded from a static catalog file captured from
real MCP servers via ``tools/list``.
"""

from __future__ import annotations

import functools
import json
from pathlib import Path

from crisis_bench.models.scenario import NoiseTier, ToolDefinition, ToolParameter

# ---------------------------------------------------------------------------
# Core tools (all tiers, 9 tools)
# ---------------------------------------------------------------------------

_CORE_TOOLS: list[ToolDefinition] = [
    ToolDefinition(
        name="get_contacts",
        description="Retrieve the full contact list with names, relationships, and phone numbers",
        parameters=[],
    ),
    ToolDefinition(
        name="get_conversations",
        description="Retrieve recent message conversation threads",
        parameters=[
            ToolParameter(
                name="count",
                type="integer",
                description="Number of recent conversations to return",
                required=False,
            ),
        ],
    ),
    ToolDefinition(
        name="get_recent_updates",
        description="Retrieve the last N data update payloads from the device",
        parameters=[
            ToolParameter(
                name="count",
                type="integer",
                description="Number of recent updates to return",
                required=True,
            ),
        ],
    ),
    ToolDefinition(
        name="list_memories",
        description="List all stored memory file keys",
        parameters=[],
    ),
    ToolDefinition(
        name="make_call",
        description="Initiate a phone call to the specified number",
        parameters=[
            ToolParameter(
                name="number",
                type="string",
                description="Phone number to call",
                required=True,
            ),
        ],
    ),
    ToolDefinition(
        name="query_device",
        description="Query the current sensor readings from a connected device",
        parameters=[
            ToolParameter(
                name="device_id",
                type="string",
                description="Device identifier to query",
                required=True,
            ),
        ],
    ),
    ToolDefinition(
        name="read_memory",
        description="Read the contents of a stored memory file by key",
        parameters=[
            ToolParameter(
                name="key",
                type="string",
                description="Memory file key to read",
                required=True,
            ),
        ],
    ),
    ToolDefinition(
        name="send_message",
        description="Send a text message to a contact",
        parameters=[
            ToolParameter(
                name="contact_id",
                type="string",
                description="Contact identifier to message",
                required=True,
            ),
            ToolParameter(
                name="text",
                type="string",
                description="Message text to send",
                required=True,
            ),
        ],
    ),
    ToolDefinition(
        name="write_memory",
        description="Write content to a memory file, creating or overwriting by key",
        parameters=[
            ToolParameter(
                name="key",
                type="string",
                description="Memory file key to write",
                required=True,
            ),
            ToolParameter(
                name="content",
                type="string",
                description="Content to store in the memory file",
                required=True,
            ),
        ],
    ),
]

# ---------------------------------------------------------------------------
# Tier-specific tools
# ---------------------------------------------------------------------------

_TIER_TOOLS: dict[str, list[ToolDefinition]] = {
    "T2": [
        ToolDefinition(
            name="get_forecast",
            description="Retrieve the current weather forecast for a location",
            parameters=[
                ToolParameter(
                    name="location",
                    type="string",
                    description="Location name or coordinates for the forecast",
                    required=True,
                ),
            ],
        ),
    ],
    "T3": [
        ToolDefinition(
            name="list_events",
            description="List calendar events for a given date",
            parameters=[
                ToolParameter(
                    name="date",
                    type="string",
                    description="Date in ISO 8601 format (YYYY-MM-DD)",
                    required=True,
                ),
            ],
        ),
    ],
    "T4": [
        ToolDefinition(
            name="get_balance",
            description="Retrieve the current account balance",
            parameters=[
                ToolParameter(
                    name="account",
                    type="string",
                    description="Account identifier",
                    required=True,
                ),
            ],
        ),
        ToolDefinition(
            name="get_transactions",
            description="Retrieve recent account transactions",
            parameters=[
                ToolParameter(
                    name="count",
                    type="integer",
                    description="Number of recent transactions to return",
                    required=True,
                ),
            ],
        ),
    ],
}

# ---------------------------------------------------------------------------
# MCP tool catalog
# ---------------------------------------------------------------------------

_CATALOG_PATH = Path(__file__).parent / "mcp_tool_catalog.json"


@functools.cache
def _load_mcp_tools() -> tuple[ToolDefinition, ...]:
    """Load MCP tool definitions from the static catalog file.

    Cached at module level — the catalog is a static committed file.
    Returns a tuple (hashable) for cache compatibility.
    """
    raw = json.loads(_CATALOG_PATH.read_text())
    tools: list[ToolDefinition] = []
    for entry in raw:
        params = [
            ToolParameter(
                name=p["name"],
                type=p["type"],
                description=p["description"],
                required=p["required"],
            )
            for p in entry["parameters"]
        ]
        tools.append(
            ToolDefinition(
                name=entry["name"],
                description=entry["description"],
                parameters=params,
            )
        )
    return tuple(tools)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def collect_tool_definitions(tier: NoiseTier) -> list[ToolDefinition]:
    """Return a deterministic, sorted list of tool definitions for *tier*.

    - T1: core only (9 tools)
    - T2: core + T2 tools
    - T3: core + T2 + T3 tools + MCP tools
    - T4: core + all tier tools + all MCP tools
    """
    tools = list(_CORE_TOOLS)

    if tier in ("T2", "T3", "T4"):
        tools.extend(_TIER_TOOLS["T2"])
    if tier in ("T3", "T4"):
        tools.extend(_TIER_TOOLS["T3"])
        tools.extend(_load_mcp_tools())
    if tier == "T4":
        tools.extend(_TIER_TOOLS["T4"])

    return sorted(tools, key=lambda t: t.name)
