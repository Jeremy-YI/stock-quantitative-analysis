import { describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

// 用桩替换四个指标 Panel，隔离数据拉取与 ECharts，专注测容器切换逻辑
vi.mock('@/features/macd/macd-panel', () => ({
  default: ({ symbol }: { symbol: string }) => <div data-testid='macd-panel'>{symbol}</div>,
}))
vi.mock('@/features/kdj/kdj-panel', () => ({
  default: ({ symbol }: { symbol: string }) => <div data-testid='kdj-panel'>{symbol}</div>,
}))
vi.mock('@/features/rsi/rsi-panel', () => ({
  default: ({ symbol }: { symbol: string }) => <div data-testid='rsi-panel'>{symbol}</div>,
}))
vi.mock('@/features/volume/volume-panel', () => ({
  default: ({ symbol }: { symbol: string }) => <div data-testid='volume-panel'>{symbol}</div>,
}))

import IndicatorView from '@/features/indicators/indicator-view'

describe('IndicatorView', () => {
  it('should default to MACD panel', () => {
    render(<IndicatorView />)
    expect(screen.getByTestId('macd-panel')).toBeTruthy()
    expect(screen.queryByTestId('kdj-panel')).toBeNull()
  })

  it('should switch panels via tabs', async () => {
    render(<IndicatorView />)
    await userEvent.click(screen.getByRole('tab', { name: 'KDJ' }))
    expect(screen.getByTestId('kdj-panel')).toBeTruthy()
    expect(screen.queryByTestId('macd-panel')).toBeNull()
  })

  it('should pass current symbol to the active panel', async () => {
    render(<IndicatorView />)
    expect(screen.getByTestId('macd-panel').textContent).toBe('600519')
    await userEvent.click(screen.getByRole('tab', { name: '量能' }))
    expect(screen.getByTestId('volume-panel').textContent).toBe('600519')
  })
})
