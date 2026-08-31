import { expect, test, type Page } from '@playwright/test'
import path from 'node:path'

/**
 * 响应式验收：同一批页面在手机 / 平板 / 桌面三档视口各截一张，
 * 顺便断言「没有横向溢出」——这是响应式最容易翻车的地方（写死宽度、表格顶宽）。
 *
 * 输出：docs/screenshots/responsive/<页面>-<档位>.png
 */

const repoRoot = path.resolve(__dirname, '..', '..', '..')
const outDir = path.join(repoRoot, 'docs', 'screenshots', 'responsive')

const VIEWPORTS = [
  { name: 'mobile', width: 375, height: 780 },
  { name: 'tablet', width: 768, height: 1024 },
  { name: 'desktop', width: 1440, height: 900 },
]

// ready 用页面 h1 判定，不用纯文本：纯文本会先命中导航里同名（且小屏隐藏）的链接
const PAGES = [
  { slug: 'dashboard', url: '/', ready: '概览' },
  { slug: 'sectors', url: '/sectors', ready: '板块资金' },
  { slug: 'recommendations', url: '/recommendations', ready: '个股推荐' },
  { slug: 'news', url: '/news', ready: '最新消息' },
  { slug: 'events', url: '/events', ready: '事件日历' },
  { slug: 'design', url: '/design', ready: '设计系统' },
]

/** 页面不应该出现横向滚动（允许 1px 取整误差）。 */
async function expectNoHorizontalOverflow(page: Page) {
  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth - document.documentElement.clientWidth
  )
  expect(overflow, `页面横向溢出 ${overflow}px`).toBeLessThanOrEqual(1)
}

for (const vp of VIEWPORTS) {
  for (const p of PAGES) {
    test(`响应式 ${vp.name}(${vp.width}) · ${p.slug}`, async ({ page }) => {
      await page.setViewportSize({ width: vp.width, height: vp.height })
      await page.goto(p.url)
      await expect(
        page.getByRole('heading', { level: 1, name: p.ready })
      ).toBeVisible({ timeout: 60_000 })
      await expectNoHorizontalOverflow(page)
      await page.screenshot({
        path: path.join(outDir, `${p.slug}-${vp.name}.png`),
        fullPage: false,
      })
    })
  }
}
