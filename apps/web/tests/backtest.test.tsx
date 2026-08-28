import { describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'

// ECharts 依赖真实 canvas，jsdom 下用桩替换
vi.mock('echarts-for-react', () => ({
  default: () => <div data-testid="echarts" />,
}))

import DetailTable from '@/features/backtest/detail-table'
import EquityChart from '@/features/backtest/equity-chart'
import DecayChart from '@/features/backtest/decay-chart'
import ExcessChart from '@/features/backtest/excess-chart'
import OverlayHeatmap from '@/features/backtest/overlay-heatmap'
import ReturnHistogram from '@/features/backtest/return-histogram'

describe('backtest charts', () => {
  it('should render equity chart container', () => {
    render(<EquityChart series={[{ date: '2026-08-24', equity: 100 }]} />)
    expect(screen.getByTestId('echarts')).toBeTruthy()
  })

  it('should render decay chart container', () => {
    render(
      <DecayChart
        points={[
          {
            date: '2026-08-24',
            window: 20,
            win_rate: 0.6,
            n: 5,
            baseline_win_rate: 0.45,
            excess_win_rate: 0.15,
          },
        ]}
      />
    )
    expect(screen.getByTestId('echarts')).toBeTruthy()
  })

  it('should render excess chart container', () => {
    render(
      <ExcessChart
        holdDays={1}
        results={[
          {
            strategy: 'b1b2b3',
            universe: 'stock',
            universe_size: 100,
            signals_per_day: 50,
            selectivity: 0.5,
            holds: [
              {
                hold_days: 1,
                n: 10,
                win_rate: 0.46,
                avg_return: 0.01,
                median_return: 0.005,
                profit_loss_ratio: 1.5,
                std: 0.02,
                best: 0.1,
                worst: -0.08,
                quantiles: {},
                histogram: [],
                baseline_win_rate: 0.466,
                baseline_avg_return: -0.0009,
                excess_win_rate: -0.006,
                excess_return: 0.0109,
              },
            ],
          },
        ]}
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

  it('should render overlay heatmap container', () => {
    render(
      <OverlayHeatmap
        cells={[
          {
            strategy_a: 'stealth_rally',
            strategy_b: 'double_bottom',
            n: 120,
            win_rate: 0.5,
            excess_win_rate: 0.07,
          },
        ]}
      />
    )
    expect(screen.getByTestId('echarts')).toBeTruthy()
  })

  it('should render overlay heatmap empty hint when no cells', () => {
    render(<OverlayHeatmap cells={[]} />)
    expect(screen.getByText(/暂无叠加分析数据/)).toBeTruthy()
  })
})

describe('backtest detail table', () => {
  const results = [
    {
      strategy: 'b1b2b3',
      universe: 'stock',
      universe_size: 5510,
      signals_per_day: 3160.3,
      selectivity: 0.573,
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
          baseline_win_rate: 0.466,
          baseline_avg_return: -0.0009,
          excess_win_rate: 0.134,
          excess_return: 0.0109,
        },
      ],
    },
  ]

  it('should render strategy and hold columns', () => {
    render(<DetailTable results={results} />)
    expect(screen.getByText('b1b2b3')).toBeTruthy()
    expect(screen.getByText('60.00%')).toBeTruthy() // 胜率 0.6 → 60%
  })

  it('should render excess win rate with sign', () => {
    render(<DetailTable results={results} />)
    expect(screen.getByText('+13.4pp')).toBeTruthy() // 超额 0.134 → +13.4pp
  })

  it('should show empty hint when no data', () => {
    render(<DetailTable results={[]} />)
    expect(screen.getByText('暂无回测明细')).toBeTruthy()
  })
})
