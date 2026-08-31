import { expect, test, type Page } from '@playwright/test'
import path from 'node:path'

/**
 * README 截图：跑 E2E 时顺便截 5 张图（1440x900），存到 docs/screenshots/。
 * 截图内容不含任何真实持仓/账号信息（演示数据 + mock 调度器）。
 */

const repoRoot = path.resolve(__dirname, '..', '..', '..')
const outDir = path.join(repoRoot, 'docs', 'screenshots')

async function shoot(page: Page, name: string) {
  await page.screenshot({
    path: path.join(outDir, name),
    fullPage: false,
  })
}

test('截图：首页 Dashboard', async ({ page }) => {
  await page.goto('/')
  await expect(page.getByText('策略信号与超额胜率')).toBeVisible({ timeout: 30_000 })
  await expect(page.getByText(/市场基线/).first()).toBeVisible()
  await shoot(page, 'dashboard.png')
})

test('截图：指标图（MACD）', async ({ page }) => {
  await page.goto('/indicators')
  await expect(page.getByText('600519 日线 MACD')).toBeVisible({ timeout: 30_000 })
  await expect(page.locator('[data-testid="indicator-chart"] canvas').first()).toBeVisible({
    timeout: 15_000,
  })
  await shoot(page, 'indicators.png')
})

test('截图：选股结果表', async ({ page }) => {
  await page.goto('/strategies')
  await page.selectOption('#strategy', 'b1b2b3')
  await page.getByRole('button', { name: '扫描' }).click()
  await expect(page.locator('tbody tr').first()).toBeVisible({ timeout: 30_000 })
  await shoot(page, 'strategies.png')
})

test('截图：回测页（含超额对比）', async ({ page }) => {
  test.setTimeout(180_000)
  await page.goto('/backtest')
  await page.getByRole('button', { name: '发起回测' }).click()
  await expect(page.getByText('策略胜率 vs 基线胜率')).toBeVisible({ timeout: 120_000 })
  await shoot(page, 'backtest.png')
})

test('截图：调度任务页', async ({ page }) => {
  await page.route('**/api/v1/scheduler/jobs', async (route) => {
    await route.fulfill({
      json: {
        message: 'ok',
        body: {
          jobs: [
            {
              name: 'daily_scan',
              description: '每日收盘全市场扫描（五策略，分片 + 断点续跑）',
              cron: '30 15 * * 1-5',
              timezone: 'Asia/Shanghai',
              enabled: true,
              allow_concurrent: false,
              timeout_seconds: 1200,
              max_retries: 1,
              notifier: 'file',
              tags: ['A股'],
              next_run_at: '2026-08-31T15:30:00+08:00',
              last_status: 'success',
              last_duration_seconds: 69.2,
              last_finished_at: '2026-08-28T15:31:09+08:00',
              last_progress: 1,
            },
            {
              name: 'daily_report',
              description: '每日选股报告',
              cron: '0 16 * * 1-5',
              timezone: 'Asia/Shanghai',
              enabled: true,
              allow_concurrent: false,
              timeout_seconds: 300,
              max_retries: 0,
              notifier: 'webhook',
              tags: ['A股'],
              next_run_at: '2026-08-31T16:00:00+08:00',
              last_status: 'failed',
              last_duration_seconds: null,
              last_finished_at: null,
              last_progress: null,
            },
          ],
        },
      },
    })
  })
  await page.route('**/api/v1/scheduler/runs*', async (route) => {
    await route.fulfill({ json: { message: 'ok', body: { runs: [] } } })
  })

  await page.goto('/scheduler')
  await expect(page.getByText('任务列表')).toBeVisible({ timeout: 30_000 })
  await expect(page.getByText('daily_scan')).toBeVisible()
  await shoot(page, 'scheduler.png')
})
