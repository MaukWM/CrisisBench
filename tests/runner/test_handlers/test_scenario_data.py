"""Tests for ScenarioDataHandler."""

from __future__ import annotations

import asyncio
import hashlib
import json

import pytest

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
)
from crisis_bench.models.scenario import (
    AgentIdentity,
    CalendarData,
    CalendarEvent,
    Contact,
    FinancialData,
    HeartbeatPayload,
    MemoryFile,
    PendingCharge,
    PersonProfile,
    Reminder,
    ScenarioManifest,
    ScenarioPackage,
    StockQuote,
    ToolDefinition,
    Transaction,
    WearableData,
    WeatherData,
)
from crisis_bench.runner.handlers.scenario_data import ScenarioDataHandler


def _run(coro):
    return asyncio.run(coro)


def _make_wearable() -> WearableData:
    return WearableData(
        heart_rate=72,
        spo2=98,
        steps=5000,
        skin_temp=36.5,
        ecg_summary="Normal sinus rhythm",
        blood_glucose=95.0,
        calories_burned=320,
        sleep_stage="awake",
        respiratory_rate=16,
        body_battery=65,
    )


def _make_weather() -> WeatherData:
    return WeatherData(
        temp=22.0,
        feels_like=21.0,
        humidity=55,
        wind_speed=8.0,
        wind_dir="NW",
        uv_index=5,
        aqi=42,
        pollen_level="Medium",
        pressure=30.1,
        dew_point=12.0,
        cloud_cover=40,
    )


def _make_calendar() -> CalendarData:
    return CalendarData(
        next_3_events=[
            CalendarEvent(
                title="Team Standup",
                time="2027-06-15T10:30:00Z",
                location="Room 201",
                attendees=["Alice", "Bob"],
            ),
        ],
        reminders=[Reminder(text="Pick up groceries", time="2027-06-15T17:00:00Z")],
        today_summary="One meeting today: Team Standup at 10:30.",
    )


def _make_financial() -> FinancialData:
    return FinancialData(
        last_3_transactions=[
            Transaction(counterparty="Coffee Shop", amount=4.50, category="outgoing"),
            Transaction(counterparty="Paycheck", amount=3000.00, category="incoming"),
            Transaction(counterparty="Gas Station", amount=45.00, category="outgoing"),
        ],
        account_balance=2950.50,
        pending_charges=[PendingCharge(merchant="Amazon", amount=29.99)],
        stock_watchlist=[StockQuote(symbol="AAPL", price=185.50)],
        crypto_prices=[],
        spending_vs_budget="72% of monthly budget used",
    )


def _make_scenario_with_modules() -> ScenarioPackage:
    """Create a scenario with heartbeats that include module data."""
    heartbeats = [
        HeartbeatPayload(
            heartbeat_id=0,
            timestamp="2027-06-15T10:00:00Z",
            wearable=_make_wearable(),
        ),
        HeartbeatPayload(
            heartbeat_id=1,
            timestamp="2027-06-15T10:01:00Z",
            wearable=_make_wearable(),
            weather=_make_weather(),
        ),
        HeartbeatPayload(
            heartbeat_id=2,
            timestamp="2027-06-15T10:02:00Z",
            wearable=_make_wearable(),
            weather=_make_weather(),
            calendar=_make_calendar(),
        ),
        HeartbeatPayload(
            heartbeat_id=3,
            timestamp="2027-06-15T10:03:00Z",
            wearable=_make_wearable(),
            weather=_make_weather(),
            calendar=_make_calendar(),
            financial=_make_financial(),
        ),
        HeartbeatPayload(
            heartbeat_id=4,
            timestamp="2027-06-15T10:04:00Z",
        ),
    ]
    heartbeats_json = json.dumps([hb.model_dump() for hb in heartbeats], sort_keys=True)
    content_hash = hashlib.sha256(heartbeats_json.encode()).hexdigest()

    return ScenarioPackage(
        scenario_id="test_modules_T4_s1",
        version="1.0.0",
        seed=1,
        crisis_type="test",
        noise_tier="T4",
        crisis_heartbeat_id=3,
        person=PersonProfile(
            name="Test User",
            birthday="January 1, 2000",
            occupation="Tester",
            home_address="123 Test St",
            office_address="456 Work Ave",
        ),
        contacts=[
            Contact(id="c1", name="Alice", relationship="colleague", phone="+1-555-0001"),
            Contact(id="c2", name="Bob", relationship="friend", phone="+1-555-0002"),
        ],
        agent_identity=AgentIdentity(name="TestBot", personality="Helpful"),
        heartbeats=heartbeats,
        tool_definitions=[
            ToolDefinition(name="query_wearable", description="test", parameters=[]),
        ],
        memory_files=[
            MemoryFile(key="test_memory", content="# Test memory"),
        ],
        persona="You are a test persona.",
        manifest=ScenarioManifest(
            content_hash=content_hash,
            generator_version="0.1.0",
            generated_at="2027-06-15T10:00:00Z",
        ),
    )


@pytest.fixture()
def scenario_with_modules() -> ScenarioPackage:
    return _make_scenario_with_modules()


@pytest.fixture()
def handler(scenario_with_modules: ScenarioPackage) -> ScenarioDataHandler:
    return ScenarioDataHandler(scenario_with_modules)


