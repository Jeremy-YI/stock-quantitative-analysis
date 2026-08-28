import { defineConfig, devices } from '@playwright/test'
import path from 'node:path'

// 仓库根目录（本文件在 apps/web/ 下，向上两级即仓库根）
const repoRoot = path.resolve(__dirname, '..', '..')

// 演示数据 + 后端路径（E2E 用演示数据，无需真实 hsjday；先跑 seed_demo_data.py）
const demoHsjday = path.join(repoRoot, 'data', 'demo_hsjday')
const apiSrc = path.join(repoRoot, 'apps', 'api', 'src')
const uvicorn = path.join(repoRoot, '.venv', 'bin', 'uvicorn')

export default defineConfig({
  testDir: './e2e',
  timeout: 90_000,
  expect: { timeout: 15_000 },
  // 后端扫描较慢且端口固定，串行跑避免资源竞争
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: [['list']],
  use: {
    baseURL: 'http://localhost:3000',
    viewport: { width: 1440, height: 900 },
    trace: 'retain-on-failure',
  },
  // Desktop Chrome 会带 1280x720 的 viewport，这里显式覆盖成 README 截图的 1440x900
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'], viewport: { width: 1440, height: 900 } },
    },
  ],
  webServer: [
    {
      // 真实 FastAPI，读演示数据；概览页快照默认读 repoRoot/data/dashboard_snapshot.json
      command: `STOCK_HSJDAY_ROOT=${demoHsjday} ${uvicorn} main:app --app-dir ${apiSrc} --port 8000`,
      url: 'http://localhost:8000/api/v1/health',
      reuseExistingServer: true,
      timeout: 120_000,
    },
    {
      command: 'npm run dev',
      url: 'http://localhost:3000',
      reuseExistingServer: true,
      timeout: 180_000,
    },
  ],
})
