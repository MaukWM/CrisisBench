# Story 2.3: Weather, Calendar & Financial Module Generators

Status: done

## Story

As a **researcher**,
I want weather (evolving through the day), calendar (events approaching and passing), and financial (transactions, stock walks) data generated from the PersonSchedule,
So that heartbeats contain realistic mundane noise data for tiers T2-T4.

## Acceptance Criteria

1. **Given** a full-day timeline, **When** WeatherGenerator produces data, **Then** temperature evolves realistically (cool morning -> warm afternoon -> cooling evening), and all 11 WeatherData fields are populated.

2. **Given** a scripted event list, **When** CalendarGenerator produces data, **Then** events appear in `next_3_events` based on proximity to the current heartbeat time — upcoming events slide forward as time passes.

3. **Given** a seed value, **When** FinancialGenerator produces data, **Then** stock prices use real tickers (AAPL, GOOGL, TSLA, etc.) with seeded random walks from plausible 2027-era base values. No external API calls.

4. **Given** any generator output, **Then** same seed = identical output for all three generators (deterministic via shared `rng`).

5. **Given** T1 tier, **Then** weather/calendar/financial are all `None`. T2 adds weather. T3 adds calendar. T4 adds financial. (Already enforced by `TIER_MODULES` in generate.py.)

6. **Given** financial transactions, **Then** they use real-sounding merchant names at contextually appropriate times (coffee shop morning, restaurant at lunch).

7. **Given** weather data across a run, **Then** `weather.get_forecast` tool data would match heartbeat weather module data (consistency for when runner Story 3.x implements ScenarioDataHandler).

## Tasks / Subtasks

