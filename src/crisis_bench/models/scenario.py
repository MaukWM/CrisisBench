"""Scenario package data models — shared contract for generation and execution."""

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

# ---------------------------------------------------------------------------
# Module data models (Task 1)
# ---------------------------------------------------------------------------


class HealthData(BaseModel):
    """Wearable device health/biometric sensor readings."""

    model_config = ConfigDict(frozen=True)

    heart_rate: int = Field(description="Current heart rate in BPM")
    spo2: int = Field(description="Blood oxygen saturation percentage")
    steps: int = Field(description="Step count today")
    skin_temp: float = Field(description="Skin temperature in Celsius")
    ecg_summary: str = Field(description="ECG reading summary text")  # TODO What is this?
    blood_glucose: float = Field(
        description="Blood glucose level mg/dL"
    )  # TODO: Can a non invasive device read this?
    calories_burned: int = Field(description="Calories burned since midnight")
    sleep_stage: str = Field(description="Current or last sleep stage")
    respiratory_rate: int = Field(description="Breaths per minute")
    body_battery: int = Field(
        description="Body battery energy level 0-100"
    )  # TODO: Is this battery information of the device?
    # Can we report other "mundane" device status? Just a few


class LocationData(BaseModel):
    """GPS and spatial positioning data."""

    model_config = ConfigDict(frozen=True)

    lat: float = Field(description="Latitude in decimal degrees")
    lon: float = Field(description="Longitude in decimal degrees")
    altitude: float = Field(description="Altitude in meters")
    speed: float = Field(description="Speed in m/s")
    heading: int = Field(description="Compass heading in degrees 0-360")
    accuracy: float = Field(description="GPS accuracy in meters")
    geofence_status: str = Field(description="Current geofence zone name")
    movement_classification: str = Field(
        description="Movement type: stationary/walking/running/driving"
    )


class WeatherData(BaseModel):
    """Local weather conditions and forecast."""

    model_config = ConfigDict(frozen=True)

    temp: float = Field(description="Temperature in Celsius")
    feels_like: float = Field(description="Feels-like temperature in Celsius")
    humidity: int = Field(description="Relative humidity percentage")
    wind_speed: float = Field(description="Wind speed in mph")
    wind_dir: str = Field(description="Wind direction abbreviation")
    uv_index: int = Field(description="UV index 0-11+")
    aqi: int = Field(description="Air quality index")
    pollen_count: int = Field(
        description="Pollen count level"
    )  # TODO: these need units, I dont know what a number means.
    pressure: float = Field(description="Barometric pressure in inHg")
    dew_point: float = Field(description="Dew point in Fahrenheit")
    cloud_cover: int = Field(description="Cloud cover percentage")


class CalendarEvent(BaseModel):
    """A single calendar event."""

    model_config = ConfigDict(frozen=True)

    title: str = Field(description="Event title")
    time: str = Field(description="Event time as ISO 8601 datetime")
    location: str = Field(description="Event location")
    attendees: list[str] = Field(
        description="List of attendee names"
    )  # TODO: Do we want/need this?


class Reminder(BaseModel):
    """A scheduled reminder."""

    model_config = ConfigDict(frozen=True)

    text: str = Field(description="Reminder text")
    time: str = Field(description="Reminder time as ISO 8601 datetime")


class CalendarData(BaseModel):
    """Calendar events and reminders."""

    model_config = ConfigDict(frozen=True)

    next_3_events: list[CalendarEvent] = Field(description="Next 3 upcoming events")
    reminders: list[Reminder] = Field(description="Active reminders")
    today_summary: str = Field(description="Natural language summary of today's schedule")


class Email(BaseModel):
    """An email header (sender + subject only)."""

    model_config = ConfigDict(frozen=True)

    sender: str = Field(description="Email sender address or name")
    subject: str = Field(description="Email subject line")


