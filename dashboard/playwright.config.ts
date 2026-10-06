import { defineConfig } from "@playwright/test";
export default defineConfig({
  testDir: "tests/browser",
  outputDir: "../reports/browser",
  use: {
    baseURL: process.env.DASHBOARD_TEST_URL || "http://127.0.0.1:18788",
    headless: true,
  },
  workers: 1,
});
