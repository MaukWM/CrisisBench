# Story 2.4: Communications Module Generator

Status: review

## Story

As a **researcher**,
I want scripted communications (emails, SMS, Slack, social notifications) appearing at realistic times throughout the day,
So that heartbeats contain authentic messaging noise without LLM-generated content.

## Acceptance Criteria

1. **Given** a scripted `_COMMS_EVENTS` list, **When** CommsGenerator produces data for a heartbeat, **Then** only communications scheduled at or before that heartbeat's timestamp appear in the cumulative fields.

2. **Given** T3/T4 tier communications, **When** I inspect a heartbeat's comms module, **Then** emails show sender+subject only (no body), SMS/Slack show complete messages, social shows platform+notification_text.

3. **Given** any heartbeat, **Then** `unread_emails`, `slack_messages`, `missed_calls`, `voicemail_count`, `sms`, and `social_notifications` are all populated (may be empty lists / zero counts early in the day).

4. **Given** two runs with the same seed, **When** I compare CommsGenerator output, **Then** they are identical (deterministic via shared `rng`).

5. **Given** T1 or T2 tier, **Then** comms module is `None` (excluded by `TIER_MODULES`). T3+ includes comms.

6. **Given** crisis heartbeats, **Then** comms data continues accumulating normally (people keep messaging David even though he collapsed — the comms system doesn't know about the crisis).

## Tasks / Subtasks

- [x] Task 1: Create `CommsGenerator` in `src/crisis_bench/generator/modules/comms.py` (AC: #1-4, #6)
  - [x] 1.1: Define scripted `_EMAIL_EVENTS` constant — 10 emails arriving throughout the day from realistic senders (Priya, Mike, Rachel, Kira, LinkedIn, Amazon, GitHub, HR, Bank of America). Sender+subject only.
  - [x] 1.2: Define scripted `_SLACK_EVENTS` constant — 8 Slack messages in work channels (#engineering, #general, #design-review, #random) from coworkers, arriving during work hours (09:05-16:30).
  - [x] 1.3: Define scripted `_SMS_EVENTS` constant — 4 SMS messages from contacts (Sarah Mitchell, Jake Mitchell, Tom Brennan) at contextually appropriate times.
  - [x] 1.4: Define scripted `_MISSED_CALL_EVENTS` constant — 2 missed calls (unknown spam at 10:45, Tom Brennan at 14:30 during Design Review).
  - [x] 1.5: Define scripted `_SOCIAL_EVENTS` constant — 5 social notifications from Instagram, LinkedIn, Reddit, X throughout the day.
  - [x] 1.6: Implement `__init__` with lazy init state tracking (same pattern as `FinancialGenerator`).
  - [x] 1.7: Implement `generate()` method: accumulate events by timestamp, return dict matching `CommsData` fields. Sliding windows for slack (last 5) and social (last 3).
  - [x] 1.8: Implement `_init_once()`: parse event times, anchor to `schedule.scenario_date`.
  - [x] 1.9: Fixed RNG consumption per heartbeat (1 call for determinism — same as CalendarGenerator pattern).

- [x] Task 2: Register CommsGenerator in `generate.py` (AC: #5)
  - [x] 2.1: Add `from crisis_bench.generator.modules.comms import CommsGenerator` import in `_collect_generators()`
  - [x] 2.2: Add `"comms": CommsGenerator()` to the registry dict (between calendar and financial)

- [x] Task 3: Update `generator/modules/__init__.py`
  - [x] 3.1: Add `comms` import line (with `# noqa: F401`)

- [x] Task 4: Write tests in `tests/generator/test_generate.py` (AC: #1-6)
  - [x] 4.1: `TestCommsRealism` class with 12 test methods
  - [x] 4.2: Test accumulation: early heartbeats have fewer items than later ones
  - [x] 4.3: Test determinism: same seed = same output
  - [x] 4.4: Test crisis continuation: comms keep arriving during/after crisis heartbeats
  - [x] 4.5: Test tier exclusion: T1/T2 packages have `comms=None`, T3+ have `CommsData`
  - [x] 4.6: Test field population: all 6 CommsData fields present and correctly typed

- [x] Task 5: Run `uv run pre-commit run --all-files` and fix any issues

## Dev Notes

### Generator Protocol (from `generate.py:39-50`)

All generators implement:
```python
class ModuleGenerator(Protocol):
    def generate(
        self,
        schedule: PersonSchedule,
        heartbeat_id: int,
        timestamp: str,
        rng: random.Random,
    ) -> dict[str, object] | None:
        ...
```

Return a dict matching `CommsData` field names. Converted to frozen Pydantic model in `_build_heartbeat()` via `_MODULE_MODEL_MAP` (line 304).

### CommsData Pydantic Model (from `models/scenario.py:134-146`)

```python
class CommsData(BaseModel):
    model_config = ConfigDict(frozen=True)
    unread_emails: list[Email]           # Email: sender, subject
    slack_messages: list[SlackMessage]   # SlackMessage: channel, sender, message
    missed_calls: int                    # Count
    voicemail_count: int                 # Count
    sms: list[Sms]                      # Sms: sender, message
    social_notifications: list[SocialNotification]  # SocialNotification: platform, notification_text
```

Supporting models (`scenario.py:97-131`): `Email(sender, subject)`, `SlackMessage(channel, sender, message)`, `Sms(sender, message)`, `SocialNotification(platform, notification_text)`.

### Implementation Pattern: Follow FinancialGenerator Exactly

`FinancialGenerator` (`financial.py`) is the closest analog — scripted time-based events accumulating over the day. Copy its pattern:

1. **Module-level constants** for scripted events with `(HH:MM, ...)` tuples
2. **`__init__`** sets state to `None` for lazy init, plus accumulator state
3. **`_init_once(schedule)`** parses time strings, anchors to `schedule.scenario_date`
4. **`generate()`** consumes fixed RNG calls, processes events up to current timestamp, returns dict

### Scripted Comms Event Design

**Emails (arrive throughout the day):**
- Use realistic senders: work colleagues from `_DEFAULT_CONTACTS` (Priya, Mike, Rachel, Kira), plus external (newsletter, Amazon shipping, bank alert, LinkedIn).
- Subject lines should be mundane work/life content. Zero health/emergency framing (NFR2).
- Accumulate: `unread_emails` grows as emails arrive (agent never "reads" them in generation).

**Slack messages (work hours 09:00-17:30):**
- Channels: `#engineering`, `#general`, `#design-review`, `#random`
- Senders: coworkers (Priya, Mike, Kira, others)
- Short realistic messages ("PR approved", "standup in 5", "anyone tried the new Rust compiler?")

**SMS (throughout the day):**
- From known contacts: Sarah ("dinner still on for 7?"), Jake ("check out this meme"), Tom ("gym at 5:30?")
- Use contact names from `_DEFAULT_CONTACTS` in generate.py

**Missed calls (1-2 during the day):**
- One spam/unknown number mid-morning
- Possibly one from a contact during a meeting (accumulate count)

**Voicemail (0-1):**
- Voicemail from the spam caller or none. Static count.

**Social notifications (sporadic):**
- Platforms: Instagram, X/Twitter, LinkedIn, Reddit
- Mundane: "Tom Brennan liked your photo", "5 new posts in r/programming", "You have 3 new connection requests"

### RNG Consumption

Comms is almost entirely scripted — minimal RNG needed. Consume exactly **1 RNG call** per heartbeat for determinism (same as CalendarGenerator pattern). This keeps the shared RNG stream predictable for downstream generators.

### Accumulation Logic

Unlike `last_3_transactions` (sliding window of 3), comms fields are **cumulative within the day**:
- `unread_emails`: grows as new emails arrive (all emails stay "unread" since the agent doesn't read them during generation)
- `slack_messages`: show the **last 5** messages (sliding window — Slack is high-volume, showing all would be unrealistic)
- `missed_calls`: integer counter, increments when a missed call event occurs
- `voicemail_count`: integer counter, increments when voicemail event occurs
- `sms`: show **all SMS** received today (low volume, ~4-6 total)
- `social_notifications`: show the **last 3** notifications (sliding window)

### Crisis Behavior

Comms continue arriving normally during and after crisis. The messaging systems have no awareness of the health event. This mirrors reality — David's phone keeps receiving notifications even if he's incapacitated.

### NFR2: Zero Health/Emergency Framing

All scripted content (email subjects, Slack messages, SMS text, social notifications) must contain ZERO health/emergency/safety language. No "are you okay?", no "emergency", no medical terms. Pure mundane work/life content.

### pending_responses (FR14)

The `pending_responses` concept (new messages since previous heartbeat) is a **runner concern** (Epic 3, Story 3.2 — PromptBuilder). The generator produces cumulative comms state; the runner diffs consecutive heartbeats to derive what's new. No special handling needed in the generator.

### Existing Wiring (Already Done)

- `"comms"` is already in `ALL_MODULE_NAMES` (`generate.py:62`)
- `"comms"` is already in `TIER_MODULES["T3"]` and `TIER_MODULES["T4"]` (`generate.py:69-70`)
- `CommsData` is already in `_MODULE_MODEL_MAP` (`generate.py:309`)
- `CommsData` is already imported in `generate.py` (line 22)
- `HeartbeatPayload` already has an optional `comms` field

The ONLY missing piece is the `CommsGenerator` class itself and its registration in `_collect_generators()`.

### Anti-Synthetic Lessons (from Stories 2.1, 2.2, 2.3)

1. **Realistic timing** — emails cluster during work hours, SMS are sporadic, Slack dies after 17:00
2. **Context-appropriate content** — morning emails are about yesterday's PRs, afternoon Slack is about design review
3. **Not perfectly uniform** — some heartbeats have nothing new, some have 2-3 events at once
4. **Use real contact names** — senders should be from `_DEFAULT_CONTACTS` where appropriate
5. **Crisis continues normally** — comms keep arriving post-crisis

### What This Story Does NOT Include

- `pending_responses` computation (runner concern — Epic 3)
- CrisisInjector or scenario packaging (Story 2.5)
- Any changes to existing generators (health, location, weather, calendar, financial)
- Any runner/orchestrator work (Epic 3)

### Project Structure Notes

New file:
- `src/crisis_bench/generator/modules/comms.py`

Modified files:
- `src/crisis_bench/generator/generate.py` (1 import + 1 registry entry in `_collect_generators`)
- `src/crisis_bench/generator/modules/__init__.py` (1 new import line)
- `tests/generator/test_generate.py` (add `TestCommsRealism` class)

### References

- [Source: src/crisis_bench/models/scenario.py#CommsData] — CommsData, Email, SlackMessage, Sms, SocialNotification models (lines 97-146)
- [Source: src/crisis_bench/generator/generate.py#ModuleGenerator] — Protocol interface (lines 39-50)
- [Source: src/crisis_bench/generator/generate.py#_collect_generators] — Where to register (lines 182-201)
- [Source: src/crisis_bench/generator/generate.py#TIER_MODULES] — T3 adds comms (lines 66-71)
- [Source: src/crisis_bench/generator/generate.py#_MODULE_MODEL_MAP] — CommsData already mapped (line 309)
- [Source: src/crisis_bench/generator/generate.py#_DEFAULT_CONTACTS] — Contact names for SMS/Slack senders (lines 85-169)
- [Source: src/crisis_bench/generator/modules/financial.py] — Closest pattern reference (scripted time-based events)
- [Source: src/crisis_bench/generator/modules/calendar.py] — CalendarGenerator pattern (1 RNG call, scripted events)
- [Source: src/crisis_bench/generator/schedule.py#PersonSchedule] — schedule.scenario_date, heartbeat_timestamps()
- [Source: _bmad-output/planning-artifacts/architecture.md#Core Architectural Decisions] — NFR2, determinism, tool contracts
- [Source: _bmad-output/planning-artifacts/epics.md#Story 2.4] — Original AC
- [Source: _bmad-output/implementation-artifacts/2-3-weather-calendar-financial-module-generators.md] — Previous story patterns

## Dev Agent Record

### Agent Model Used

Claude Opus 4.6

### Debug Log References

No issues encountered during implementation.

### Completion Notes List

- Implemented `CommsGenerator` following the `FinancialGenerator`/`CalendarGenerator` patterns exactly
- 10 scripted emails from realistic senders (coworkers, newsletters, automated notifications) — sender+subject only per AC #2
- 8 Slack messages across 4 channels (#engineering, #general, #design-review, #random) during work hours
- 4 SMS from contacts (Sarah, Jake, Tom) at contextually appropriate times
- 2 missed calls (spam at 10:45, Tom at 14:30) with 1 voicemail from spam caller
- 5 social notifications from Instagram, LinkedIn, Reddit, X
- All content is mundane work/life — zero health/emergency framing (NFR2 compliant)
- Accumulation logic: unread_emails cumulative, slack last-5 window, sms cumulative, social last-3 window, missed_calls/voicemail as counters
- 1 RNG call per heartbeat for determinism (CalendarGenerator pattern)
- 68 tests pass (12 new + 56 existing), zero regressions
- All pre-commit hooks pass (ruff, mypy, codespell, secrets, pip-audit)

### Change Log

- 2026-02-27: Implemented story 2.4 — CommsGenerator module, registration, tests
- 2026-02-27: Refactored to notification-based design (architecture Decision 13). All CommsData fields now per-heartbeat deltas instead of cumulative. Renamed fields: unread_emails→new_emails, slack_messages→new_slack_messages, missed_calls→new_missed_calls, voicemail_count→new_voicemails, sms→new_sms, social_notifications→new_notifications. Event timings made irregular/clustered for realism. Updated architecture.md Decision 13.

### File List

- `src/crisis_bench/generator/modules/comms.py` (new)
- `src/crisis_bench/generator/generate.py` (modified — added CommsGenerator import + registry entry)
- `src/crisis_bench/generator/modules/__init__.py` (modified — added comms import)
- `tests/generator/test_generate.py` (modified — added TestCommsRealism class with 12 tests)
