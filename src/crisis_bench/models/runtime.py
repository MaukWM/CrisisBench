"""Runtime data models — tool responses, transcripts, and run configuration."""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

# ---------------------------------------------------------------------------
# Tool response models (Task 1)
# ---------------------------------------------------------------------------


class ToolResponse(BaseModel):
    """Base tool response — all tool handlers return a subclass of this."""

    model_config = ConfigDict(frozen=True)

    status: str = Field(description="Response status indicator")


class ErrorResponse(ToolResponse):
    """Error response returned when a tool call fails."""

    message: str = Field(description="Error description message")


class SendMessageResponse(ToolResponse):
    """Response from send_message tool."""

    status: str = Field(default="delivered", description="Delivery status (always 'delivered')")


class MakeCallResponse(ToolResponse):
    """Response from make_call tool."""

    transcript: str | None = Field(default=None, description="Call transcript if connected")


class QueryDeviceResponse(ToolResponse):
    """Response from query_device tool."""

    device_id: str = Field(description="Device identifier queried")
    data: dict[str, Any] = Field(description="Device sensor data payload")


class GetRecentUpdatesResponse(ToolResponse):
    """Response from get_recent_updates tool."""

    heartbeats: list[dict[str, Any]] = Field(description="Recent heartbeat payloads")


class ReadMemoryResponse(ToolResponse):
    """Response from read_memory tool."""

    content: str | None = Field(
        default=None, description="Memory content or null if key not found"
    )


class WriteMemoryResponse(ToolResponse):
    """Response from write_memory tool."""

    status: str = Field(default="written", description="Write status (always 'written')")


class ListMemoriesResponse(ToolResponse):
    """Response from list_memories tool."""

    keys: list[str] = Field(description="Available memory file keys")


class ConversationMessage(BaseModel):
    """A single message within a conversation thread."""

    model_config = ConfigDict(frozen=True)

    sender: str = Field(description="Message sender name")
    text: str = Field(description="Message text content")
    timestamp: str = Field(description="Message time as ISO 8601 datetime")


class Conversation(BaseModel):
    """A conversation thread with a contact."""

    model_config = ConfigDict(frozen=True)

    contact_id: str = Field(description="Contact identifier")
    contact_name: str = Field(description="Contact display name")
    messages: list[ConversationMessage] = Field(description="Messages in this conversation")


class GetContactsResponse(ToolResponse):
    """Response from get_contacts tool."""

    contacts: list[dict[str, Any]] = Field(description="Contact list entries")


class GetConversationsResponse(ToolResponse):
    """Response from get_conversations tool."""

    conversations: list[Conversation] = Field(
        description="Conversation threads with typed sub-models"
    )


class ListEventsResponse(ToolResponse):
    """Response from list_events tool."""

    events: list[dict[str, Any]] = Field(description="Calendar event entries")


class GetForecastResponse(ToolResponse):
    """Response from get_forecast tool."""

    forecast: dict[str, Any] = Field(description="Weather forecast data")


class GetBalanceResponse(ToolResponse):
    """Response from get_balance tool."""

    data: dict[str, Any] = Field(description="Financial balance data")


# ---------------------------------------------------------------------------
# Transcript models (Task 2)
# ---------------------------------------------------------------------------


class ToolCall(BaseModel):
    """A single tool invocation within an agent turn."""

    model_config = ConfigDict(frozen=True)

    tool: str = Field(description="Tool name that was called")
    args: dict[str, Any] = Field(description="Arguments passed to the tool")
    result: dict[str, Any] = Field(description="Serialized tool response")
    routed_to: str = Field(description="Handler that processed the call")


class Turn(BaseModel):
    """A single agent turn containing optional text and tool calls."""

    model_config = ConfigDict(frozen=True)

    agent_text: str | None = Field(default=None, description="Agent reasoning or text output")
    tool_calls: list[ToolCall] = Field(description="Tool calls made during this turn")


class MemoryOp(BaseModel):
    """A memory operation performed during a heartbeat."""

    model_config = ConfigDict(frozen=True)

    op: Literal["read", "write", "list"] = Field(description="Memory operation type")
    key: str | None = Field(default=None, description="Memory key (null for list operations)")
    content: str | None = Field(default=None, description="Content written (null for read/list)")


class UserSimInteraction(BaseModel):
    """An interaction with the user simulator during a heartbeat."""

    model_config = ConfigDict(frozen=True)

    type: Literal["message", "call"] = Field(description="Interaction channel")
    agent_sent: str = Field(description="Text the agent sent")
    user_response: str | None = Field(default=None, description="User simulator reply")


class ContextSent(BaseModel):
    """Token counts for context delivered to the agent."""

    model_config = ConfigDict(frozen=True)

    system_prompt_tokens: int = Field(description="Tokens in the system prompt")
    user_message_tokens: int = Field(description="Tokens in the user message")


class ActionLogEntry(BaseModel):
    """An entry in the rolling action log shown to the agent."""

    model_config = ConfigDict(frozen=True)

    time: str = Field(description="Action time as ISO 8601 datetime")
    action_type: str = Field(description="Category of action taken")
    tool_name: str = Field(description="Tool involved in the action")
    summary: str = Field(description="Brief human-readable summary")


class HeartbeatTranscript(BaseModel):
    """Complete transcript for a single heartbeat execution."""

    model_config = ConfigDict(frozen=True)

    heartbeat_id: int = Field(description="Sequential heartbeat identifier")
    timestamp: str = Field(description="Heartbeat time as ISO 8601 datetime")
    scenario_hash: str = Field(description="SHA-256 hash of the scenario content")
    context_sent: ContextSent = Field(description="Token counts for context delivered")
    turns: list[Turn] = Field(description="Agent turns in this heartbeat")
    memory_ops: list[MemoryOp] = Field(description="Memory operations performed")
    user_sim_interactions: list[UserSimInteraction] = Field(
        description="User simulator interactions"
    )


# ---------------------------------------------------------------------------
# Configuration and full transcript models (Task 3)
# ---------------------------------------------------------------------------


class RunConfig(BaseModel):
    """Run configuration controlling benchmark execution."""

    model_config = ConfigDict(frozen=True)

    agent_model: str = Field(description="Agent LLM model identifier")
    user_sim_model: str = Field(description="User simulator LLM model identifier")
    judge_model: str = Field(description="Judge LLM model identifier")
    model_params: dict[str, Any] = Field(
        default_factory=dict,
        description="Provider-specific model parameters (e.g. temperature, thinking level)",
    )
    max_tool_turns: int = Field(default=10, description="Maximum tool turns per heartbeat")
    max_post_crisis_heartbeats: int = Field(
        default=20, description="Heartbeats to continue after crisis detection"
    )
    action_log_window: int = Field(default=20, description="Rolling action log window size")


class RunTranscript(BaseModel):
    """Complete transcript for a full benchmark run."""

    model_config = ConfigDict(frozen=True)

    scenario_id: str = Field(description="Unique scenario identifier")
    run_id: str = Field(description="Unique run identifier")
    run_config: RunConfig = Field(description="Configuration used for this run")
    heartbeats: list[HeartbeatTranscript] = Field(description="Per-heartbeat transcripts")
