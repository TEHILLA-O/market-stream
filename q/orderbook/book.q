/ Market-by-price book in q.
/ Absolute quantities. A zero quantity deletes a level.
/ A sequence gap sets stale. Deltas are ignored until a snapshot arrives.
/ This does not invent order ids.

\d .book
state:()!()

empty:{[s]
  state[s]:`bids`asks`seq`stale`gaps!(()!();()!();0N;0b;0)
 };

ensure:{[s] if[not s in key state; empty s]};

bestBid:{[s] b:state[s]`bids; $[count b; max key b; 0N]};
bestAsk:{[s] a:state[s]`asks; $[count a; min key a; 0N]};

applySnap:{[s;seq;bids;asks]
  ensure s;
  state[s;`bids]:bids;
  state[s;`asks]:asks;
  state[s;`seq]:seq;
  state[s;`stale]:0b;
 };

/ bids and asks are dictionaries of price -> quantity.
applyDelta:{[s;seq;side;price;qty]
  ensure s;
  st:state s;
  if[not null st`seq; if[seq<=st`seq; :`duplicate]];
  if[not null st`seq; if[seq>1+st`seq; state[s;`stale]:1b; state[s;`gaps]+:1]];
  if[state[s]`stale; :`quarantine];
  dict:$[side=`bid; `bids; `asks];
  book:st dict;
  book:$[qty=0; enlist[price]_book; book,enlist[price]!enlist qty];
  state[s;dict]:book;
  state[s;`seq]:seq;
  `applied
 };

view:{[s]
  ensure s;
  bb:bestBid s; ba:bestAsk s;
  `sym`bid`ask`spread`stale`seq!(s;bb;ba;$[null bb;0N;null ba;0N;ba-bb];state[s]`stale;state[s]`seq)
 };
\d .
