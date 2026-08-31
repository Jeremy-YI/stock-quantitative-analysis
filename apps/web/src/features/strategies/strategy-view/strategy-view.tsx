'use client'

import { useState } from 'react'

import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Skeleton } from '@/components/ui/skeleton'
import MacdPanel from '@/features/macd/macd-panel'

import SignalTable from '../signal-table'
import { field, form, header, pageTitle, pageWrapper, tableCard } from '../style'
import useScan from '../use-scan'
import useStrategies from '../use-strategies'

const DEFAULT_DATE = '2026-08-27'

/**
 * 选股看板页：策略选择 + 日期选择 + 结果表格（点击行展开该股的指标图）。
 */
export default function StrategyView() {
  const { data: strategies, loading, error } = useStrategies()

  const [strategy, setStrategy] = useState<string | null>(null)
  const [date, setDate] = useState(DEFAULT_DATE)
  const [submittedStrategy, setSubmittedStrategy] = useState<string | null>(null)
  const [selectedSymbol, setSelectedSymbol] = useState<string | null>(null)

  const { data: signals, loading: scanning, error: scanError } = useScan(submittedStrategy, date)

  const handleSubmit = (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    setSubmittedStrategy(strategy)
    setSelectedSymbol(null)
  }

  return (
    <main className={pageWrapper}>
      <header className={header}>
        <h1 className={pageTitle}>选股策略</h1>
      </header>

      <form className={form} onSubmit={handleSubmit}>
        <div className={field}>
          <Label htmlFor='strategy'>策略</Label>
          <select
            id='strategy'
            value={strategy ?? ''}
            onChange={(event) => setStrategy(event.target.value || null)}
            className='h-9 rounded-md border border-border bg-background px-3 text-sm'
          >
            <option value=''>请选择策略</option>
            {strategies.map((s) => (
              <option key={s.name} value={s.name}>
                {s.label} — {s.description}
              </option>
            ))}
          </select>
        </div>

        <div className={field}>
          <Label htmlFor='date'>日期</Label>
          <Input
            id='date'
            value={date}
            onChange={(event) => setDate(event.target.value)}
            placeholder='YYYY-MM-DD'
          />
        </div>

        <Button type='submit' disabled={!strategy}>
          扫描
        </Button>
      </form>

      {loading && <Skeleton className='h-10 w-full' />}
      {!loading && error && <p className='text-down'>{error}</p>}

      {scanning && <Skeleton className='h-[240px] w-full mobile-portrait:h-[300px]' />}

      {!scanning && submittedStrategy && !scanError && (
        <Card className={tableCard}>
          <CardHeader>
            <CardTitle>
              {submittedStrategy} · {date} · {signals.length} 个信号
            </CardTitle>
          </CardHeader>
          <CardContent>
            {scanError ? (
              <p className='text-down'>{scanError}</p>
            ) : (
              <SignalTable signals={signals} onRowClick={(symbol) => setSelectedSymbol(symbol)} />
            )}
          </CardContent>
        </Card>
      )}

      {!scanning && scanError && <p className='text-down'>{scanError}</p>}

      {selectedSymbol && (
        <div className='w-full'>
          <MacdPanel symbol={selectedSymbol} />
        </div>
      )}
    </main>
  )
}
