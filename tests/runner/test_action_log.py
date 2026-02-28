"""Tests for ActionLog, _classify_action, and _summarize_tool_call."""

from __future__ import annotations

from crisis_bench.runner.orchestrator import ActionLog, _classify_action, _summarize_tool_call


class TestActionLog:
    """AC #3, #4: ActionLog rolling window behavior."""

    def test_empty_action_log(self) -> None:
        action_log = ActionLog(window_size=20)
        window, total = action_log.get_window()
        assert window == []
        assert total == 0

    def test_record_and_retrieve(self) -> None:
        action_log = ActionLog(window_size=20)
        action_log.record("2027-06-15T10:00:00Z", "query", "query_wearable", "Checked wearable")
        action_log.record("2027-06-15T10:00:00Z", "query", "get_contacts", "Retrieved contacts")
        action_log.record("2027-06-15T10:00:00Z", "memory", "read_memory", "Read memory 'notes'")
        window, total = action_log.get_window()
        assert total == 3
        assert len(window) == 3
        assert window[0].tool_name == "query_wearable"
        assert window[2].tool_name == "read_memory"

    def test_window_size_limits_entries(self) -> None:
        action_log = ActionLog(window_size=20)
        for i in range(25):
            action_log.record(
                f"2027-06-15T10:{i:02d}:00Z",
                "query",
                "query_wearable",
                f"Action {i}",
            )
        window, total = action_log.get_window()
        assert total == 25
        assert len(window) == 20
        # Window should be the last 20 entries (5..24)
        assert window[0].summary == "Action 5"
        assert window[-1].summary == "Action 24"

    def test_window_size_larger_than_entries(self) -> None:
        action_log = ActionLog(window_size=20)
        for i in range(5):
            action_log.record(
                f"2027-06-15T10:{i:02d}:00Z",
                "query",
                "query_wearable",
                f"Action {i}",
            )
        window, total = action_log.get_window()
        assert total == 5
        assert len(window) == 5


class TestClassifyAction:
    """AC #4: Tool call classification."""

    def test_query_tools(self) -> None:
        for tool in [
            "query_wearable",
            "get_recent_updates",
            "get_contacts",
            "get_conversations",
            "list_events",
            "get_forecast",
            "get_balance",
            "get_transactions",
        ]:
            assert _classify_action(tool) == "query"

    def test_memory_tools(self) -> None:
        for tool in ["read_memory", "write_memory", "list_memories"]:
            assert _classify_action(tool) == "memory"

    def test_communication_tools(self) -> None:
        for tool in ["send_message", "make_call"]:
            assert _classify_action(tool) == "communication"

    def test_unknown_tool_fallback(self) -> None:
        assert _classify_action("some_unknown_tool") == "tool_call"


class TestSummarizeToolCall:
    """AC #4: Human-readable tool call summaries."""

    def test_static_summaries(self) -> None:
        assert _summarize_tool_call("query_wearable", {}) == "Checked wearable sensor data"
        assert _summarize_tool_call("get_contacts", {}) == "Retrieved contacts list"
        assert _summarize_tool_call("get_conversations", {}) == "Retrieved conversations"
        assert _summarize_tool_call("list_events", {}) == "Listed calendar events"
        assert _summarize_tool_call("get_forecast", {}) == "Checked weather forecast"
        assert _summarize_tool_call("get_balance", {}) == "Checked account balance"
        assert _summarize_tool_call("list_memories", {}) == "Listed memory files"

    def test_parameterized_summaries(self) -> None:
        result = _summarize_tool_call("get_recent_updates", {"count": 5})
        assert result == "Retrieved 5 recent updates"
        result = _summarize_tool_call("get_transactions", {"count": 3})
        assert result == "Retrieved 3 recent transactions"
        assert _summarize_tool_call("read_memory", {"key": "notes"}) == "Read memory 'notes'"
        assert _summarize_tool_call("write_memory", {"key": "todo"}) == "Updated memory 'todo'"
        assert _summarize_tool_call("send_message", {"contact_id": "c1"}) == "Sent message to c1"
        assert _summarize_tool_call("make_call", {"number": "+1-555-0001"}) == "Called +1-555-0001"

    def test_missing_args_fallback(self) -> None:
        assert _summarize_tool_call("get_recent_updates", {}) == "Retrieved ? recent updates"
        assert _summarize_tool_call("read_memory", {}) == "Read memory '?'"
        assert _summarize_tool_call("send_message", {}) == "Sent message to ?"

    def test_unknown_tool_fallback(self) -> None:
        assert _summarize_tool_call("some_custom_tool", {}) == "Called some_custom_tool"
