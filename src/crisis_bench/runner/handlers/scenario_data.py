"""ScenarioDataHandler — serves scenario data in response to agent tool calls."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import structlog

from crisis_bench.models.runtime import (
    ErrorResponse,
    GetBalanceResponse,
    GetContactsResponse,
    GetConversationsResponse,
    GetForecastResponse,
    GetRecentUpdatesResponse,
    GetTransactionsResponse,
    ListEventsResponse,
    QueryWearableResponse,
    ToolResponse,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from crisis_bench.models.scenario import HeartbeatPayload, ScenarioPackage


class ScenarioDataHandler:
    """Handles tool calls that query scenario data (wearable, calendar, etc.)."""

    def __init__(self, scenario: ScenarioPackage) -> None:
        self.scenario = scenario
        self._current_heartbeat: HeartbeatPayload | None = None
        self._heartbeat_index: int = 0
        self._tool_map: dict[str, Callable[..., ToolResponse]] = {
            "query_wearable": self._handle_query_wearable,
            "get_recent_updates": self._handle_get_recent_updates,
            "get_contacts": self._handle_get_contacts,
            "get_conversations": self._handle_get_conversations,
            "list_events": self._handle_list_events,
            "get_forecast": self._handle_get_forecast,
            "get_balance": self._handle_get_balance,
            "get_transactions": self._handle_get_transactions,
        }
        self.log = structlog.get_logger().bind(handler="ScenarioDataHandler")

    def set_current_heartbeat(self, heartbeat: HeartbeatPayload, index: int) -> None:
        """Update the current heartbeat context. Called by orchestrator before routing."""
        self._current_heartbeat = heartbeat
        self._heartbeat_index = index

    def can_handle(self, tool_name: str) -> bool:
        return tool_name in self._tool_map

    async def handle(self, tool_name: str, args: dict[str, Any]) -> ToolResponse:
        handler_fn = self._tool_map[tool_name]
        self.log.debug("handling_tool", tool_name=tool_name)
        return handler_fn(args)

    def _handle_query_wearable(self, args: dict[str, Any]) -> QueryWearableResponse:
        assert self._current_heartbeat is not None
        wearable = self._current_heartbeat.wearable
        data = wearable.model_dump() if wearable else {}
        return QueryWearableResponse(status="ok", data=data)

    def _handle_get_recent_updates(self, args: dict[str, Any]) -> GetRecentUpdatesResponse:
        count = args["count"]
        recent = self.scenario.heartbeats[: self._heartbeat_index + 1][-count:]
        return GetRecentUpdatesResponse(status="ok", heartbeats=[hb.model_dump() for hb in recent])

    def _handle_get_contacts(self, args: dict[str, Any]) -> GetContactsResponse:
        return GetContactsResponse(
            status="ok",
            contacts=[c.model_dump() for c in self.scenario.contacts],
        )

    def _handle_get_conversations(self, args: dict[str, Any]) -> GetConversationsResponse:
        return GetConversationsResponse(status="ok", conversations=[])

    def _handle_list_events(self, args: dict[str, Any]) -> ListEventsResponse:
        assert self._current_heartbeat is not None
        calendar = self._current_heartbeat.calendar
        if calendar is None:
            return ListEventsResponse(status="ok", events=[])
        return ListEventsResponse(
            status="ok",
            events=[e.model_dump() for e in calendar.next_3_events],
        )

    def _handle_get_forecast(self, args: dict[str, Any]) -> GetForecastResponse:
        assert self._current_heartbeat is not None
        weather = self._current_heartbeat.weather
        if weather is None:
            return GetForecastResponse(status="ok", forecast={})
        return GetForecastResponse(status="ok", forecast=weather.model_dump())

    def _handle_get_balance(self, args: dict[str, Any]) -> GetBalanceResponse:
        assert self._current_heartbeat is not None
        financial = self._current_heartbeat.financial
        if financial is None:
            return GetBalanceResponse(status="ok", data={})
        return GetBalanceResponse(
            status="ok",
            data={
                "account_balance": financial.account_balance,
                "pending_charges": [pc.model_dump() for pc in financial.pending_charges],
            },
        )

    def _handle_get_transactions(
        self, args: dict[str, Any]
    ) -> GetTransactionsResponse | ErrorResponse:
        assert self._current_heartbeat is not None
        financial = self._current_heartbeat.financial
        count = args["count"]
        if financial is None:
            return ErrorResponse(
                status="error",
                message="Financial data not available at this tier",
            )
        return GetTransactionsResponse(
            status="ok",
            transactions=[t.model_dump() for t in financial.last_3_transactions[:count]],
        )