class SlackMessage(BaseModel):
    """A Slack message."""

    model_config = ConfigDict(frozen=True)

    channel: str = Field(description="Slack channel name")
    sender: str = Field(description="Message sender username")
    message: str = Field(description="Message text content")


class Sms(BaseModel):
    """An SMS message."""

    model_config = ConfigDict(frozen=True)

    sender: str = Field(description="SMS sender name or number")
    message: str = Field(description="SMS message text")


class SocialNotification(BaseModel):
    """A social media notification."""

    model_config = ConfigDict(frozen=True)

    platform: str = Field(description="Social media platform name")
    notification_text: str = Field(description="Notification content text")


class CommsData(BaseModel):
    """Communications module: emails, messages, calls, social."""

    model_config = ConfigDict(frozen=True)

    unread_emails: list[Email] = Field(description="Unread email headers")
    slack_messages: list[SlackMessage] = Field(description="Recent Slack messages")
    missed_calls: int = Field(description="Number of missed calls")
    voicemail_count: int = Field(description="Number of voicemails")
    sms: list[Sms] = Field(description="Recent SMS messages")
    social_notifications: list[SocialNotification] = Field(
        description="Social media notifications"  # TODO This is the only one im unsure of
    )


class Transaction(BaseModel):
    """A financial transaction."""

    model_config = ConfigDict(frozen=True)

    merchant: str = Field(
        description="Merchant name"
    )  # TODO: Merchant? Not receiver? Might need to be classified as incoming or outgoing as well
    amount: float = Field(description="Transaction amount in USD")


class PendingCharge(BaseModel):
    """A pending financial charge."""

    model_config = ConfigDict(frozen=True)

    merchant: str = Field(description="Merchant name")  # TODO: Merchant?
    amount: float = Field(description="Charge amount in USD")


class StockQuote(BaseModel):
    """A stock price quote."""

    model_config = ConfigDict(frozen=True)

    symbol: str = Field(description="Stock ticker symbol")
    price: float = Field(description="Current price in USD")


class CryptoPrice(BaseModel):
    """A cryptocurrency price."""

    model_config = ConfigDict(frozen=True)

    symbol: str = Field(description="Cryptocurrency symbol")
    price: float = Field(description="Current price in USD")


class FinancialData(BaseModel):
    """Financial module: transactions, balances, markets."""

    model_config = ConfigDict(frozen=True)

    last_3_transactions: list[Transaction] = Field(description="Last 3 transactions")
    account_balance: float = Field(description="Checking account balance in USD")
    pending_charges: list[PendingCharge] = Field(description="Pending charges")
    stock_watchlist: list[StockQuote] = Field(description="Watched stock prices")
    crypto_prices: list[CryptoPrice] = Field(description="Watched crypto prices")
    spending_vs_budget: str = Field(description="Spending vs budget summary text")


# ---------------------------------------------------------------------------
# Core scenario models (Task 2)
# ---------------------------------------------------------------------------

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class PersonProfile(BaseModel):
    """Simulated user's demographic profile."""

    model_config = ConfigDict(frozen=True)

    name: str = Field(description="Full name")
    age: int = Field(description="Age in years")
    birthday: int = 0  # TODO: Let's define a birthday field.
    occupation: str = Field(description="Job title or occupation")
    home_address: str = Field(description="Home street address")
    office_address: str = Field(description="Office street address")


class Contact(BaseModel):
    """A contact in the simulated user's address book."""

    model_config = ConfigDict(frozen=True)

    id: str = Field(description="Unique contact identifier")
    name: str = Field(description="Contact full name")
    relationship: str = Field(description="Relationship to user")
    phone: str = Field(description="Phone number")


class AgentIdentity(BaseModel):
    """The AI assistant's identity."""

    model_config = ConfigDict(frozen=True)
    # TODO: Identity is missing stuff that openclaw has (like personality etc.)
    name: str = Field(description="Agent display name")


