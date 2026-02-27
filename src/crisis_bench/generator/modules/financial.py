"""FinancialGenerator — stock walks, crypto, scripted transactions.

Stateful generator producing financial data:
- Stock watchlist with seeded random walks from plausible 2027-era base values
- Crypto prices with higher-volatility random walks
- Scripted transactions with contextually appropriate timing
- Account balance decrementing with each transaction
- Static pending charges
- Spending vs budget summary

During crisis, financial data continues evolving — markets don't know
someone collapsed.
"""

from __future__ import annotations

from datetime import UTC, datetime, time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import random

    from crisis_bench.generator.schedule import PersonSchedule

# Stock watchlist: (ticker, plausible 2027 base price).
_STOCK_WATCHLIST: list[tuple[str, float]] = [
    ("AAPL", 245.0),
    ("GOOGL", 195.0),
    ("TSLA", 310.0),
    ("MSFT", 480.0),
    ("AMZN", 220.0),
]

# Crypto watchlist: (symbol, plausible 2027 base price).
_CRYPTO_WATCHLIST: list[tuple[str, float]] = [
    ("BTC", 95000.0),
    ("ETH", 4800.0),
]

# Scripted transactions: (HH:MM, counterparty, amount, category).
# Negative amounts = spending.
_RAW_TRANSACTIONS: list[tuple[str, str, float, str]] = [
    ("06:50", "Starbucks", -5.75, "food_and_drink"),
    ("07:05", "MTA MetroCard", -2.90, "transportation"),
    ("12:35", "Bibimbap House", -18.50, "food_and_drink"),
    ("13:45", "Amazon", -34.99, "shopping"),
    ("15:20", "Venmo - Jake Mitchell", -50.00, "transfer"),
]

# Yesterday's transactions (shown before today's first transaction).
_YESTERDAY_TRANSACTIONS: list[dict[str, object]] = [
    {"counterparty": "Whole Foods Market", "amount": -67.43, "category": "groceries"},
    {"counterparty": "Con Edison", "amount": -142.30, "category": "utilities"},
    {"counterparty": "Spotify Premium", "amount": -10.99, "category": "subscription"},
]

# Static pending charges.
_PENDING_CHARGES: list[dict[str, object]] = [
    {"merchant": "Netflix", "amount": 15.99},
    {"merchant": "Spotify Premium", "amount": 10.99},
]

# Starting account balance and monthly budget.
_STARTING_BALANCE = 4850.00
_MONTHLY_BUDGET = 2500.00
# Prior spending this month (before today).
_PRIOR_MONTH_SPENDING = 735.00


def _parse_time(s: str) -> time:
    """Parse 'HH:MM' into a ``datetime.time``."""
    parts = s.split(":")
    return time(int(parts[0]), int(parts[1]))


class FinancialGenerator:
    """Generate financial data for each heartbeat.

    Tracks stock/crypto prices via random walks and transaction state
    across heartbeats.
    """

    def __init__(self) -> None:
        self._stock_prices: list[float] | None = None
        self._crypto_prices: list[float] | None = None
        self._account_balance: float = _STARTING_BALANCE
        self._transactions: list[tuple[datetime, dict[str, object]]] | None = None
        self._tx_index: int = 0  # next unprocessed transaction
        self._active_transactions: list[dict[str, object]] = list(_YESTERDAY_TRANSACTIONS)
        self._total_spent_today: float = 0.0

    def generate(
        self,
        schedule: PersonSchedule,
        heartbeat_id: int,
        timestamp: str,
        rng: random.Random,
    ) -> dict[str, object]:
        """Produce one heartbeat's financial data.

        Consumes exactly 8 RNG calls per heartbeat for determinism:
        5 stock walks + 2 crypto walks + 1 spare.
        """
        # Lazy init on first call.
        if self._stock_prices is None:
            self._init_once(schedule)

        assert self._stock_prices is not None
        assert self._crypto_prices is not None
        assert self._transactions is not None

        # 5 stock random walks (0.1% volatility per 5-min interval).
        for i in range(len(_STOCK_WATCHLIST)):
            step = rng.gauss(0, 0.001)
            self._stock_prices[i] *= 1.0 + step
            self._stock_prices[i] = round(self._stock_prices[i], 2)

        # 2 crypto random walks (0.2% volatility).
        for i in range(len(_CRYPTO_WATCHLIST)):
            step = rng.gauss(0, 0.002)
            self._crypto_prices[i] *= 1.0 + step
            self._crypto_prices[i] = round(self._crypto_prices[i], 2)

        # 1 spare RNG call for determinism.
        _unused = rng.random()

        # Process any transactions that have occurred by this timestamp.
        current = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        while self._tx_index < len(self._transactions):
            tx_time, tx_data = self._transactions[self._tx_index]
            if tx_time <= current:
                self._active_transactions.append(tx_data)
                self._account_balance += tx_data["amount"]  # type: ignore[operator]
                self._total_spent_today += abs(tx_data["amount"])  # type: ignore[arg-type]
                self._tx_index += 1
            else:
                break

        # Last 3 transactions.
        last_3 = self._active_transactions[-3:]

        # Stock watchlist snapshot.
        stock_watchlist = [
            {"symbol": sym, "price": price}
            for (sym, _base), price in zip(_STOCK_WATCHLIST, self._stock_prices, strict=True)
        ]

        # Crypto snapshot.
        crypto_prices = [
            {"symbol": sym, "price": price}
            for (sym, _base), price in zip(_CRYPTO_WATCHLIST, self._crypto_prices, strict=True)
        ]

        # Spending vs budget.
        total_month = _PRIOR_MONTH_SPENDING + self._total_spent_today
        pct = total_month / _MONTHLY_BUDGET * 100
        spending_vs_budget = (
            f"${total_month:,.0f} of ${_MONTHLY_BUDGET:,.0f} monthly budget ({pct:.0f}%)"
        )

        return {
            "last_3_transactions": last_3,
            "account_balance": round(self._account_balance, 2),
            "pending_charges": list(_PENDING_CHARGES),
            "stock_watchlist": stock_watchlist,
            "crypto_prices": crypto_prices,
            "spending_vs_budget": spending_vs_budget,
        }

    def _init_once(self, schedule: PersonSchedule) -> None:
        """Build transaction list anchored to scenario_date."""
        d = schedule.scenario_date

        self._stock_prices = [base for _sym, base in _STOCK_WATCHLIST]
        self._crypto_prices = [base for _sym, base in _CRYPTO_WATCHLIST]

        transactions: list[tuple[datetime, dict[str, object]]] = []
        for time_str, counterparty, amount, category in _RAW_TRANSACTIONS:
            t = _parse_time(time_str)
            dt = datetime.combine(d, t, tzinfo=UTC)
            transactions.append(
                (
                    dt,
                    {
                        "counterparty": counterparty,
                        "amount": amount,
                        "category": category,
                    },
                )
            )
        self._transactions = transactions
