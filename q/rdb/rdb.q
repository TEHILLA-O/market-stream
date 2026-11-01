/ Real-time database.
/ Subscribes to the tickerplant, keeps the current session, and can
/ replay a tickerplant log after a restart. Analytics are functions
/ over these tables. They are not called from the update hook.

/ Load from the q/ directory: q rdb/rdb.q
\l schemas/market.q
\l analytics/analytics.q
\l hdb/hdb.q

marketSchema[]

/ Replay an append-only tickerplant log into the RDB.
replayLog:{[path]
  msgs:get hsym `$path;
  {[m] .[upsert;(m 0;m 1)]} each msgs;
  attributeSym[`trade`quote`bookDelta`bookSnapshot];
 };

/ Latest trade per symbol. `select by sym` keeps the last row.
latestTrade:{[] select by sym from trade};
latestQuote:{[] select by sym from quote};

/ Intraday window. `within` is inclusive.
tradesBetween:{[s;a;b] select from trade where sym=s, time within (a;b)};

/ End of session: the caller passes a date partition root.
endOfDay:{[root;dt]
  .ms.hdb.save[root;dt;`trade;trade];
  .ms.hdb.save[root;dt;`quote;quote];
  delete from `trade;
  delete from `quote;
  delete from `bookDelta;
  delete from `bookSnapshot;
 };
