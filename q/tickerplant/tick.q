/ Compact tickerplant.
/ Receives rows, appends them to an on-disk log, inserts into memory,
/ and publishes to subscribers. Analytics do not run in this process.
/
/ Start from the q/ directory, after creating data/tick:
/   q tickerplant/tick.q -p 5001

\d .u
tabs:`trade`quote`bookDelta`bookSnapshot`marketStatus`feedHealth`instrument
logh:0N
subs:()!()

init:{[path]
  logh::hopen hsym path;
  subs::tabs!{()} each tabs;
 };

upd:{[t;x]
  if[not t in tabs; '"unknown table"];
  if[not null logh; logh enlist (t;x)];
  t insert x;
  pub[t;x];
 };

pub:{[t;x]
  if[t in key subs;
    {[t;x;w] w(`upd;t;x)}[t;x] each subs t
  ];
 };

sub:{[t]
  if[not t in key subs; subs[t]:()];
  subs[t],:neg .z.w;
 };

.z.pg:{[m] value m};
.z.ps:{[m] value m};
.z.pc:{[h] subs::subs except\: neg h};
\d .

if[count .z.x;
  system "p ",.z.x 0;
  system "mkdir data/tick";
  .u.init[`:data/tick/ticklog];
  -1 "MarketStream tickerplant listening";
 ];
