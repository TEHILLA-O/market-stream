/ Curated queries. Load the RDB first so trade and quote exist.
/ These names are the only expressions the API is allowed to request.

.ms.q.latest:{[] select last price, last time by sym from trade};
.ms.q.ohlc:{[s;bucket] ohlc[trade;s;bucket]};
.ms.q.vwap:{[s] vwap[trade;s]};
.ms.q.range:{[s] sessionRange[trade;s]};
.ms.q.spread:{[s] select from spreads[quote;s] where i>count[i]-50};
.ms.q.asof:{[s]
  tradeAtQuote[
    select from trade where sym=s;
    select time, sym, bid, ask from quote where sym=s]
 };
.ms.q.vol:{[s]
  closes:exec close from ohlc[trade;s;0D00:00:05];
  rollingVol[closes;20]
 };