class ToolParameter(BaseModel):
    """A single parameter in a tool definition."""

    model_config = ConfigDict(frozen=True)  # TODO: Why is tool param/definition here,
    # don't we get that for free when we define a react agent? ...

    name: str = Field(description="Parameter name")
    type: str = Field(description="Parameter type (string, int, etc.)")
    description: str = Field(description="Parameter description")
    required: bool = Field(description="Whether parameter is required")


class ToolDefinition(BaseModel):
    """A tool available to the agent during execution."""

    model_config = ConfigDict(frozen=True)

    name: str = Field(description="Tool name (flat for core, dotted for MCP)")
    description: str = Field(description="Tool description for the agent")
    parameters: list[ToolParameter] = Field(description="Tool parameters")


class MemoryFile(BaseModel):
    """A pre-seeded memory file."""

    model_config = ConfigDict(frozen=True)

    key: str = Field(description="Memory file key/name")
    content: str = Field(description="Memory file Markdown content")


class HeartbeatPayload(BaseModel):
    """A single heartbeat's data payload with optional module data per tier."""

    model_config = ConfigDict(frozen=True)

    heartbeat_id: int = Field(description="Sequential heartbeat identifier")
    # TODO: If we do heartbeat id, the simulation MUST start with a heartbeat
    #  1 week old. Maybe we can drop this entirely.
    timestamp: str = Field(description="Heartbeat time as ISO 8601 datetime")
    health: HealthData | None = Field(default=None, description="Health sensor data (T1+)")
    # TODO: Does the agent see these descriptions? or not?
    #  Cause T1/2/3/4 is leaking information otherwise.
    location: LocationData | None = Field(default=None, description="Location data (T2+)")
    weather: WeatherData | None = Field(default=None, description="Weather data (T2+)")
    calendar: CalendarData | None = Field(default=None, description="Calendar data (T3+)")
    comms: CommsData | None = Field(default=None, description="Communications data (T3+)")
    financial: FinancialData | None = Field(default=None, description="Financial data (T4)")


class ScenarioManifest(BaseModel):
    """Scenario package manifest with content hash for reproducibility."""

    model_config = ConfigDict(frozen=True)

    content_hash: str = Field(description="SHA-256 hex digest of heartbeats data")
    generator_version: str = Field(description="Generator version that produced this scenario")
    generated_at: str = Field(description="Generation timestamp as ISO 8601 datetime")

    @field_validator("content_hash")
    @classmethod
    def validate_sha256(cls, v: str) -> str:
        """Validate content_hash is a 64-char lowercase hex string."""
        if not _SHA256_RE.match(v):
            msg = "content_hash must be a 64-character lowercase hex SHA-256 digest"
            raise ValueError(msg)
        return v


class ScenarioPackage(BaseModel):
    """Complete scenario package — the published benchmark artifact."""

    model_config = ConfigDict(frozen=True)

    scenario_id: str = Field(description="Unique scenario identifier")
    version: str = Field(description="Scenario format version")
    seed: int = Field(description="Random seed used for generation")
    crisis_type: str = Field(description="Type of crisis simulated")
    noise_tier: Literal["T1", "T2", "T3", "T4"] = Field(
        description="Noise tier controlling module inclusion"
    )
    crisis_heartbeat_id: int = Field(
        description="Heartbeat ID when crisis occurs"
    )  # TODO: Ah this is why we need id!
    person: PersonProfile = Field(description="Simulated user profile")
    contacts: list[Contact] = Field(description="User's contact list")
    agent_identity: AgentIdentity = Field(description="AI assistant identity")
    heartbeats: list[HeartbeatPayload] = Field(description="All heartbeat payloads")
    tool_definitions: list[ToolDefinition] = Field(
        description="Tool definitions for this noise tier"
    )
    memory_files: list[MemoryFile] = Field(description="Pre-seeded memory files")
    manifest: ScenarioManifest = Field(description="Package manifest with content hash")
