import { defineConfig } from "@playwright/test";

const python = process.platform === "win32" ? ".venv\\Scripts\\python.exe" : "python3";

export default defineConfig({
  testDir: "./tests",
  timeout: 60_000,
  expect: { timeout: 20_000 },
  use: {
    baseURL: "http://127.0.0.1:5199",
    channel: process.env.CI ? undefined : "msedge",
  },
  webServer: [
    {
      command: `${python} -m marketstream`,
      cwd: "..",
      env: {
        ...process.env,
        MARKETSTREAM_PORT: "8791",
        MARKETSTREAM_HOST: "127.0.0.1",
        MARKETSTREAM_DATA_DIR: "data/playwright",
        MARKETSTREAM_WARMUP_PULSES: "8",
        MARKETSTREAM_BUILD_DEMOS: "true",
        MARKETSTREAM_Q_ENABLED: "false",
        MARKETSTREAM_SPEED: "8",
      },
      url: "http://127.0.0.1:8791/healthz",
      reuseExistingServer: false,
      timeout: 120_000,
    },
    {
      command: "node ./node_modules/vite/bin/vite.js --host 127.0.0.1 --port 5199",
      env: { ...process.env, MARKETSTREAM_API: "http://127.0.0.1:8791" },
      url: "http://127.0.0.1:5199",
      reuseExistingServer: false,
      timeout: 120_000,
    },
  ],
});
