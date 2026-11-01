/ Vectorised analytics over in-memory trade and quote tables.
/ Prices are ticks (long). VWAP is a fractional tick count, not a float price.
/ Volatility is the sample standard deviation of log returns. It is not annualised.

/ xbar buckets on the time column. Empty buckets do not appear.
ohlc:{[t;s;bucket]
  d:select time, price, qty from t where sym=s;
  select open:first price, high:max price, low:min price, close:last price,
    volume:sum qty, trades:count i, vwap:qty wavg price
    by time:bucket xbar time from d
 };

vwap:{[t;s]
  exec qty wavg price from t where sym=s
 };

volume:{[t;s] exec sum qty from t where sym=s};
tradeCount:{[t;s] exec count i from t where sym=s};

sessionRange:{[t;s]
  select high:max price, low:min price from t where sym=s
 };

/ Quote spread. Mid is the integer average only when bid+ask is even;
/ the basis-point figure uses a float mid so a one-tick spread is visible.
spreads:{[q;s]
  select time, spread:ask-bid, mid:0.5*bid+ask,
    bps:10000*(ask-bid)%0.5*bid+ask
    from q where sym=s, not null bid, not null ask
 };

/ Log returns of a close vector, then sample deviation of the last n returns.
logReturns:{[closes] log closes%prev closes};

rollingVol:{[closes;n]
  r:logReturns[closes];
  r:n#r where not null r;
  if[2>count r; :0n];
  dev r
 };

/ As-of join. Both tables must be sorted by time within sym.
tradeAtQuote:{[trades;quotes]
  aj[`sym`time; `sym`time xasc trades; `sym`time xasc quotes]
 };

/ Depth imbalance from a snapshot table of side/price/qty.
depthImbalance:{[snap;s]
  d:select qty by side from snap where sym=s;
  bid:exec qty from d where side=`bid;
  ask:exec qty from d where side=`ask;
  bid:0^first bid; ask:0^first ask;
  $[0=bid+ask; 0n; (bid-ask)%bid+ask]
 };

/ Small worked example used by the q test and the documentation.
/ Trades at 1000, 1200, 1100 ticks with quantities 100, 50, 50.
/ VWAP = (1000*100 + 1200*50 + 1100*50) % 200 = 1075 ticks.
exampleTrades:{[]
  ([] time:3#2026.06.02D14:30:00.000000000;
      sym:3#`ATHR;
      price:1000 1200 1100;
      qty:100 50 50)
 };
