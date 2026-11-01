import { expect, test } from "@playwright/test";

test.beforeEach(async ({ page }) => {
  await page.goto("/", { waitUntil: "domcontentloaded" });
});

test("switches workspaces from the ribbon and keeps the command ribbon", async ({ page }) => {
  await expect(page.getByText("MarketStream").first()).toBeVisible();
  await expect(page.locator("aside.sidebar, nav.sidebar")).toHaveCount(0);
  const workspaces = page.getByRole("navigation", { name: "Workspaces" });
  await workspaces.getByRole("button", { name: "Depth", exact: true }).click();
  await expect(page.getByText("Gaps")).toBeVisible();
  await workspaces.getByRole("button", { name: "Tape", exact: true }).click();
  await expect(page.getByRole("button", { name: "Export CSV" })).toBeVisible();
  await workspaces.getByRole("button", { name: "Systems", exact: true }).click();
  await expect(page.getByText("tickerplant")).toBeVisible();
  await expect(page.getByText("PYTHON REF", { exact: true })).toBeVisible();
});

test("searches for an instrument and opens the command palette", async ({ page }) => {
  await page.getByLabel("Search instruments").fill("brdl");
  await page.getByRole("listbox").getByRole("button", { name: /BRDL/ }).click();
  await expect(page.locator(".dock").getByRole("button", { name: /BRDL/ })).toHaveAttribute("data-active", "true");
  await page.keyboard.press("Control+k");
  await expect(page.getByRole("dialog", { name: "Command palette" })).toBeVisible();
  await page.getByPlaceholder("Instruments, workspaces, simulation").fill("Reset panel");
  await page.getByRole("button", { name: /Reset panel layout/ }).click();
  await expect(page.getByRole("dialog", { name: "Command palette" })).toHaveCount(0);
});

test("shows a chart and can collapse a panel", async ({ page }) => {
  await expect(page.locator(".chart canvas").first()).toBeVisible();
  await page.getByRole("button", { name: "Collapse tape" }).click();
  await expect(page.getByTestId("panel-tape")).toHaveAttribute("data-collapsed", "true");
  await page.reload();
  await expect(page.getByTestId("panel-tape")).toHaveAttribute("data-collapsed", "true");
  await page.getByRole("button", { name: "Open tape" }).click();
  await expect(page.getByTestId("panel-tape")).toHaveAttribute("data-collapsed", "false");
});

test("rejects an oversized paper order with the named rule", async ({ page }) => {
  const loaded = page.waitForResponse(
    (response) => response.url().includes("/api/v1/orders") && response.request().method() === "GET" && response.ok(),
    { timeout: 15_000 },
  );
  await page.getByRole("navigation", { name: "Workspaces" }).getByRole("button", { name: "Execution", exact: true }).click();
  await loaded;
  await expect(page.locator(".pane-b tbody tr, .empty-note").first()).toBeVisible();
  const rejected = page.getByRole("cell", { name: /rejected · max_order_quantity/ });
  const before = await rejected.count();
  await page.getByLabel("Quantity (lots)").fill("5000");
  await expect(page.locator(".ticket .reject").getByText(/max_order_quantity/)).toBeVisible();
  const posted = page.waitForResponse(
    (response) => new URL(response.url()).pathname === "/api/v1/orders" && response.request().method() === "POST",
    { timeout: 15_000 },
  );
  await page.getByRole("button", { name: "Simulate buy" }).click();
  const body = await (await posted).json();
  expect(body.reject_rule).toBe("max_order_quantity");
  await expect(rejected).toHaveCount(before + 1);
});

test("marks the book stale after a sequence gap and recovers", async ({ page, request }) => {
  await request.post("http://127.0.0.1:8791/api/v1/simulation/speed", { data: { speed: 0.25 } });
  await request.post("http://127.0.0.1:8791/api/v1/simulation/gap");
  const book = page.getByTestId("book-state");
  await expect(book).toHaveText("stale", { timeout: 12_000 });
  await expect(book).toHaveText("live", { timeout: 15_000 });
  await request.post("http://127.0.0.1:8791/api/v1/simulation/speed", { data: { speed: 4 } });
});

test("loads a recorded session in replay without touching the live blotter", async ({ page }) => {
  await page.getByRole("navigation", { name: "Workspaces" }).getByRole("button", { name: "Replay", exact: true }).click();
  const session = page.getByLabel("Session");
  await expect(session.locator("option[value='demo-calm']")).toHaveCount(1);
  const loaded = page.waitForResponse(
    (response) => response.url().includes("/api/v1/replay/load") && response.ok(),
  );
  await session.selectOption("demo-calm");
  await loaded;
  await expect(page.getByText("Ledger untouched.")).toBeVisible();
  await page.getByRole("button", { name: "Step", exact: true }).click();
  await expect(page.getByLabel("Playback speed")).toBeVisible();
  await page.getByLabel("Jump to time").fill("14:30:10");
  await page.getByRole("button", { name: "Jump" }).click();
  await expect(page.getByText("Playhead risk")).toBeVisible();
});

test("reconnects after the market socket is dropped", async ({ page }) => {
  await page.addInitScript(() => {
    const native = window.WebSocket;
    const sockets: WebSocket[] = [];
    const wrapped = function (this: WebSocket, url: string | URL, protocols?: string | string[]) {
      const socket = protocols === undefined ? new native(url) : new native(url, protocols);
      if (String(url).includes("/ws/v1/market")) sockets.push(socket);
      (window as unknown as { __marketSockets: WebSocket[] }).__marketSockets = sockets;
      return socket;
    } as unknown as typeof WebSocket;
    wrapped.prototype = native.prototype;
    wrapped.CONNECTING = native.CONNECTING;
    wrapped.OPEN = native.OPEN;
    wrapped.CLOSING = native.CLOSING;
    wrapped.CLOSED = native.CLOSED;
    window.WebSocket = wrapped;
  });
  await page.reload({ waitUntil: "domcontentloaded" });
  const health = page.locator(".health");
  await expect(health).toContainText("live");
  await page.evaluate(() => {
    const target = document.querySelector(".health");
    const seen: string[] = [];
    (window as unknown as { __health: string[] }).__health = seen;
    if (!target) return;
    const read = () => (target.textContent || "").trim();
    seen.push(read());
    const observer = new MutationObserver(() => seen.push(read()));
    observer.observe(target, { subtree: true, characterData: true, childList: true });
    const sockets = (window as unknown as { __marketSockets?: WebSocket[] }).__marketSockets ?? [];
    for (const socket of sockets) {
      if (socket.readyState === WebSocket.OPEN) socket.close();
    }
  });
  await expect.poll(async () => page.evaluate(() => (window as unknown as { __health: string[] }).__health.join(" | "))).toContain("reconnecting");
  await expect(health).toContainText("live");
});
