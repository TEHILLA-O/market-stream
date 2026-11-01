# Performance

## Method

`benchmarks/run_benchmark.py` builds events with the production simulator, then times the feedhandler, the book applier, and an ATHR OHLC plus VWAP pass. The clock is `time.perf_counter`. Rates are events divided by that elapsed time. No network and no browser are included.

Machine: Intel Core i7-9750H at 2.60 GHz, 32 GB RAM, Windows, Python 3.12, one process. Seed 1, five symbols.

| events | generate evt/s | feed evt/s | book apply evt/s | ATHR 5s bars |
| ---: | ---: | ---: | ---: | ---: |
| 10,000 | 25,188 | 38,837 | 153,336 | 23 |
| 100,000 | 18,325 | 27,755 | 142,429 | 224 |
| 1,000,000 | 22,320 | 29,324 | 343,309 | 2,226 |

Measured in one run of `benchmarks/run_benchmark.py` on 1 November 2026. An earlier partial run on the same machine, while other processes were busy, recorded 16,439 and 22,197 generate events/s for 10,000 and 100,000 events. The table above is the complete three-size run. These numbers will move with power settings and other processes. They are not a claim about kdb+, and they are not microsecond exchange latency.

### Second machine

The same script on an 8 vCPU Intel Xeon cloud VM, Linux, Python 3.12, also on 1 November 2026, one run:

| events | generate evt/s | feed evt/s | book apply evt/s | ATHR 5s bars |
| ---: | ---: | ---: | ---: | ---: |
| 10,000 | 197,944 | 233,432 | 1,706,759 | 23 |
| 100,000 | 192,109 | 171,654 | 1,353,057 | 224 |
| 1,000,000 | 137,472 | 139,154 | 1,604,447 | 2,226 |

These are several times higher than the laptop figures. The reason has not been investigated (operating system, power settings and background load are all candidates), so do not read the two tables as a like for like comparison.

## Python and q on the same arithmetic

`benchmarks/compare_python.py` repeats a 10,000-point VWAP and a sample deviation of log returns 200 times. Python took 5,745 ms for that loop. `q` is not on PATH, so `benchmarks/compare_calc.q` was not executed and there is no q timing. The script prints `q_available=0` in that case.

The in-process feedhandler latency shown in Systems is the same style of measurement: batch time divided by events in the batch, reported as p50, p95, and p99 in milliseconds. The payload says `not_exchange_latency: true`.

## What was not measured

- A q tickerplant ingest rate. No q binary was available, so the comparison script records Python only.
- Browser frame time. The workstation throttles socket applies to the server frame (about 10 Hz) and virtualises the tape. That is a design choice, not a profiled frame budget.

## Hot path choices

The simulator keeps integer mids and emits pydantic models at the boundary. The book uses dicts of price to size. Analytics for the live frame are cached once per pulse rather than once per socket message. The session log flushes in batches of 40 so the disk is not on the per-event critical path. None of that is a substitute for a tickerplant once q is actually running.
