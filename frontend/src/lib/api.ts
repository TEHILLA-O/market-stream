export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    ...init,
    headers: {
      "content-type": "application/json",
      ...(init?.headers ?? {}),
    },
  });
  if (!response.ok) {
    let detail = response.statusText;
    try {
      const body = await response.json();
      detail = body.detail ?? detail;
    } catch {
      /* keep the status text */
    }
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  return response.json() as Promise<T>;
}

export function tone(value?: string | null): string {
  if (value == null || value === "") return "flat";
  const numeric = Number(value);
  if (Number.isNaN(numeric) || numeric === 0) return "flat";
  return numeric > 0 ? "pos" : "neg";
}

export function clockLabel(iso?: string | null): string {
  if (!iso) return "—";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso.slice(11, 19);
  return date.toISOString().slice(11, 19);
}

export function csvTrades(rows: { event_timestamp: string; symbol: string; price: string; quantity: string; notional: string; aggressor_side: string; venue: string }[]): void {
  const header = "time,symbol,price,quantity,notional,aggressor,venue";
  const body = rows.map((row) =>
    [row.event_timestamp, row.symbol, row.price, row.quantity, row.notional, row.aggressor_side, row.venue].join(","),
  );
  const blob = new Blob([[header, ...body].join("\n")], { type: "text/csv" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = "marketstream-tape.csv";
  link.click();
  URL.revokeObjectURL(url);
}
