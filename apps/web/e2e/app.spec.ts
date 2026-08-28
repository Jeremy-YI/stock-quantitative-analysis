import { expect, test, type Page } from '@playwright/test'

/**
 * 端到端测试：真实 FastAPI（演示数据）+ Next.js。
 * 覆盖五条关键路径 + 错误路径（后端 404/500 前端有友好提示，不白屏）。
 */

// 指标图表容器（IndicatorPanel 渲染图表时挂这个 data-testid）
const CHART = '[data-testid="indicator-chart"]'

async function waitForChart(page: Page) {
  await expect(page.locator(CHART)).toBeVisible({ timeout: 30_000 })
  // ECharts 渲染后容器内会出现 canvas
  await expect(page.locator(`${CHART} canvas`).first()).toBeVisible({
    timeout: 15_000,
  })
}

test('1. 首页 Dashboard 加载，关键卡片有数据', async ({ page }) => {
  await page.goto('/')
  // 概览页标题 + 快照日
  await expect(page.getByRole('heading', { name: '概览' })).toBeVisible({
    timeout: 30_000,
  })
  // 策略卡片区标题与至少一个策略名
  await expect(page.getByText('策略信号与超额胜率')).toBeVisible()
  await expect(page.getByText('b1b2b3')).toBeVisible()
  await expect(page.getByText('stealth_rally')).toBeVisible()
  // 市场基线卡片
  await expect(page.getByText(/市场基线/).first()).toBeVisible()
  // 最近扫描状态卡片
  await expect(page.getByText('最近扫描状态')).toBeVisible()
})

test('2. 指标页输入代码 → MACD 渲染 → 切换 KDJ/RSI/量能', async ({ page }) => {
  await page.goto('/indicators')
  await expect(page.getByRole('heading', { name: '技术指标' })).toBeVisible({
    timeout: 30_000,
  })

  // 默认 600519，MACD 自动加载并渲染
  await expect(page.getByText('600519 日线 MACD')).toBeVisible({ timeout: 30_000 })
  await waitForChart(page)

  // 切 KDJ
  await page.getByRole('tab', { name: 'KDJ' }).click()
  await expect(page.getByText(/日线 KDJ/)).toBeVisible({ timeout: 30_000 })
  await waitForChart(page)

  // 切 RSI
  await page.getByRole('tab', { name: 'RSI' }).click()
  await expect(page.getByText(/日线 RSI/)).toBeVisible({ timeout: 30_000 })
  await waitForChart(page)

  // 切量能
  await page.getByRole('tab', { name: '量能' }).click()
  await expect(page.getByText(/日线 量能/)).toBeVisible({ timeout: 30_000 })
  await waitForChart(page)
})

test('3. 选股页选策略 + 日期 → 表格 → 排序 → 点行看图', async ({ page }) => {
  await page.goto('/strategies')
  await expect(page.getByRole('heading', { name: '选股策略' })).toBeVisible({
    timeout: 30_000,
  })

  // 选策略 + 保持默认日期 2026-08-27
  await page.selectOption('#strategy', 'b1b2b3')
  await page.getByRole('button', { name: '扫描' }).click()

  // 表格出数据（b1b2b3 在演示数据当日有 19 条信号）
  await expect(page.getByText(/个信号/)).toBeVisible({ timeout: 30_000 })
  await expect(page.locator('tbody tr').first()).toBeVisible({ timeout: 30_000 })

  // 点「评分」列头排序，出现排序箭头
  await page.getByRole('columnheader', { name: /评分/ }).click()
  await expect(page.locator('thead').getByText('↑').first()).toBeVisible()

  // 点某行 → 下方出现该股的指标图
  await page.locator('tbody tr').first().click()
  await expect(page.getByText(/日线 MACD/)).toBeVisible({ timeout: 30_000 })
})

test('4. 回测页加载 → 净值曲线 / 超额胜率 / 选择性渲染', async ({ page }) => {
  test.setTimeout(180_000)
  await page.goto('/backtest')
  await expect(page.getByRole('heading', { name: '策略回测' })).toBeVisible({
    timeout: 30_000,
  })

  await page.getByRole('button', { name: '发起回测' }).click()

  // 统计卡片（总信号数 / 组合总收益等）
  await expect(page.getByText('总信号数')).toBeVisible({ timeout: 60_000 })
  // 超额胜率对比卡片
  await expect(page.getByText('策略胜率 vs 基线胜率')).toBeVisible()
  // 选择性指标（在明细表或卡片里）
  await expect(page.getByText(/选择性/).first()).toBeVisible()
})

test('5. 调度页任务列表渲染 → 手动触发可点（mock 后端）', async ({ page }) => {
  // 调度器默认连 MySQL，E2E 里 mock 掉三个端点，不真跑任务
  await page.route('**/api/v1/scheduler/jobs', async (route) => {
    await route.fulfill({
      json: {
        message: 'ok',
        body: {
          jobs: [
            {
              name: 'daily_scan',
              description: '每日收盘全市场扫描',
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
          ],
        },
      },
    })
  })
  await page.route('**/api/v1/scheduler/runs*', async (route) => {
    await route.fulfill({ json: { message: 'ok', body: { runs: [] } } })
  })
  const triggerRequest = page.waitForRequest(
    (req) =>
      req.method() === 'POST' &&
      req.url().includes('/api/v1/scheduler/jobs/daily_scan/trigger')
  )
  await page.route('**/api/v1/scheduler/jobs/*/trigger', async (route) => {
    await route.fulfill({
      json: {
        message: 'ok',
        body: {
          job_name: 'daily_scan',
          trigger: 'manual',
          run: {
            run_id: 'mock-run-1',
            job_name: 'daily_scan',
            trigger: 'manual',
            status: 'success',
            started_at: '2026-08-28T18:00:00+08:00',
            finished_at: '2026-08-28T18:00:01+08:00',
            duration_seconds: 1.0,
            progress: 1,
            summary: 'mock ok',
            error: '',
            attempt: 0,
          },
        },
      },
    })
  })

  await page.goto('/scheduler')
  await expect(page.getByText('任务调度器')).toBeVisible({ timeout: 30_000 })
  await expect(page.getByText('daily_scan')).toBeVisible()
  await expect(page.getByText('30 15 * * 1-5')).toBeVisible()

  // 手动触发按钮可点，点击后发出 POST 请求
  await page.getByRole('button', { name: '手动触发' }).click()
  await triggerRequest
})

test('6. 错误路径：未知代码 404 有友好提示，不白屏', async ({ page }) => {
  await page.goto('/indicators')
  await expect(page.getByRole('heading', { name: '技术指标' })).toBeVisible({
    timeout: 30_000,
  })

  await page.fill('#symbol', '999999')
  await page.getByRole('button', { name: '查询' }).click()

  // 后端 404 → 前端把语义串渲染出来，而不是白屏
  await expect(page.getByText(/不存在/)).toBeVisible({ timeout: 30_000 })
})