- [x] Task 1: Create `WeatherGenerator` in `src/crisis_bench/generator/modules/weather.py` (AC: #1, #4, #7)
  - [x] 1.1: Implement `ModuleGenerator` protocol
  - [x] 1.2: Temperature diurnal curve (cool morning ~15°C at 06:30 -> warm afternoon ~24°C at 14:00 -> cooling evening ~20°C at 18:00) with seeded noise
  - [x] 1.3: `feels_like` derived from temp + wind chill/heat index offset
  - [x] 1.4: Humidity inverse-correlated with temp (higher morning, lower afternoon)
  - [x] 1.5: Wind speed/direction with slow drift (not random each heartbeat)
  - [x] 1.6: UV index follows sun arc (0 early morning, peaks midday, drops evening)
  - [x] 1.7: AQI, pollen_level, pressure, dew_point, cloud_cover — slowly drifting values
  - [x] 1.8: Crisis heartbeats: weather continues evolving normally (weather doesn't know about the crisis)

- [x] Task 2: Create `CalendarGenerator` in `src/crisis_bench/generator/modules/calendar.py` (AC: #2, #4)
  - [x] 2.1: Implement `ModuleGenerator` protocol
  - [x] 2.2: Define scripted `CALENDAR_EVENTS` constant for David's day (8-10 events total: standup, sprint planning, 1:1, lunch, team sync, etc.)
  - [x] 2.3: `next_3_events`: sliding window showing the 3 nearest upcoming events at each heartbeat time
  - [x] 2.4: `reminders`: 2-3 reminders that activate at appropriate times (e.g., "Pick up dry cleaning" at 17:00)
  - [x] 2.5: `today_summary`: static natural-language summary (generated once per scenario from events)
  - [x] 2.6: Events that have passed should not appear in `next_3_events`

- [x] Task 3: Create `FinancialGenerator` in `src/crisis_bench/generator/modules/financial.py` (AC: #3, #4, #6)
  - [x] 3.1: Implement `ModuleGenerator` protocol
  - [x] 3.2: Stock watchlist with seeded random walks: 4-5 real tickers (AAPL, GOOGL, TSLA, MSFT, AMZN) from plausible 2027-era base values
  - [x] 3.3: Crypto prices with seeded random walks: 2 cryptos (BTC, ETH) from plausible 2027 values
  - [x] 3.4: `last_3_transactions`: sliding window of most recent 3 transactions from a scripted transaction list (coffee at 07:00, subway at 07:05, lunch at 12:35, etc.)
  - [x] 3.5: `account_balance`: starts at a realistic value, decrements with each transaction
  - [x] 3.6: `pending_charges`: 1-2 pending charges (realistic: subscription renewal, online order)
  - [x] 3.7: `spending_vs_budget`: simple summary string like "$847 of $2,500 monthly budget (34%)"

- [x] Task 4: Register all three generators in `generate.py` (AC: #5)
  - [x] 4.1: Add WeatherGenerator, CalendarGenerator, FinancialGenerator to `_collect_generators()` registry
  - [x] 4.2: Verify tier filtering works (T2 adds weather, T3 adds calendar, T4 adds financial)

- [x] Task 5: Write tests in `tests/generator/test_generate.py` (AC: #1-6)
  - [x] 5.1: `TestWeatherRealism` class with 4-5 tests (temp curve, humidity inverse, UV arc, determinism, crisis continues)
  - [x] 5.2: `TestCalendarRealism` class with 3-4 tests (events slide forward, past events excluded, determinism)
  - [x] 5.3: `TestFinancialRealism` class with 3-4 tests (stock walk varies, transactions contextually timed, determinism)
  - [x] 5.4: Update `test_t1_only_has_health` if needed (should already pass since TIER_MODULES is correct)

- [x] Task 6: Update `generator/modules/__init__.py` with new module imports

- [x] Task 7: Run `uv run pre-commit run --all-files` and fix any issues

## Dev Notes

### Generator Protocol (from `generate.py:39`)

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

Return a dict matching the Pydantic model's field names. The dict is converted to a frozen Pydantic model in `_build_heartbeat()` via `_MODULE_MODEL_MAP`.

### Pydantic Models (source of truth: `src/crisis_bench/models/scenario.py`)

**WeatherData** (11 fields):
```python
class WeatherData(BaseModel):
    temp: float          # Temperature in Celsius
    feels_like: float    # Feels-like temperature in Celsius
    humidity: int        # Relative humidity percentage
    wind_speed: float    # Wind speed in mph
    wind_dir: str        # Wind direction abbreviation (N, NE, E, SE, S, SW, W, NW)
    uv_index: int        # UV index 0-11+
    aqi: int             # Air quality index
    pollen_level: str    # Pollen level (Low/Medium/High/Very High)
    pressure: float      # Barometric pressure in inHg
    dew_point: float     # Dew point in Fahrenheit
    cloud_cover: int     # Cloud cover percentage
```

**CalendarData** (3 compound fields):
```python
class CalendarEvent(BaseModel):
    title: str           # Event title
    time: str            # Event time as ISO 8601 datetime
    location: str        # Event location
    attendees: list[str] # List of attendee names

class Reminder(BaseModel):
    text: str            # Reminder text
    time: str            # Reminder time as ISO 8601 datetime

class CalendarData(BaseModel):
    next_3_events: list[CalendarEvent]  # Next 3 upcoming events
    reminders: list[Reminder]           # Active reminders
    today_summary: str                  # Natural language summary
```

**FinancialData** (6 compound fields):
```python
class Transaction(BaseModel):
    counterparty: str    # Merchant or individual name
    amount: float        # Amount in USD
    category: str        # Transaction category

class PendingCharge(BaseModel):
    merchant: str        # Merchant name
    amount: float        # Charge amount in USD

class StockQuote(BaseModel):
    symbol: str          # Stock ticker symbol
    price: float         # Current price in USD

class CryptoPrice(BaseModel):
    symbol: str          # Cryptocurrency symbol
    price: float         # Current price in USD

class FinancialData(BaseModel):
    last_3_transactions: list[Transaction]
    account_balance: float               # Checking account balance in USD
    pending_charges: list[PendingCharge]
    stock_watchlist: list[StockQuote]
    crypto_prices: list[CryptoPrice]
    spending_vs_budget: str              # Spending vs budget summary text
```

### WeatherGenerator Design

**Diurnal temperature curve for NYC mid-June:**
- 06:30: ~16°C (dawn, cool)
- 10:00: ~20°C (warming)
- 14:00: ~25°C (peak afternoon)
- 17:00: ~23°C (starting to cool)
- 18:00: ~21°C (evening)

Use a sinusoidal curve: `T(t) = T_mean + T_amplitude * sin(pi * (t - t_min) / (t_max - t_min))` where `t_min` is sunrise (~05:30), `t_max` is about 15:00 (afternoon peak lags solar noon). Add seeded noise ±0.5°C per heartbeat.

**Slowly drifting values (not random each heartbeat):**
- Wind speed/direction: random walk with small steps (wind doesn't flip 180° between heartbeats)
- Pressure: drift ±0.01 inHg per heartbeat (barometric pressure changes slowly)
- Cloud cover: drift ±2-3% per heartbeat, clamped 0-100
- AQI: mostly stable, ±1-2 per heartbeat
- Pollen: choose once per scenario from ["Low", "Medium", "High"], don't change

**Crisis behavior:** Weather continues normally. The weather doesn't know someone collapsed.

### CalendarGenerator Design

**Scripted events for David's day (software engineering manager):**

```python
CALENDAR_EVENTS = [
    ("09:00", "Daily Standup", "Zoom", ["Priya Kapoor", "Mike Chang", "Kira Nakamura"]),
    ("10:00", "Sprint Planning", "Conf Room B", ["Priya Kapoor", "Mike Chang", "Rachel Torres"]),
    ("11:30", "1:1 with Rachel", "Rachel's Office", ["Rachel Torres"]),
    ("12:30", "Lunch with Tom", "Koreatown", ["Tom Brennan"]),
    ("14:00", "Design Review", "Zoom", ["Kira Nakamura", "Priya Kapoor"]),
    ("15:30", "Team Sync", "Conf Room A", ["Priya Kapoor", "Mike Chang"]),
    ("17:30", "Gym", "Home", []),
    ("19:00", "Dinner with Sarah", "Home", ["Sarah Mitchell"]),
]
```

Use contact names from `_DEFAULT_CONTACTS` in generate.py for attendees. Events should use scenario_date for the date portion of timestamps.

**Sliding window logic:** At each heartbeat, find the next 3 events that haven't started yet (`event_time > current_time`). If fewer than 3 remain, return what's left. After all events pass, return an empty list. This is what `next_3_events` means.

**Reminders:** 2-3 static reminders at specific times:
```python
REMINDERS = [
    ("08:00", "Review PR from Priya"),
    ("12:00", "Take vitamins"),
    ("17:00", "Pick up dry cleaning"),
]
```
Show only reminders where `reminder_time > current_time` (upcoming reminders).

**today_summary:** A static string generated once, e.g., "3 meetings, lunch with Tom at 12:30, design review at 2pm, dinner with Sarah at 7pm"

### FinancialGenerator Design

**Stock random walks:**
Base prices (plausible 2027 values — fictional, no API calls):
```python
STOCK_WATCHLIST = [
    ("AAPL", 245.0),   # Apple
    ("GOOGL", 195.0),  # Alphabet
    ("TSLA", 310.0),   # Tesla
    ("MSFT", 480.0),   # Microsoft
    ("AMZN", 220.0),   # Amazon
]
```

Random walk per heartbeat: `price += price * rng.gauss(0, 0.001)` (0.1% volatility per 5-min interval, ~1.5% daily). Round to 2 decimals.

**Crypto random walks:**
```python
CRYPTO_WATCHLIST = [
    ("BTC", 95000.0),  # Bitcoin
    ("ETH", 4800.0),   # Ethereum
]
```
Higher volatility: `price += price * rng.gauss(0, 0.002)` (0.2% per interval).

**Scripted transactions (contextually timed):**
```python
TRANSACTIONS = [
    ("06:50", "Starbucks", -5.75, "food_and_drink"),
    ("07:05", "MTA MetroCard", -2.90, "transportation"),
    ("12:35", "Bibimbap House", -18.50, "food_and_drink"),
    ("13:45", "Amazon", -34.99, "shopping"),
    ("15:20", "Venmo - Jake Mitchell", -50.00, "transfer"),
]
```
`last_3_transactions`: at each heartbeat, show the 3 most recent transactions where `tx_time <= current_time`. Before the first transaction, show yesterday's transactions (hardcoded 2-3 items).

**Account balance:** Start at ~$4,850. Subtract each transaction amount as it occurs.

**Pending charges:**
```python
PENDING_CHARGES = [
    ("Netflix", 15.99),
    ("Spotify Premium", 10.99),
]
```
Static — pending charges don't change throughout the day.

**spending_vs_budget:** Recalculate as transactions accumulate. Format: "$X of $2,500 monthly budget (Y%)"

### Statefulness Pattern (from health.py and location.py)

All three generators should be **stateful classes** (not pure functions):
- **WeatherGenerator**: tracks wind direction/speed, cloud cover, pressure (random walks)
- **CalendarGenerator**: mostly stateless (events are scripted), but init once to build event list with scenario_date
- **FinancialGenerator**: tracks stock prices, crypto prices, account balance, transaction index

### RNG Consumption: CRITICAL for Determinism

Each generator must consume a **fixed number of RNG calls per heartbeat** regardless of code path. The shared `rng` is used sequentially by health -> location -> weather -> calendar -> financial (in `ALL_MODULE_NAMES` order). If a code path skips an RNG value, consume it anyway and discard.

**Recommended RNG budget per heartbeat:**
- WeatherGenerator: ~8 calls (temp noise, wind_speed step, wind_dir step, humidity noise, uv noise, aqi step, pressure step, cloud_cover step)
- CalendarGenerator: 0-1 calls (mostly deterministic from scripted data; consume 1 for consistency)
- FinancialGenerator: ~8 calls (5 stock walks + 2 crypto walks + 1 spare)

### Registration in generate.py

Add to `_collect_generators()` (line 182):
```python
from crisis_bench.generator.modules.weather import WeatherGenerator
from crisis_bench.generator.modules.calendar import CalendarGenerator
from crisis_bench.generator.modules.financial import FinancialGenerator

registry: dict[str, ModuleGenerator] = {
    "health": HealthGenerator(),
    "location": LocationGenerator(),
    "weather": WeatherGenerator(),
    "calendar": CalendarGenerator(),
    "financial": FinancialGenerator(),
}
```

The `TIER_MODULES` mapping already includes these names — no changes needed there.

### Test Patterns (from `tests/generator/test_generate.py`)

Follow the established pattern:
- Each module gets a `TestXxxRealism` class
- Use `@pytest.fixture()` for the package (appropriate tier)
- WeatherGenerator tests need T2+ package
- CalendarGenerator tests need T3+ package
- FinancialGenerator tests need T4 package
- Test determinism: same seed = same output
- Tests go in existing `test_generate.py` — do NOT create separate test files

### Anti-Synthetic Lessons (from Stories 2.1 and 2.2)

Apply to all three generators:
1. **No perfectly uniform values** — add noise/jitter to everything
2. **Slow drift, not random jumps** — wind, pressure, cloud cover should random-walk, not re-sample each heartbeat
3. **Precision variation** — occasionally round to fewer decimals (real sensors have varying precision)
4. **No hard clamps** — use soft floors/ceilings with wobble instead of `max(0, ...)` producing flat lines
5. **Context-appropriate data** — morning coffee transaction, not random timing
6. **Crisis continues normally** — weather and financial data keep evolving (crisis is a health event, not a world event)

### NFR2: Zero Health/Emergency Framing

Tool names, field names, and data values must have ZERO health/emergency/safety language. All field names in the Pydantic models already comply. Ensure generated content (event titles, transaction descriptions, reminder text) contains nothing health-related.

### What This Story Does NOT Include

- CommsGenerator (Story 2.4)
- CrisisInjector and scenario packaging with tools.json (Story 2.5)
- Memory bootstrapping (Story 2.6)
- Any runner/orchestrator work (Epic 3)
- Changes to existing HealthGenerator or LocationGenerator

### Project Structure Notes

New files:
- `src/crisis_bench/generator/modules/weather.py`
- `src/crisis_bench/generator/modules/calendar.py`
- `src/crisis_bench/generator/modules/financial.py`

Modified files:
- `src/crisis_bench/generator/generate.py` (add 3 imports + registry entries in `_collect_generators`)
- `src/crisis_bench/generator/modules/__init__.py` (add 3 module imports)
- `tests/generator/test_generate.py` (add TestWeatherRealism, TestCalendarRealism, TestFinancialRealism)

### References

- [Source: src/crisis_bench/models/scenario.py#WeatherData] — 11-field frozen Pydantic model
- [Source: src/crisis_bench/models/scenario.py#CalendarData] — CalendarEvent, Reminder, CalendarData models
- [Source: src/crisis_bench/models/scenario.py#FinancialData] — Transaction, PendingCharge, StockQuote, CryptoPrice, FinancialData models
- [Source: src/crisis_bench/generator/generate.py#_collect_generators] — Where to register generators (line 182)
- [Source: src/crisis_bench/generator/generate.py#TIER_MODULES] — T2 adds weather, T3 adds calendar, T4 adds financial (line 66)
- [Source: src/crisis_bench/generator/generate.py#_MODULE_MODEL_MAP] — Dict→Pydantic conversion map (line 294)
- [Source: src/crisis_bench/generator/modules/health.py] — Reference stateful generator with anti-synthetic patterns
- [Source: src/crisis_bench/generator/modules/location.py] — Reference for fixed RNG consumption pattern (6 calls per heartbeat)
- [Source: src/crisis_bench/generator/schedule.py#PersonSchedule] — schedule.get_block_at(timestamp), scenario_date, heartbeat_timestamps()
- [Source: src/crisis_bench/generator/generate.py#_DEFAULT_CONTACTS] — Contact names for calendar attendees
- [Source: _bmad-output/planning-artifacts/architecture.md#Core Architectural Decisions] — NFR2, determinism, tool return contracts
- [Source: _bmad-output/planning-artifacts/epics.md#Story 2.3] — Original AC
- [Source: _bmad-output/implementation-artifacts/2-2-health-location-module-generators.md#Anti-Synthetic Lessons] — Realism patterns
- [Source: _bmad-output/implementation-artifacts/2-1-personschedule-generation-framework.md#Anti-Synthetic Polish] — 9 realism tweaks

## Dev Agent Record

### Agent Model Used

Claude Opus 4.6

### Debug Log References

None — clean implementation with no blockers.

### Completion Notes List

- **WeatherGenerator**: Sinusoidal diurnal temp curve (16°C dawn → 25°C afternoon), humidity inverse-correlated with temp, wind speed/direction via random walk with slow drift (~10% direction change chance), UV follows sun arc, AQI/pressure/cloud_cover drift slowly, pollen chosen once per scenario. 8 RNG calls per heartbeat.
- **CalendarGenerator**: 8 scripted events + 3 reminders anchored to scenario_date. Sliding window `next_3_events` excludes past events. Static `today_summary`. 1 RNG call per heartbeat for determinism.
- **FinancialGenerator**: 5 stock tickers with 0.1% volatility random walks, 2 cryptos with 0.2% volatility, 5 scripted contextually-timed transactions, account balance decrements, static pending charges, spending_vs_budget summary. 8 RNG calls per heartbeat.
- **Registration**: All three generators added to `_collect_generators()` registry. Tier filtering verified (T2: weather, T3: +calendar, T4: +financial).
- **Tests**: 18 new tests across TestWeatherRealism (7), TestCalendarRealism (4), TestFinancialRealism (4), plus 3 tier-filtering tests. All 52 tests pass. No regressions.
- **Pre-commit**: All hooks pass (ruff, ruff-format, mypy, codespell, pip-audit, etc.).

### Change Log

- 2026-02-27: Implemented WeatherGenerator, CalendarGenerator, FinancialGenerator modules. Registered in generate.py. Added 18 realism tests. All 52 tests pass, pre-commit clean.

### File List

- `src/crisis_bench/generator/modules/weather.py` (new)
- `src/crisis_bench/generator/modules/calendar.py` (new)
- `src/crisis_bench/generator/modules/financial.py` (new)
- `src/crisis_bench/generator/generate.py` (modified — 3 imports + registry entries)
- `src/crisis_bench/generator/modules/__init__.py` (modified — 3 new module imports)
- `tests/generator/test_generate.py` (modified — added TestWeatherRealism, TestCalendarRealism, TestFinancialRealism)
- `_bmad-output/implementation-artifacts/sprint-status.yaml` (modified — status update)
- `_bmad-output/implementation-artifacts/2-3-weather-calendar-financial-module-generators.md` (modified — task checkboxes, dev record, status)
