"""Tests for PromptBuilder."""

from __future__ import annotations

from crisis_bench.models.runtime import ActionLogEntry
from crisis_bench.models.scenario import (
    HeartbeatPayload,
    LocationData,
    ScenarioPackage,
    WearableData,
)
from crisis_bench.prompt import PromptBuilder, format_module_data


class TestSystemPrompt:
    """AC #1, #6: System prompt assembly and content."""

    def test_system_prompt_contains_all_sections(
        self,
        small_scenario_package: ScenarioPackage,
    ) -> None:
        builder = PromptBuilder(small_scenario_package)
        prompt = builder.system_prompt
        # All 6 section markers present.
        assert "# Who You Are" in prompt  # SOUL
        assert "# Your Identity" in prompt  # IDENTITY
        assert "# About" in prompt  # USER
        assert "# Memory" in prompt  # MEMORY_PROTOCOL
        assert "# How Updates Work" in prompt  # HEARTBEAT_BEHAVIOR
        assert "# Guidelines" in prompt  # SAFETY

    def test_system_prompt_no_emergency_framing(
        self,
        small_scenario_package: ScenarioPackage,
    ) -> None:
        builder = PromptBuilder(small_scenario_package)
        prompt = builder.system_prompt.lower()
        banned = [
            "emergency",
            "crisis",
            "health alert",
            "medical",
            "safety alert",
            "911",
            "urgent care",
        ]
        for word in banned:
            assert word not in prompt, f"System prompt contains banned word: {word!r}"

    def test_system_prompt_agent_identity(
        self,
        small_scenario_package: ScenarioPackage,
    ) -> None:
        builder = PromptBuilder(small_scenario_package)
        prompt = builder.system_prompt
        assert small_scenario_package.agent_identity.name in prompt
        assert small_scenario_package.agent_identity.personality in prompt

    def test_system_prompt_user_profile(
        self,
        small_scenario_package: ScenarioPackage,
    ) -> None:
        builder = PromptBuilder(small_scenario_package)
        prompt = builder.system_prompt
        person = small_scenario_package.person
        assert person.name in prompt
        assert person.birthday in prompt
        assert person.occupation in prompt
        assert person.home_address in prompt
        assert person.office_address in prompt

    def test_system_prompt_no_contacts(
        self,
        small_scenario_package: ScenarioPackage,
    ) -> None:
        builder = PromptBuilder(small_scenario_package)
        prompt = builder.system_prompt
        for contact in small_scenario_package.contacts:
            assert contact.name not in prompt
            assert contact.phone not in prompt


class TestUserMessage:
    """AC #2: User message building."""

    def test_user_message_contains_heartbeat_data(
        self,
        small_scenario_package: ScenarioPackage,
    ) -> None:
        hb = HeartbeatPayload(
            heartbeat_id=5,
            timestamp="2027-06-15T10:25:00Z",
            wearable=WearableData(
                heart_rate=72,
                spo2=98,
                steps=3400,
                skin_temp=36.5,
                ecg_summary="normal sinus rhythm",
                blood_glucose=95.2,
                calories_burned=450,
                sleep_stage="awake",
                respiratory_rate=16,
                body_battery=65,
            ),
            location=LocationData(
                lat=40.7849,
                lon=-73.9785,
                altitude=30.0,
                speed=0.0,
                heading=180,
                accuracy=5.0,
                movement_classification="stationary",
            ),
        )
        builder = PromptBuilder(small_scenario_package)
        msg = builder.build_user_message(
            heartbeat=hb,
            action_log_entries=[],
            total_action_count=0,
            pending_responses=[],
        )
        assert "5" in msg  # heartbeat_id
        assert "2027-06-15T10:25:00Z" in msg  # timestamp

    def test_user_message_empty_action_log(
        self,
        small_scenario_package: ScenarioPackage,
    ) -> None:
        hb = HeartbeatPayload(heartbeat_id=0, timestamp="2027-06-15T10:00:00Z")
        builder = PromptBuilder(small_scenario_package)
        msg = builder.build_user_message(
            heartbeat=hb,
            action_log_entries=[],
            total_action_count=0,
            pending_responses=[],
        )
        assert "No actions yet today." in msg

    def test_user_message_with_action_log(
        self,
        small_scenario_package: ScenarioPackage,
    ) -> None:
        hb = HeartbeatPayload(heartbeat_id=1, timestamp="2027-06-15T10:05:00Z")
        entries = [
            ActionLogEntry(
                time="10:00",
                action_type="read",
                tool_name="read_memory",
                summary="Read user_profile memory",
            ),
        ]
        builder = PromptBuilder(small_scenario_package)
        msg = builder.build_user_message(
            heartbeat=hb,
            action_log_entries=entries,
            total_action_count=1,
            pending_responses=[],
        )
        assert "Read user_profile memory" in msg

    def test_user_message_skips_none_modules(
        self,
        small_scenario_package: ScenarioPackage,
    ) -> None:
        hb = HeartbeatPayload(
            heartbeat_id=0,
            timestamp="2027-06-15T10:00:00Z",
            wearable=WearableData(
                heart_rate=72,
                spo2=98,
                steps=0,
                skin_temp=36.5,
                ecg_summary="normal sinus rhythm",
                blood_glucose=92.0,
                calories_burned=0,
                sleep_stage="awake",
                respiratory_rate=16,
                body_battery=90,
            ),
        )
        builder = PromptBuilder(small_scenario_package)
        msg = builder.build_user_message(
            heartbeat=hb,
            action_log_entries=[],
            total_action_count=0,
            pending_responses=[],
        )
        assert '"wearable"' in msg
        assert '"weather"' not in msg
        assert '"calendar"' not in msg
        assert '"comms"' not in msg
        assert '"financial"' not in msg


class TestFormatModuleData:
    """Test format_module_data helper."""

    def test_format_module_data_raw_json(self) -> None:
        hb = HeartbeatPayload(
            heartbeat_id=3,
            timestamp="2027-06-15T10:15:00Z",
            wearable=WearableData(
                heart_rate=68,
                spo2=97,
                steps=1200,
                skin_temp=36.4,
                ecg_summary="normal sinus rhythm",
                blood_glucose=94.5,
                calories_burned=200,
                sleep_stage="awake",
                respiratory_rate=15,
                body_battery=78,
            ),
        )
        import json

        result = format_module_data(hb)
        parsed = json.loads(result)
        # heartbeat_id and timestamp excluded
        assert "heartbeat_id" not in parsed
        assert "timestamp" not in parsed
        # None modules excluded
        assert "location" not in parsed
        assert "weather" not in parsed
        # wearable key present (not "health")
        assert "wearable" in parsed
        assert parsed["wearable"]["heart_rate"] == 68
