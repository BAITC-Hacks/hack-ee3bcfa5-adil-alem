import { defineConfig } from "@playwright/test";
export default defineConfig({
  testDir: "./tests", fullyParallel: false, workers: 1,
  use: { baseURL: "http://localhost:3000", channel: "chrome", headless: true, viewport: { width: 1440, height: 1050 } },
  webServer: [
    { command: process.platform === "win32" ? "..\\backend\\.venv\\Scripts\\python.exe tests/serve_backend.py" : "../backend/.venv/bin/python tests/serve_backend.py", url: "http://127.0.0.1:8000/health", reuseExistingServer: false, timeout: 30000 },
    { command: "npm run start -- --hostname 127.0.0.1", url: "http://localhost:3000", reuseExistingServer: false, timeout: 60000 },
  ],
});
