import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'

import SignalTable, { changePct } from '@/features/strategies/signal-table'
import type { Signal } from '@/features/strategies/types'

function makeSignal(
  symbol: string,
  signalType: string,
  score: number,
  metrics: Signal['metrics'],
): Signal {
  return {
    symbol,
    strategy: 'b1b2b3',
    signal_type: signalType,
    score,
    triggered_at: '2026-08-27',
    metrics,
  }
}

const signals: Signal[] = [
  makeSignal('600002', 'b1', 70, { pct: -3.0, close: 20 }),
  makeSignal('600001', 'b2', 85, { pct: 5.0, close: 10 }),
  makeSignal('600003', 'b3', 55, { volume_ratio: 0.5 }),
]

describe('changePct', () => {
  it('should extract pct from metrics', () => {
    expect(changePct(makeSignal('1', 'b2', 80, { pct: 5.0 }))).toBe(5.0)
  })

  it('should fall back to stealth_gain / drawdown_pct', () => {
    expect(changePct(makeSignal('1', 'x', 80, { stealth_gain: -2.5 }))).toBe(-2.5)
    expect(changePct(makeSignal('1', 'x', 80, { drawdown_pct: -35 }))).toBe(-35)
  })

  it('should return null when no change field present', () => {
    expect(changePct(makeSignal('1', 'x', 80, { close: 10 }))).toBeNull()
  })
})

describe('SignalTable', () => {
  it('should render symbols and signal types', () => {
    render(<SignalTable signals={signals} />)
    expect(screen.getByText('600001')).toBeTruthy()
    expect(screen.getByText('600002')).toBeTruthy()
    expect(screen.getByText('b1')).toBeTruthy()
    expect(screen.getByText('b2')).toBeTruthy()
  })

  it('should render empty hint when no signals', () => {
    render(<SignalTable signals={[]} />)
    expect(screen.getByText('该日期无命中信号')).toBeTruthy()
  })

  it('should sort by score when clicking header (ascending)', () => {
    render(<SignalTable signals={signals} />)
    fireEvent.click(screen.getByRole('columnheader', { name: /评分/ }))

    const rows = screen.getAllByRole('row').slice(1) // 去掉表头
    const firstSymbol = rows[0].textContent
    // 升序：最低分 55（600003）在前
    expect(firstSymbol).toContain('600003')
  })

  it('should toggle column visibility', () => {
    render(<SignalTable signals={signals} />)
    // 详情列默认可见
    expect(screen.getByRole('columnheader', { name: '详情' })).toBeTruthy()

    // 取消勾选「详情」列
    const checkbox = screen.getByRole('checkbox', { name: /详情/ })
    fireEvent.click(checkbox)

    expect(screen.queryByRole('columnheader', { name: '详情' })).toBeNull()
  })

  it('should color positive change with up semantic color', () => {
    render(<SignalTable signals={signals} />)
    // 600001 的涨跌幅 +5.00 → text-up
    const cell = screen.getByText('5.00')
    expect(cell.className).toContain('text-up')
  })

  it('should invoke onRowClick with symbol', () => {
    const onRowClick = vi.fn()
    render(<SignalTable signals={signals} onRowClick={onRowClick} />)
    fireEvent.click(screen.getByText('600001'))
    expect(onRowClick).toHaveBeenCalledWith('600001')
  })
})
