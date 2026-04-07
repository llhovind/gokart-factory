import { defineConfig } from '@playwright/test'

export default defineConfig({
  testDir: './tests',
  timeout: 30_000,
  retries: 0,
  use: {
    baseURL: 'http://localhost:5173',
    headless: true,
    // Clear localStorage between tests so each test gets a fresh tenant UUID
    storageState: { cookies: [], origins: [] },
  },
  webServer: [
    {
      command: 'rm -f /tmp/gokart_test.db && cd ../backend && SQLALCHEMY_DATABASE_URL="sqlite:////tmp/gokart_test.db" venv/bin/uvicorn app.main:app --port 8000',
      port: 8000,
      reuseExistingServer: true,
      timeout: 15_000,
    },
    {
      command: 'cd ../frontend && npm run dev',
      port: 5173,
      reuseExistingServer: true,
      timeout: 30_000,
    },
  ],
})
