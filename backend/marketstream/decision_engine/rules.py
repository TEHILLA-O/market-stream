"""Transparent rule evaluations.

A trigger is a statement about current measurements and configured
thresholds. It is not a prediction that a trade will make money.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal


RULES = {
    "spread_widening": {"version": "1.0.0", "default_bps": Decimal("8")},
    "liquidity_imbalance": {"version": "1.0.0", "default_ratio": Decimal("0.45")},
    "volatility_spike": {"version": "1.0.0", "default_multiple": Decimal("2.0")},
    "vwap_deviation": {"version": "1.0.0", "default_bps": Decimal("25")},
    "momentum": {"version": "1.0.0", "default_bps": Decimal("8")},
}


@dataclass
class Decision:
    rule_id: str
    rule_version: str
    symbol: str
    timestamp: datetime
    inputs: dict
    thresholds: dict
    result: str
    explanation: str

    def to_public(self) -> dict:
        return {
            "rule_id": self.rule_id,
            "rule_version": self.rule_version,
            "symbol": self.symbol,
            "timestamp": self.timestamp.isoformat(),
            "inputs": self.inputs,
            "thresholds": self.thresholds,
            "result": self.result,
            "explanation": self.explanation,
            "predictive": False,
        }


class DecisionEngine:
    def __init__(self) -> None:
        self.history: deque[Decision] = deque(maxlen=400)
        self.baselines: dict[str, Decimal] = {}

    def evaluate(self, symbol: str, stats: dict, now: datetime) -> list[Decision]:
        decisions = [
            self._spread(symbol, stats, now),
            self._imbalance(symbol, stats, now),
            self._volatility(symbol, stats, now),
            self._vwap(symbol, stats, now),
            self._momentum(symbol, stats, now),
        ]
        kept = [item for item in decisions if item is not None]
        self.history.extend(kept)
        return kept

    def summarise(self, symbol: str | None = None) -> dict:
        rows = [item for item in self.history if symbol is None or item.symbol == symbol]
        triggers = [item for item in rows if item.result == "trigger"]
        return {
            "evaluations": len(rows),
            "triggers": len(triggers),
            "note": (
                "Trigger counts describe how often a rule matched its threshold "
                "on this synthetic sample. They are not a forecast of profit."
            ),
            "recent": [item.to_public() for item in list(rows)[-12:]],
        }

    def _spread(self, symbol: str, stats: dict, now: datetime) -> Decision | None:
        value = _dec(stats.get("spread_bps"))
        if value is None:
            return None
        threshold = RULES["spread_widening"]["default_bps"]
        triggered = value > threshold
        return self._make(
            "spread_widening",
            symbol,
            now,
            {"spread_bps": str(value)},
            {"spread_bps": str(threshold)},
            triggered,
            f"Spread is {value:.2f} bps. Threshold is {threshold:.2f} bps.",
        )

    def _imbalance(self, symbol: str, stats: dict, now: datetime) -> Decision | None:
        value = _dec(stats.get("imbalance"))
        if value is None:
            return None
        threshold = RULES["liquidity_imbalance"]["default_ratio"]
        triggered = abs(value) > threshold
        return self._make(
            "liquidity_imbalance",
            symbol,
            now,
            {"imbalance": str(value)},
            {"absolute_imbalance": str(threshold)},
            triggered,
            f"Depth imbalance is {value:.2f}. Absolute threshold is {threshold:.2f}.",
        )

    def _volatility(self, symbol: str, stats: dict, now: datetime) -> Decision | None:
        current = _dec(stats.get("volatility"))
        if current is None:
            return None
        baseline = self.baselines.get(symbol)
        if baseline is None:
            self.baselines[symbol] = current
            baseline = current
        else:
            self.baselines[symbol] = (baseline * Decimal("0.95")) + (current * Decimal("0.05"))
        multiple = RULES["volatility_spike"]["default_multiple"]
        floor = baseline if baseline > 0 else current
        triggered = floor > 0 and current > floor * multiple
        return self._make(
            "volatility_spike",
            symbol,
            now,
            {"rolling_stdev": str(current), "baseline": str(floor)},
            {"multiple": str(multiple)},
            triggered,
            f"Rolling stdev {current:.6f} versus baseline {floor:.6f}. Spike multiple is {multiple}.",
        )

    def _vwap(self, symbol: str, stats: dict, now: datetime) -> Decision | None:
        last = _dec(stats.get("last"))
        vwap = _dec(stats.get("vwap"))
        if last is None or vwap is None or vwap == 0:
            return None
        deviation_bps = (last - vwap) / vwap * Decimal(10000)
        threshold = RULES["vwap_deviation"]["default_bps"]
        triggered = abs(deviation_bps) > threshold
        return self._make(
            "vwap_deviation",
            symbol,
            now,
            {"last": str(last), "vwap": str(vwap), "deviation_bps": f"{deviation_bps:.2f}"},
            {"absolute_deviation_bps": str(threshold)},
            triggered,
            f"Last is {deviation_bps:.2f} bps from session VWAP. Threshold is {threshold:.2f} bps.",
        )

    def _momentum(self, symbol: str, stats: dict, now: datetime) -> Decision | None:
        short = _dec(stats.get("return_short_bps"))
        long = _dec(stats.get("return_long_bps"))
        if short is None or long is None:
            return None
        gap = short - long
        threshold = RULES["momentum"]["default_bps"]
        triggered = abs(gap) > threshold
        return self._make(
            "momentum",
            symbol,
            now,
            {"short_return_bps": str(short), "long_return_bps": str(long), "gap_bps": f"{gap:.2f}"},
            {"absolute_gap_bps": str(threshold)},
            triggered,
            f"Short minus long return is {gap:.2f} bps. Threshold is {threshold:.2f} bps.",
        )

    def _make(
        self,
        rule_id: str,
        symbol: str,
        now: datetime,
        inputs: dict,
        thresholds: dict,
        triggered: bool,
        explanation: str,
    ) -> Decision:
        return Decision(
            rule_id=rule_id,
            rule_version=str(RULES[rule_id]["version"]),
            symbol=symbol,
            timestamp=now,
            inputs=inputs,
            thresholds=thresholds,
            result="trigger" if triggered else "clear",
            explanation=explanation,
        )


def _dec(value) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except Exception:
        return None
