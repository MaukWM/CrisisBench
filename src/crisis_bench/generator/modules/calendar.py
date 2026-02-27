"""CalendarGenerator — scripted calendar events with sliding window.

Mostly stateless generator producing calendar data:
- Scripted CALENDAR_EVENTS for David's day (software engineering manager)
- next_3_events: sliding window of the 3 nearest upcoming events
- reminders: upcoming reminders that haven't passed yet
- today_summary: static natural-language summary generated once per scenario

During crisis, calendar continues normally — events still slide forward.
"""

from __future__ import annotations

from datetime import UTC, datetime, time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import random

    from crisis_bench.generator.schedule import PersonSchedule

# Scripted events for David's day.
# (HH:MM, title, location, [attendees])
_RAW_EVENTS: list[tuple[str, str, str, list[str]]] = [
    ("09:00", "Daily Standup", "Zoom", ["Priya Kapoor", "Mike Chang", "Kira Nakamura"]),
    ("10:00", "Sprint Planning", "Conf Room B", ["Priya Kapoor", "Mike Chang", "Rachel Torres"]),
    ("11:30", "1:1 with Rachel", "Rachel's Office", ["Rachel Torres"]),
    ("12:30", "Lunch with Tom", "Koreatown", ["Tom Brennan"]),
    ("14:00", "Design Review", "Zoom", ["Kira Nakamura", "Priya Kapoor"]),
    ("15:30", "Team Sync", "Conf Room A", ["Priya Kapoor", "Mike Chang"]),
    ("17:30", "Gym", "Home", []),
    ("19:00", "Dinner with Sarah", "Home", ["Sarah Mitchell"]),
]

# Reminders that activate at specific times.
# (HH:MM, reminder text)
_RAW_REMINDERS: list[tuple[str, str]] = [
    ("08:00", "Review PR from Priya"),
    ("12:00", "Take vitamins"),
    ("17:00", "Pick up dry cleaning"),
]


def _parse_time(s: str) -> time:
    """Parse 'HH:MM' into a ``datetime.time``."""
    parts = s.split(":")
    return time(int(parts[0]), int(parts[1]))


_SOCIAL_KEYWORDS = ("lunch", "dinner", "gym", "coffee", "drinks")


def _format_casual_time(time_24h: str) -> str:
    """Convert '14:30' to '2:30pm', '12:00' to 'noon'."""
    h, m = time_24h.split(":")
    hour, minute = int(h), int(m)
    if hour == 12 and minute == 0:
        return "noon"
    suffix = "am" if hour < 12 else "pm"
    display = hour if hour <= 12 else hour - 12
    if display == 0:
        display = 12
    return f"{display}:{minute:02d}{suffix}" if minute else f"{display}{suffix}"


def _build_today_summary(events: list[tuple[str, str, str, list[str]]]) -> str:
    """Generate a natural-language summary from the scripted events list."""
    highlighted: set[int] = set()
    notable_parts: list[str] = []

    # Find notable social/personal events to highlight separately.
    for i, (time_str, title, _loc, _att) in enumerate(events):
        if any(kw in title.lower() for kw in _SOCIAL_KEYWORDS):
            highlighted.add(i)
            notable_parts.append(f"{title.lower()} at {_format_casual_time(time_str)}")

    # Count remaining events as "meetings".
    meeting_count = sum(1 for i, e in enumerate(events) if i not in highlighted and e[3])
    solo_count = sum(1 for i, e in enumerate(events) if i not in highlighted and not e[3])

    parts: list[str] = []
    if meeting_count:
        parts.append(f"{meeting_count} meetings")
    if solo_count:
        parts.append(f"{solo_count} block{'s' if solo_count > 1 else ''}")
    parts.extend(notable_parts)

    return ", ".join(parts)


class CalendarGenerator:
    """Generate calendar data for each heartbeat.

    Builds the event/reminder lists once on first call using scenario_date,
    then returns sliding-window views at each heartbeat.
    """

    def __init__(self) -> None:
        self._events: list[dict[str, object]] | None = None
        self._reminders: list[dict[str, object]] | None = None
        self._today_summary: str | None = None
        self._event_times: list[datetime] | None = None
        self._reminder_times: list[datetime] | None = None

    def generate(
        self,
        schedule: PersonSchedule,
        heartbeat_id: int,
        timestamp: str,
        rng: random.Random,
    ) -> dict[str, object]:
        """Produce one heartbeat's calendar data.

        Consumes exactly 1 RNG call per heartbeat for determinism.
        """
        # Consume 1 RNG call for consistency (calendar is mostly deterministic).
        _unused = rng.random()

        # Lazy init on first call.
        if self._events is None:
            self._init_once(schedule)

        assert self._events is not None
        assert self._reminders is not None
        assert self._event_times is not None
        assert self._reminder_times is not None
        assert self._today_summary is not None

        current = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))

        # Sliding window: next 3 events that haven't started yet.
        upcoming = [
            event
            for event, event_time in zip(self._events, self._event_times, strict=True)
            if event_time > current
        ]
        next_3 = upcoming[:3]

        # Upcoming reminders (not yet passed).
        active_reminders = [
            reminder
            for reminder, rem_time in zip(self._reminders, self._reminder_times, strict=True)
            if rem_time > current
        ]

        return {
            "next_3_events": next_3,
            "reminders": active_reminders,
            "today_summary": self._today_summary,
        }

    def _init_once(self, schedule: PersonSchedule) -> None:
        """Build event and reminder lists anchored to scenario_date."""
        d = schedule.scenario_date

        events: list[dict[str, object]] = []
        event_times: list[datetime] = []
        for time_str, title, location, attendees in _RAW_EVENTS:
            t = _parse_time(time_str)
            dt = datetime.combine(d, t, tzinfo=UTC)
            events.append(
                {
                    "title": title,
                    "time": dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "location": location,
                    "attendees": list(attendees),
                }
            )
            event_times.append(dt)

        reminders: list[dict[str, object]] = []
        reminder_times: list[datetime] = []
        for time_str, text in _RAW_REMINDERS:
            t = _parse_time(time_str)
            dt = datetime.combine(d, t, tzinfo=UTC)
            reminders.append(
                {
                    "text": text,
                    "time": dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
                }
            )
            reminder_times.append(dt)

        self._events = events
        self._event_times = event_times
        self._reminders = reminders
        self._reminder_times = reminder_times

        # Generate today_summary from the events list.
        self._today_summary = _build_today_summary(_RAW_EVENTS)
