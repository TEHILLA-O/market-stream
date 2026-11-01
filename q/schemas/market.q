/ MarketStream table schemas.
/ Prices are integer ticks. Quantities are integer lots.
/ Times are timestamps (nanoseconds). Symbols are interned symbols.
/ `g# on sym keeps instrument scans contiguous after a bulk load.
/ The tickerplant itself does not sort or attribute on the hot path.

marketSchema:{[]
  trade:([
    ] time:`timestamp$(); sym:`symbol$(); seq:`long$();
      price:`long$(); qty:`long$(); aggressor:`symbol$();
      venue:`symbol$(); session:`symbol$(); tradeId:`symbol$());
  quote:([
    ] time:`timestamp$(); sym:`symbol$(); seq:`long$();
      bid:`long$(); ask:`long$(); bidQty:`long$(); askQty:`long$();
      venue:`symbol$(); session:`symbol$());
  bookDelta:([
    ] time:`timestamp$(); sym:`symbol$(); seq:`long$();
      side:`symbol$(); price:`long$(); qty:`long$(); action:`symbol$();
      venue:`symbol$(); session:`symbol$());
  bookSnapshot:([
    ] time:`timestamp$(); sym:`symbol$(); seq:`long$();
      side:`symbol$(); price:`long$(); qty:`long$();
      venue:`symbol$(); session:`symbol$());
  marketStatus:([
    ] time:`timestamp$(); sym:`symbol$(); seq:`long$();
      status:`symbol$(); regime:`symbol$(); reason:();
      venue:`symbol$(); session:`symbol$());
  feedHealth:([
    ] time:`timestamp$(); sym:`symbol$(); seq:`long$();
      quality:`symbol$(); detail:(); venue:`symbol$(); session:`symbol$());
  instrument:([
    sym:`symbol$()] assetClass:`symbol$(); ccy:`symbol$();
      tickSize:`float$(); lotSize:`float$(); venue:`symbol$(); refPrice:`float$());
  `trade`quote`bookDelta`bookSnapshot`marketStatus`feedHealth`instrument
 };

/ Apply grouped attribute after a replay or end-of-session load, not per insert.
attributeSym:{[names]
  {[n] if[count value n; n set @[`sym xasc value n;`sym;`g#]]} each names
 };
