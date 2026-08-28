import { beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'

import type { DashboardOverview } from '@/features/dashboard/types'

// 在组件挂载前 mock useDashboard，让 DashboardView 拿到固定数据，避免真实请求
const mockUseDashboard = vi.hoisted(() => vi.fn())

vi.mock('@/features/dashboard/use-dashboard', () => ({
  default: mockUseDashboard,
}))

import DashboardView from '@/features/dashboard/dashboard-view'

function makeOverview(): DashboardOverview {
  return {
    as_of: '2026-08-27',
    strategies: [
      {
        name: 'stealth_rally',
        description: '水下二次金叉',
        signals_today: 1263,
        selectivity: 0.152,
        excess_win_rate: 0.068,
        hold_days: 20,
      },
      {
        name: 'macd_resonance',
        description: '月线水上 + 周线底部金叉',
        signals_today: 629,
        selectivity: 0.045,
        excess_win_rate: -0.129,
        hold_days: 20,
      },
    ],
    baselines: [
      {
        universe: 'stock',
        size: 5510,
        holds: [{ hold_days: 1, win_rate: 0.467, avg_return: -0.0009 }],
      },
    ],
    last_scan: { status: 'ok', as_of: '2026-08-27', duration_seconds: 45.2, symbols_scanned: 6968 },
    regime: {
      as_of: '2026-08-27',
      index_20d_return: -0.03,
      activity: 0.9,
      drawdown: -0.05,
      index_20d_label: '微跌-4~0',
      activity_label: '偏淡0.8-1.0',
      drawdown_label: '近高-8~-3%',
      allow_open: true,
    },
    recent_runs: [],
  }
}

describe('DashboardView', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockUseDashboard.mockReturnValue({
      data: makeOverview(),
      loading: false,
      error: null,
    })
  })

  it('should render strategy names and signals', () => {
    render(<DashboardView />)
    expect(screen.getByText('stealth_rally')).toBeTruthy()
    expect(screen.getByText('1263')).toBeTruthy()
    expect(screen.getByText('macd_resonance')).toBeTruthy()
  })

  it('should render excess win rate with sign and pp', () => {
    render(<DashboardView />)
    expect(screen.getByText('+6.8pp')).toBeTruthy()
    expect(screen.getByText('-12.9pp')).toBeTruthy()
  })

  it('should render baseline win rate and scan status', () => {
    render(<DashboardView />)
    expect(screen.getByText('市场基线 · 个股')).toBeTruthy()
    expect(screen.getByText('46.7%')).toBeTruthy()
    expect(screen.getByText('6968')).toBeTruthy()
  })

  it('should render navigation to sub pages', () => {
    render(<DashboardView />)
    expect(screen.getByText('技术指标')).toBeTruthy()
    expect(screen.getByText('选股策略')).toBeTruthy()
    expect(screen.getByText('策略回测')).toBeTruthy()
    expect(screen.getByText('任务调度')).toBeTruthy()
  })

  it('should render market regime card', () => {
    render(<DashboardView />)
    expect(screen.getByText('当前市场环境')).toBeTruthy()
    expect(screen.getByText('微跌-4~0')).toBeTruthy()
    expect(screen.getByText('允许开仓')).toBeTruthy()
  })

  it('should show error when loading fails', () => {
    mockUseDashboard.mockReturnValue({
      data: null,
      loading: false,
      error: '加载失败',
    })
    render(<DashboardView />)
    expect(screen.getByText('加载失败')).toBeTruthy()
  })
})
