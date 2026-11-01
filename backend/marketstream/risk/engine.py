"""Exposure, limits, drawdown, and a clearly bounded historical VaR.

VaR here is a historical simulation on recent synthetic mid returns.
It is a teaching analytic. It is not a regulatory or desk risk number:
the sample is short, the market is simulated, shocks are linear, and
there is no volatility scaling or liquidity adjustment.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from math import sqrt

from marketstream.core.instruments import Instrument
from marketstream.core.models import OrderRequest
from marketstream.core.money import format_decimal, notional


@dataclass
class RiskLimits:
    max_position_lots: int = 5000
    max_gross_exposure: Decimal = Decimal("2000000")
    max_net_exposure: Decimal = Decimal("1500000")
    max_symbol_concentration: Decimal = Decimal("0.40")
    daily_loss: Decimal = Decimal("25000")
    max_order_notional: Decimal = Decimal("250000")
    max_order_lots: int = 2000
    drawdown_alert: Decimal = Decimal("10000")
    capital_base: Decimal = Decimal("1000000")

    def to_public(self) -> dict:
        return {
            "max_position_lots": self.max_position_lots,
            "max_gross_exposure": format_decimal(self.max_gross_exposure, 2),
            "max_net_exposure": format_decimal(self.max_net_exposure, 2),
            "max_symbol_concentration": format_decimal(self.max_symbol_concentration, 4),
            "daily_loss": format_decimal(self.daily_loss, 2),
            "max_order_notional": format_decimal(self.max_order_notional, 2),
            "max_order_lots": self.max_order_lots,
            "drawdown_alert": format_decimal(self.drawdown_alert, 2),
            "capital_base": format_decimal(self.capital_base, 2),
        }


@dataclass
class RiskEngine:
    limits: RiskLimits = field(default_factory=RiskLimits)
    equity_curve: deque = field(default_factory=lambda: deque(maxlen=2000))
    alerts: deque = field(default_factory=lambda: deque(maxlen=200))
    returns: dict[str, deque] = field(default_factory=dict)
    last_mid: dict[str, Decimal] = field(default_factory=dict)
    alert_seq: int = 0

    def check_order(
        self,
        request: OrderRequest,
        instrument: Instrument,
        reference_ticks: int | None,
        positions: dict[str, int],
        exposures: dict[str, Decimal],
        net_pnl: Decimal,
    ) -> tuple[str | None, str | None]:
        if request.quantity_lots > self.limits.max_order_lots:
            return "max_order_quantity", (
                f"order quantity {request.quantity_lots} lots exceeds {self.limits.max_order_lots}"
            )
        if reference_ticks is None:
            return "stale_mark", "no reference price for pre-trade notional"
        order_notion = notional(request.quantity_lots, reference_ticks, instrument)
        if order_notion > self.limits.max_order_notional:
            return "max_order_notional", (
                f"order notional {order_notion:.2f} exceeds {self.limits.max_order_notional:.2f}"
            )
        signed = request.quantity_lots if request.side == "buy" else -request.quantity_lots
        projected = positions.get(request.symbol, 0) + signed
        if abs(projected) > self.limits.max_position_lots:
            return "max_position_size", (
                f"projected position {projected} lots exceeds {self.limits.max_position_lots}"
            )
        signed_notion = order_notion if request.side == "buy" else -order_notion
        projected_symbol = exposures.get(request.symbol, Decimal("0")) + signed_notion
        gross = Decimal("0")
        net = Decimal("0")
        for symbol, exposure in exposures.items():
            value = projected_symbol if symbol == request.symbol else exposure
            gross += abs(value)
            net += value
        if request.symbol not in exposures:
            gross += abs(projected_symbol)
            net += projected_symbol
        if gross > self.limits.max_gross_exposure:
            return "max_gross_exposure", f"projected gross exposure {gross:.2f} exceeds limit"
        if abs(net) > self.limits.max_net_exposure:
            return "max_net_exposure", f"projected net exposure {net:.2f} exceeds limit"
        if self.limits.capital_base > 0:
            concentration = abs(projected_symbol) / self.limits.capital_base
            if concentration > self.limits.max_symbol_concentration:
                return "max_symbol_concentration", (
                    f"{request.symbol} would be {concentration:.1%} of capital, "
                    f"limit is {self.limits.max_symbol_concentration:.1%}"
                )
        if net_pnl < -self.limits.daily_loss:
            return "daily_loss_threshold", f"net P&L {net_pnl:.2f} is past the daily loss threshold"
        return None, None

    def sample_return(self, symbol: str, mid: Decimal | None) -> None:
        if mid is None or mid <= 0:
            return
        previous = self.last_mid.get(symbol)
        self.last_mid[symbol] = mid
        if previous is None or previous <= 0:
            return
        change = (mid - previous) / previous
        self.returns.setdefault(symbol, deque(maxlen=300)).append(change)

    def sample_equity(self, equity: Decimal, now: datetime) -> None:
        self.equity_curve.append({"time": now.isoformat(), "equity": format_decimal(equity, 2)})

    def drawdown(self) -> dict:
        if not self.equity_curve:
            return {"peak": None, "trough": None, "drawdown": "0.00", "peak_to_trough": "0.00"}
        values = [Decimal(point["equity"]) for point in self.equity_curve]
        peak = values[0]
        worst = Decimal("0")
        trough = values[0]
        peak_at = values[0]
        for value in values:
            if value > peak:
                peak = value
            drop = peak - value
            if drop > worst:
                worst = drop
                trough = value
                peak_at = peak
        return {
            "peak": format_decimal(peak_at, 2),
            "trough": format_decimal(trough, 2),
            "drawdown": format_decimal(worst, 2),
            "peak_to_trough": format_decimal(worst, 2),
        }

    def historical_var(self, notionals: dict[str, Decimal], confidence: Decimal = Decimal("0.95")) -> dict:
        """Sum of position notional times historical simple returns, per sample index.

        The window is whatever overlapping return history each symbol has.
        Missing symbols contribute nothing for that observation. Confidence
        is the lower-tail empirical quantile of that simulated P&L.
        """

        series = {symbol: list(rows) for symbol, rows in self.returns.items() if symbol in notionals}
        if not series:
            return self._var_shell(confidence, 0, None)
        length = min(len(rows) for rows in series.values())
        if length < 20:
            return self._var_shell(confidence, length, None)
        pnl = []
        for index in range(length):
            sample = Decimal("0")
            for symbol, rows in series.items():
                sample += notionals[symbol] * Decimal(str(rows[-length + index]))
            pnl.append(sample)
        ordered = sorted(pnl)
        # For 95%, the loss quantile is the 5th percentile.
        tail = max(0, int((Decimal(1) - confidence) * len(ordered)) - 1)
        quantile = ordered[tail]
        losses = [-item for item in pnl if item < 0]
        mean = sum(pnl, Decimal("0")) / Decimal(len(pnl))
        variance = sum((item - mean) ** 2 for item in pnl) / Decimal(len(pnl) - 1)
        return {
            "method": "historical_simulation",
            "confidence": format_decimal(confidence, 2),
            "window": length,
            "frequency": "simulator pulse",
            "return_method": "simple mid-price return",
            "currency": "USD",
            "var": format_decimal(-quantile if quantile < 0 else Decimal("0"), 2),
            "observation_count": length,
            "loss_observations": len(losses),
            "sample_stdev": f"{sqrt(float(variance)):.6f}",
            "limitations": [
                "Synthetic prices, not exchange history.",
                "Linear exposure. Options and convexity are absent.",
                "No volatility scaling, decay, or liquidity horizon.",
                "A short window dominated by the current regime.",
                "Not sufficient for real-money risk management.",
            ],
        }

    def scenario(self, notionals: dict[str, Decimal]) -> list[dict]:
        shocks = [Decimal("-0.10"), Decimal("-0.05"), Decimal("-0.01"), Decimal("0.01"), Decimal("0.05"), Decimal("0.10")]
        rows = []
        for shock in shocks:
            pnl = sum((notionals[symbol] * shock for symbol in notionals), Decimal("0"))
            rows.append(
                {
                    "shock": format_decimal(shock * 100, 1) + "%",
                    "estimated_pnl": format_decimal(pnl, 2),
                    "method": "linear mark shock, all priced instruments, USD",
                }
            )
        return rows

    def raise_alert(self, kind: str, detail: str, now: datetime, symbol: str | None = None) -> dict | None:
        for existing in self.alerts:
            if existing["kind"] == kind and existing.get("symbol") == symbol and existing["detail"] == detail:
                return None
        self.alert_seq += 1
        alert = {
            "id": f"{kind}-{self.alert_seq}",
            "kind": kind,
            "symbol": symbol,
            "detail": detail,
            "timestamp": now.isoformat(),
            "simulated": True,
        }
        self.alerts.append(alert)
        return alert

    def _var_shell(self, confidence: Decimal, window: int, var: str | None) -> dict:
        return {
            "method": "historical_simulation",
            "confidence": format_decimal(confidence, 2),
            "window": window,
            "frequency": "simulator pulse",
            "return_method": "simple mid-price return",
            "currency": "USD",
            "var": var,
            "observation_count": window,
            "limitations": ["Not enough return history yet. At least 20 overlapping pulses are required."],
        }
