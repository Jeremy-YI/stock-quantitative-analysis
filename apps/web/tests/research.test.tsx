import { beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'

import type { ResearchSummary } from '@/features/research/types'

const mockUseResearch = vi.hoisted(() => vi.fn())

vi.mock('@/features/research/use-research', () => ({
  default: mockUseResearch,
}))

import ResearchView from '@/features/research/research-view'

function makeSummary(): ResearchSummary {
  return {
    as_of: '2026-08-27',
    sample: 700,
    hold_days: 5,
    baseline_win_rate: 0.449,
    single_factors: [
      {
        factor: 'vr60',
        label: '极缩<0.6',
        n: 6080,
        win_rate: 0.538,
        avg_return: 0.0072,
        excess_win_rate: 0.089,
        excess_return: 0.009,
      },
      {
        factor: '完美多头',
        label: '5>13>25>75>120',
        n: 4000,
        win_rate: 0.43,
        avg_return: -0.002,
        excess_win_rate: -0.017,
        excess_return: -0.003,
      },
    ],
    cross_matrix: [
      { row: '水下多头', col: '极缩<0.6', n: 6080, win_rate: 0.538, excess_win_rate: 0.089 },
      { row: '水上多头', col: '放量>1.2', n: 3000, win_rate: 0.39, excess_win_rate: -0.06 },
    ],
    regime_layers: [
      {
        dimension: '大盘 20 日涨跌',
        label: '弱跌-10~-4%',
        baseline_win_rate: 0.487,
        trend_n: 3316,
        trend_excess: -0.071,
        reversion_n: 8221,
        reversion_excess: 0.053,
      },
    ],
  }
}

describe('ResearchView', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockUseResearch.mockReturnValue({
      data: makeSummary(),
      loading: false,
      error: null,
    })
  })

  it('should render factor table rows', () => {
    render(<ResearchView />)
    expect(screen.getByText('因子研究')).toBeTruthy()
    expect(screen.getByText('vr60')).toBeTruthy()
    // +8.9pp 在单因子表与交叉矩阵中都会出现，至少出现一次即可
    expect(screen.getAllByText('+8.9pp').length).toBeGreaterThan(0)
    expect(screen.getByText('完美多头')).toBeTruthy()
    expect(screen.getByText('-1.7pp')).toBeTruthy()
  })

  it('should render cross matrix heatmap', () => {
    render(<ResearchView />)
    expect(screen.getByText('因子交叉矩阵（超额胜率）')).toBeTruthy()
    expect(screen.getByText('水下多头')).toBeTruthy()
  })

  it('should render regime layered comparison', () => {
    render(<ResearchView />)
    expect(screen.getByText('市场环境分层（趋势跟随 vs 均值回归超额）')).toBeTruthy()
    expect(screen.getByText('弱跌-10~-4%')).toBeTruthy()
  })

  it('should show error when loading fails', () => {
    mockUseResearch.mockReturnValue({
      data: null,
      loading: false,
      error: '加载失败',
    })
    render(<ResearchView />)
    expect(screen.getByText('加载失败')).toBeTruthy()
  })
})
