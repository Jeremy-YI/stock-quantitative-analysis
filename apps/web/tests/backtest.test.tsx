import { describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'

// ECharts 依赖真实 canvas，jsdom 下用桩替换
vi.mock('echarts-for-react', () => ({
  default: () => <div data-testid="echarts" />,
}))

import DetailTable from '@/features/backtest/detail-table'
import EquityChart from '@/features/backtest/equity-chart'
import DecayChart from '@/features/backtest/decay-chart'
import ReturnHistogram from '@/features/backtest/return-histogram'

describe('backtest charts', () => {
  it('should render equity chart container', () => {
    render(<EquityChart series={[{ date: '2026-08-24', equity: 100 }]} />)
    expect(screen.getByTestId('echarts')).toBeTruthy()
  })

  it('should render decay chart container', () => {
    render(
      <DecayChart
        points={[{ date: '2026-08-24', window: 20, win_rate: 0.6, n: 5 }]}
      />
    )
    expect(screen.getByTestId('echarts')).toBeTruthy()
  })

  it('should render return histogram container', () => {
    render(
      <ReturnHistogram
        holdDays={1}
        bins={[{ lower: 0, upper: 0.02, count: 3 }]}
      />
    )
    expect(screen.getByTestId('echarts')).toBeTruthy()
  })
})

describe('backtest detail table', () => {
  const results = [
    {
      strategy: 'b1b2b3',
      holds: [
        {
          hold_days: 1,
          n: 10,
          win_rate: 0.6,
          avg_return: 0.01,
          median_return: 0.005,
          profit_loss_ratio: 1.5,
          std: 0.02,
          best: 0.1,
          worst: -0.08,
          quantiles: {},
          histogram: [],
        },
      ],
    },
  ]

  it('should render strategy and hold columns', () => {
    render(<DetailTable results={results} />)
    expect(screen.getByText('b1b2b3')).toBeTruthy()
    expect(screen.getByText('60.00%')).toBeTruthy() // 胜率 0.6 → 60%
  })

  it('should show empty hint when no data', () => {
    render(<DetailTable results={[]} />)
    expect(screen.getByText('暂无回测明细')).toBeTruthy()
  })
})