class TestScenarioDataHandlerCanHandle:
    def test_can_handle_known_tools(self, handler: ScenarioDataHandler) -> None:
        """All 8 scenario data tools are recognized."""
        expected_tools = [
            "query_wearable",
            "get_recent_updates",
            "get_contacts",
            "get_conversations",
            "list_events",
            "get_forecast",
            "get_balance",
            "get_transactions",
        ]
        for tool_name in expected_tools:
            assert handler.can_handle(tool_name), f"Expected can_handle({tool_name!r}) to be True"

    def test_can_handle_unknown_tool(self, handler: ScenarioDataHandler) -> None:
        assert not handler.can_handle("unknown_tool")


class TestScenarioDataHandlerTools:
    def test_query_wearable_returns_sensor_data(self, handler: ScenarioDataHandler) -> None:
        """query_wearable returns wearable sensor fields only."""
        handler.set_current_heartbeat(handler.scenario.heartbeats[0], 0)
        response = _run(handler.handle("query_wearable", {}))
        assert isinstance(response, QueryWearableResponse)
        assert response.status == "ok"
        assert response.data["heart_rate"] == 72
        assert response.data["spo2"] == 98
        # Must NOT contain weather/calendar/financial data
        assert "temp" not in response.data
        assert "next_3_events" not in response.data
        assert "account_balance" not in response.data

    def test_query_wearable_no_wearable(self, handler: ScenarioDataHandler) -> None:
        """query_wearable returns empty data dict when wearable is None."""
        handler.set_current_heartbeat(handler.scenario.heartbeats[4], 4)
        response = _run(handler.handle("query_wearable", {}))
        assert isinstance(response, QueryWearableResponse)
        assert response.data == {}

    def test_get_contacts_returns_scenario_contacts(self, handler: ScenarioDataHandler) -> None:
        handler.set_current_heartbeat(handler.scenario.heartbeats[0], 0)
        response = _run(handler.handle("get_contacts", {}))
        assert isinstance(response, GetContactsResponse)
        assert len(response.contacts) == 2
        assert response.contacts[0]["name"] == "Alice"
        assert response.contacts[1]["name"] == "Bob"

    def test_get_recent_updates_count(self, handler: ScenarioDataHandler) -> None:
        """Returns only the requested number of heartbeats up to current index."""
        handler.set_current_heartbeat(handler.scenario.heartbeats[3], 3)
        response = _run(handler.handle("get_recent_updates", {"count": 2}))
        assert isinstance(response, GetRecentUpdatesResponse)
        assert len(response.heartbeats) == 2
        # Should be heartbeats 2 and 3 (last 2 of indices 0,1,2,3)
        assert response.heartbeats[0]["heartbeat_id"] == 2
        assert response.heartbeats[1]["heartbeat_id"] == 3

    def test_get_forecast_with_weather(self, handler: ScenarioDataHandler) -> None:
        handler.set_current_heartbeat(handler.scenario.heartbeats[1], 1)
        response = _run(handler.handle("get_forecast", {}))
        assert isinstance(response, GetForecastResponse)
        assert response.forecast["temp"] == 22.0
        assert response.forecast["humidity"] == 55

    def test_get_forecast_without_weather(self, handler: ScenarioDataHandler) -> None:
        """No weather module returns empty forecast dict."""
        handler.set_current_heartbeat(handler.scenario.heartbeats[0], 0)
        response = _run(handler.handle("get_forecast", {}))
        assert isinstance(response, GetForecastResponse)
        assert response.forecast == {}

    def test_list_events_with_calendar(self, handler: ScenarioDataHandler) -> None:
        handler.set_current_heartbeat(handler.scenario.heartbeats[2], 2)
        response = _run(handler.handle("list_events", {}))
        assert isinstance(response, ListEventsResponse)
        assert len(response.events) == 1
        assert response.events[0]["title"] == "Team Standup"

    def test_list_events_without_calendar(self, handler: ScenarioDataHandler) -> None:
        handler.set_current_heartbeat(handler.scenario.heartbeats[0], 0)
        response = _run(handler.handle("list_events", {}))
        assert isinstance(response, ListEventsResponse)
        assert response.events == []

    def test_get_balance_with_financial(self, handler: ScenarioDataHandler) -> None:
        handler.set_current_heartbeat(handler.scenario.heartbeats[3], 3)
        response = _run(handler.handle("get_balance", {}))
        assert isinstance(response, GetBalanceResponse)
        assert response.data["account_balance"] == 2950.50
        assert len(response.data["pending_charges"]) == 1

    def test_get_balance_without_financial(self, handler: ScenarioDataHandler) -> None:
        handler.set_current_heartbeat(handler.scenario.heartbeats[0], 0)
        response = _run(handler.handle("get_balance", {}))
        assert isinstance(response, GetBalanceResponse)
        assert response.data == {}

    def test_get_transactions_with_financial(self, handler: ScenarioDataHandler) -> None:
        handler.set_current_heartbeat(handler.scenario.heartbeats[3], 3)
        response = _run(handler.handle("get_transactions", {"count": 2}))
        assert isinstance(response, GetTransactionsResponse)
        assert len(response.transactions) == 2

    def test_get_transactions_without_financial(self, handler: ScenarioDataHandler) -> None:
        handler.set_current_heartbeat(handler.scenario.heartbeats[0], 0)
        response = _run(handler.handle("get_transactions", {"count": 2}))
        assert isinstance(response, ErrorResponse)
        assert response.message == "Financial data not available at this tier"

    def test_get_conversations_empty(self, handler: ScenarioDataHandler) -> None:
        """Placeholder: returns empty conversations list."""
        handler.set_current_heartbeat(handler.scenario.heartbeats[0], 0)
        response = _run(handler.handle("get_conversations", {}))
        assert isinstance(response, GetConversationsResponse)
        assert response.conversations == []
