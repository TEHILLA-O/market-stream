/ Same arithmetic as benchmarks/compare_python.py.
/ 10,000 prices and quantities, 200 repetitions of VWAP and sample deviation of log returns.
/ Prints one line the Python harness can parse. This file does not start a listener.

prices:1000+til[10000] mod 50
qtys:1+til[10000] mod 7
vwap:{[p;q] q wavg p}
vol:{[p]
  r:log (1_ p)%-1_ p
  dev r
 }
st:.z.p
do[200; (vwap[prices;qtys]; vol[prices])]
en:.z.p
result:qtys wavg prices
-1 "q_available=1 vwap=",string[result]," ms=",string[`long$(en-st)%1000000]
exit 0
