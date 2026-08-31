import { test } from '@playwright/test'
test('回测页发起回测', async ({ page }) => {
  const reqs: string[] = []
  page.on('request', (r) => { if (r.url().includes('/api/')) reqs.push(`${r.method()} ${r.url()}`) })
  page.on('response', async (r) => {
    if (r.url().includes('/api/') && r.status() >= 400) {
      console.log('HTTP', r.status(), r.url())
      try { console.log('  body', (await r.text()).slice(0, 300)) } catch {}
    }
  })
  await page.setViewportSize({ width: 1440, height: 900 })
  await page.goto('/backtest')
  await page.selectOption('#strategy', 'pin30')
  await page.getByRole('button', { name: '发起回测' }).click()
  await page.waitForTimeout(12000)
  console.log('API REQUESTS:', JSON.stringify(reqs))
})
