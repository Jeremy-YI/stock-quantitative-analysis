'use client'

import { useState } from 'react'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import Tabs from '@/components/ui/tabs'

import MacdPanel from '@/features/macd/macd-panel'
import KdjPanel from '@/features/kdj/kdj-panel'
import RsiPanel from '@/features/rsi/rsi-panel'
import VolumePanel from '@/features/volume/volume-panel'
import PricingLinesPanel from '@/features/pricing-lines/pricing-lines-panel'

import { field, form, header, pageTitle, pageWrapper, tabsRow } from '../style'

const DEFAULT_SYMBOL = '600519'

const TABS = [
  { value: 'macd', label: 'MACD' },
  { value: 'kdj', label: 'KDJ' },
  { value: 'rsi', label: 'RSI' },
  { value: 'volume', label: '量能' },
  { value: 'pricing', label: '定价线' },
]

/**
 * 指标页容器：股票代码输入 + 指标 Tab 切换。
 * 只有当前激活的指标 Panel 会挂载并发起请求。
 */
export default function IndicatorView() {
  const [input, setInput] = useState(DEFAULT_SYMBOL)
  const [symbol, setSymbol] = useState(DEFAULT_SYMBOL)
  const [tab, setTab] = useState('macd')

  const handleSubmit = (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    setSymbol(input.trim())
  }

  return (
    <main className={pageWrapper}>
      <header className={header}>
        <h1 className={pageTitle}>技术指标</h1>
      </header>

      <form className={form} onSubmit={handleSubmit}>
        <div className={field}>
          <Label htmlFor='symbol'>股票代码</Label>
          <Input
            id='symbol'
            value={input}
            onChange={(event) => setInput(event.target.value)}
            placeholder='6 位代码，如 600519'
            maxLength={6}
          />
        </div>
        <Button type='submit'>查询</Button>
      </form>

      <div className={tabsRow}>
        <Tabs value={tab} onValueChange={setTab} items={TABS} />
      </div>

      {tab === 'macd' && <MacdPanel symbol={symbol} />}
      {tab === 'kdj' && <KdjPanel symbol={symbol} />}
      {tab === 'rsi' && <RsiPanel symbol={symbol} />}
      {tab === 'volume' && <VolumePanel symbol={symbol} />}
      {tab === 'pricing' && <PricingLinesPanel symbol={symbol} />}
    </main>
  )
}
