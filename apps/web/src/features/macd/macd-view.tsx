'use client'

import { useState } from 'react'
import dynamic from 'next/dynamic'

import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Skeleton } from '@/components/ui/skeleton'

import {
  chartCard,
  chartContainer,
  field,
  form,
  header,
  legendHint,
  pageTitle,
  pageWrapper,
} from './macd-styles'
import useMacd from './use-macd'

// ECharts 依赖浏览器 API，SSR 阶段无法执行，用 ssr:false 只在客户端渲染
const MacdChart = dynamic(() => import('./macd-chart'), { ssr: false })

const DEFAULT_SYMBOL = '600519'

export default function MacdView() {
  const [input, setInput] = useState(DEFAULT_SYMBOL)
  const [symbol, setSymbol] = useState(DEFAULT_SYMBOL)
  const { data, loading, error } = useMacd(symbol)

  const handleSubmit = (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    setSymbol(input.trim())
  }

  return (
    <main className={pageWrapper}>
      <header className={header}>
        <h1 className={pageTitle}>MACD 指标</h1>
      </header>

      <form className={form} onSubmit={handleSubmit}>
        <div className={field}>
          <Label htmlFor="symbol">股票代码</Label>
          <Input
            id="symbol"
            value={input}
            onChange={(event) => setInput(event.target.value)}
            placeholder="6 位代码，如 600519"
            maxLength={6}
          />
        </div>
        <Button type="submit">查询</Button>
      </form>

      <Card className={chartCard}>
        <CardHeader>
          <CardTitle>{data ? `${data.symbol} 日线 MACD` : '加载中…'}</CardTitle>
          <div className={legendHint}>
            <span className="text-up">● 红涨</span>
            <span className="text-down">● 绿跌</span>
          </div>
        </CardHeader>
        <CardContent>
          {loading && <Skeleton className="h-[520px] w-full" />}
          {!loading && error && (
            <p className="py-10 text-center text-down">{error}</p>
          )}
          {!loading && !error && data && (
            <div className={chartContainer}>
              <MacdChart series={data.series} />
            </div>
          )}
        </CardContent>
      </Card>
    </main>
  )
}
