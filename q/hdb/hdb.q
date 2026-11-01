/ Session partitions.
/ One directory per virtual session date: hdb/YYYY.MM.DD/trade/
/ Loading with \l reassembles the partition when q is started from the root.
/ This script can also save a single table without requiring a running RDB.

\d .ms
hdb.save:{[root;dt;name;data]
  part:hsym `$":",root,"/",string[dt],"/",string[name],"/";
  part set .Q.en[hsym `$root;0!data];
 };

hdb.loadDay:{[root;dt;name]
  get hsym `$":",root,"/",string[dt],"/",string[name],"/"
 };

/ Compare two sessions by symbol volume. Both arguments are trade tables.
hdb.compareVolume:{[a;b]
  av:select volumeA:sum qty by sym from a;
  bv:select volumeB:sum qty by sym from b;
  av lj bv
 };
\d .
