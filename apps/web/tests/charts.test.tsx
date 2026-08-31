import { describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'

// ECharts 依赖真实浏览器 canvas，jsdom 下用桩替换，只验证图表组件能挂载并传入数据
vi.mock('echarts-for-react', () => ({
  default: () => <div data-testid='echarts' />,
}))

import MacdChart from '@/features/macd/macd-chart'
import KdjChart from '@/features/kdj/kdj-chart'
import RsiChart from '@/features/rsi/rsi-chart'
import VolumeChart from '@/features/volume/volume-chart'

describe('indicator charts', () => {
  it('should render MACD chart container', () => {
    render(<MacdChart series={[{ date: '2026-01-02', close: 10, dif: 0, dea: 0, macd: 0 }]} />)
    expect(screen.getByTestId('echarts')).toBeTruthy()
  })

  it('should render KDJ chart container', () => {
    render(<KdjChart series={[{ date: '2026-01-02', close: 10, k: 50, d: 50, j: 50 }]} />)
    expect(screen.getByTestId('echarts')).toBeTruthy()
  })

  it('should render RSI chart container', () => {
    render(<RsiChart series={[{ date: '2026-01-02', close: 10, rsi: 50 }]} />)
    expect(screen.getByTestId('echarts')).toBeTruthy()
  })

  it('should render volume chart container', () => {
    render(
      <VolumeChart
        series={[
          {
            date: '2026-01-02',
            close: 10,
            volume: 10000,
            mavol1: 10000,
            mavol2: 10000,
            volume_ratio: 1.0,
            relation: '—',
          },
        ]}
      />,
    )
    expect(screen.getByTestId('echarts')).toBeTruthy()
  })
})
