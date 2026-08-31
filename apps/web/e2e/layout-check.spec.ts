import { expect, test } from '@playwright/test'

/**
 * 版式回归：表格行不能重叠（sticky 表头 / 分组行 / 徽标换行都可能压行，
 * 肉眼看截图容易误判，这里直接量 DOM 矩形）。
 */
test('板块资金 + ETF 资金流：表格行不重叠', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 })
  await page.goto('/sectors')
  await expect(page.getByRole('heading', { level: 1, name: '板块资金' })).toBeVisible()
  await page.waitForTimeout(3500)

  const report = await page.evaluate(() => {
    const problems: string[] = []
    document.querySelectorAll('table').forEach((tbl, ti) => {
      const rows = [...tbl.querySelectorAll('tbody tr')]
      for (let i = 1; i < rows.length; i += 1) {
        const a = rows[i - 1].getBoundingClientRect()
        const b = rows[i].getBoundingClientRect()
        if (a.height > 0 && b.height > 0 && b.top < a.bottom - 1.5) {
          problems.push(
            `table#${ti} row${i - 1}/${i} 重叠 ${(a.bottom - b.top).toFixed(1)}px: ` +
              `${rows[i - 1].textContent?.slice(0, 20)} / ${rows[i].textContent?.slice(0, 20)}`,
          )
        }
      }
    })
    return problems
  })

  console.log('重叠报告:', JSON.stringify(report, null, 1))
  expect(report).toEqual([])
})
