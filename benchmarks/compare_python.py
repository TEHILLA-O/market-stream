"""Time the same VWAP and log-return deviation in Python and, when present, q.

The q number is printed only if `q compare_calc.q` actually runs.
A missing binary is reported as unavailable. It is not given a made-up time.
"""

from __future__ import annotations

import math
import shutil
import subprocess
import time
from pathlib import Path

PRICES = [1000 + (i % 50) for i in range(10_000)]
QTYS = [1 + (i % 7) for i in range(10_000)]
REPEATS = 200


def vwap(prices: list[int], qtys: list[int]) -> float:
    total = 0
    weight = 0
    for price, qty in zip(prices, qtys, strict=True):
        total += price * qty
        weight += qty
    return total / weight


def log_deviation(prices: list[int]) -> float:
    returns = [math.log(current / previous) for previous, current in zip(prices, prices[1:], strict=False)]
    mean = sum(returns) / len(returns)
    variance = sum((item - mean) ** 2 for item in returns) / (len(returns) - 1)
    return math.sqrt(variance)


def time_python() -> tuple[float, float]:
    started = time.perf_counter()
    result = 0.0
    for _ in range(REPEATS):
        result = vwap(PRICES, QTYS)
        log_deviation(PRICES)
    elapsed_ms = (time.perf_counter() - started) * 1000
    return result, elapsed_ms


def time_q() -> str | None:
    binary = shutil.which("q")
    if binary is None:
        return None
    script = Path(__file__).with_name("compare_calc.q")
    completed = subprocess.run(
        [binary, str(script)],
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
    )
    if completed.returncode != 0:
        return f"q exited {completed.returncode}: {completed.stderr.strip() or completed.stdout.strip()}"
    return completed.stdout.strip().splitlines()[-1]


def main() -> None:
    result, elapsed = time_python()
    print(f"python vwap={result:.2f} ms={elapsed:.1f} repeats={REPEATS} prices={len(PRICES)}")
    q_line = time_q()
    if q_line is None:
        print("q_available=0 reason=q is not on PATH")
    else:
        print(q_line)


if __name__ == "__main__":
    main()
