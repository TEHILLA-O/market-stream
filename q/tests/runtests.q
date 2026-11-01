/ Executable checks. Run with: q tests/runtests.q
/ Exits 1 on the first failed assertion so a shell can see the result.

\l ../analytics/analytics.q
\l ../orderbook/book.q

failures:0
pass:{[name] -1 "PASS ",name}
fail:{[name;detail] failures+:1; -2 "FAIL ",name," ",detail}

expect:{[name;cond;detail] $[cond; pass name; fail[name;detail]]}

t:exampleTrades[]
expect["vwap"; 1075=vwap[t;`ATHR]; "expected 1075 ticks"]
bar:ohlc[t;`ATHR;0D00:01:00]
expect["ohlc open"; 1000=first exec open from bar; ""]
expect["ohlc high"; 1200=first exec high from bar; ""]
expect["ohlc low"; 1000=first exec low from bar; ""]
expect["ohlc close"; 1100=first exec close from bar; ""]
expect["ohlc volume"; 200=first exec volume from bar; ""]

.book.applySnap[`ATHR;1; (100 99)!(10 8); (102 103)!(7 9)]
.book.applyDelta[`ATHR;2;`bid;100;15]
.book.applyDelta[`ATHR;3;`ask;102;0]
v:.book.view[`ATHR]
expect["book bid"; 100=v`bid; ""]
expect["book ask"; 103=v`ask; ""]
expect["book spread"; 3=v`spread; ""]
expect["book live"; not v`stale; ""]
gap:.book.applyDelta[`ATHR;6;`bid;100;4]
expect["gap quarantined"; gap=`quarantine; ""]
expect["stale after gap"; .book.view[`ATHR]`stale; ""]

-1 "failures ",string failures
exit failures
