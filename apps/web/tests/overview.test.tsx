import { describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'

// 概览页把六个数据源拼在一起，这里全部 mock 掉，只验「拼装逻辑 + 展示规则」
const mockDashboard = vi.hoisted(() => vi.fn())
const mockSectors = vi.hoisted(() => vi.fn())
const mockEtfFlow = vi.hoisted(() => vi.fn())
const mockNews = vi.hoisted(() => vi.fn())
const mockEvents = vi.hoisted(() => vi.fn())
const mockRecommendations = vi.hoisted(() => vi.fn())

vi.mock('@/features/dashboard/use-dashboard', () => ({ default: mockDashboard }))
vi.mock('@/features/sectors/use-sectors', () => ({ default: mockSectors }))
vi.mock('@/features/sectors/use-etf-flow', () => ({ default: mockEtfFlow }))
vi.mock('@/features/news/use-news', () => ({ default: mockNews }))
vi.mock('@/features/events/use-events', () => ({ default: mockEvents }))
vi.mock('@/features/recommendations/use-recommendations', () => ({
  useRecommendations: mockRecommendations,
  useSectorList: () => [],
}))

import OverviewView from '@/features/overview/overview-view'

function sectorRow(sector: string, net: number) {
  return {
    sector,
    etf: null,
    change_pct: 1.2,
    inflow: 100,
    outflow: 90,
    net,
    companies: 50,
    leader: '',
    leader_pct: 0,
    signal: null,
  }
}

function setup() {
  mockDashboard.mockReturnValue({
    data: {
      as_of: '2026-08-28',
      strategies: [],
      baselines: [],
      recent_runs: [],
      last_scan: null,
      regime: {
        as_of: '2026-08-28',
        index_20d_return: -0.031,
        index_20d_label: '偏弱',
        activity: 1.12,
        activity_label: '中性',
        drawdown: -0.085,
        drawdown_label: '回撤中',
        allow_open: false,
      },
    },
    loading: false,
    error: null,
  })
  mockSectors.mockImplementation((days: string) =>
    days === '即时'
      ? {
          data: {
            days,
            top_inflow: [sectorRow('工业金属', 14.7), sectorRow('半导体', 9.1)],
            top_outflow: [sectorRow('酿酒行业', -8.3)],
          },
          loading: false,
          error: null,
        }
      : {
          data: {
            days,
            top_inflow: [sectorRow('工业金属', 30.2)],
            top_outflow: [],
          },
          loading: false,
          error: null,
        },
  )
  mockEtfFlow.mockReturnValue({
    data: {
      date: '2026-08-28',
      total: 1121,
      has_share_flow: false,
      flow_available: false,
      leaders: [
        {
          code: '510300',
          name: '沪深300ETF华泰柏瑞',
          price: 4.679,
          change_pct: -0.26,
          net: null,
          net_ratio: null,
          turnover: 28.35,
          turnover_rate: 0,
          mcap: 1099.2,
          share_net: null,
          category: '宽基',
          theme: '沪深300',
          peers: 25,
        },
      ],
      top_inflow: [],
      top_outflow: [],
    },
    loading: false,
    error: null,
  })
  mockNews.mockReturnValue({
    data: {
      date: '2026-08-28',
      source: '金十数据',
      items: [
        { title: '结构性关注的消息', impact: '结构性关注', outlook: 'a', sources: 2 },
        { title: '会改变定价的消息', impact: '改变定价', outlook: 'b', sources: 5 },
      ],
    },
    loading: false,
    error: null,
  })
  const today = new Date()
  const soon = new Date(today.getTime() + 2 * 86400000).toISOString().slice(0, 10)
  const far = new Date(today.getTime() + 60 * 86400000).toISOString().slice(0, 10)
  mockEvents.mockReturnValue({
    data: {
      note: '种子数据',
      events: [
        { date: soon, name: 'FOMC 会议', type: '央行会议', importance: '高' },
        { date: far, name: '远期事件', type: '数据', importance: '高' },
        { date: soon, name: '低重要度事件', type: '数据', importance: '低' },
      ],
    },
    loading: false,
    error: null,
  })
  mockRecommendations.mockReturnValue({
    data: {
      sector: '工业金属',
      date: '2026-08-28',
      signals: [],
      stocks: [
        {
          symbol: '600584',
          name: '长电科技',
          score: 85,
          signals: [
            {
              symbol: '600584',
              strategy: 'b1b2b3',
              signal_type: 'b2',
              score: 85,
              triggered_at: '2026-08-28',
              metrics: {},
            },
          ],
        },
      ],
      excluded_st: 2,
      names_available: true,
    },
    loading: false,
    error: null,
  })
}

describe('OverviewView', () => {
  it('市场状态用 regime：开仓建议为「不建议开仓」且标红', () => {
    setup()
    render(<OverviewView />)
    const value = screen.getByText('不建议开仓')
    expect(value.className).toContain('text-down')
    expect(screen.getByText('-3.1%')).toBeTruthy() // 大盘 20 日
  })

  it('资金主线取 TOP3，并给「5日同向」的板块打标', () => {
    setup()
    render(<OverviewView />)
    expect(screen.getByText('工业金属')).toBeTruthy()
    expect(screen.getByText('半导体')).toBeTruthy()
    expect(screen.getByText('酿酒行业')).toBeTruthy()
    // 工业金属在即时和 5 日都在流入榜 → 打标
    expect(screen.getByText('5日同向')).toBeTruthy()
  })

  it('今日精选取资金最强板块的信号股，链接到个股详情', () => {
    setup()
    render(<OverviewView />)
    const link = screen.getByRole('link', { name: /长电科技/ })
    expect(link.getAttribute('href')).toBe('/stocks/600584?date=2026-08-28')
    expect(screen.getByText('超卖反弹')).toBeTruthy()
  })

  it('要闻按影响评级排序（改变定价排最前）', () => {
    setup()
    render(<OverviewView />)
    const titles = screen.getAllByText(/的消息$/).map((el) => el.textContent)
    expect(titles[0]).toBe('会改变定价的消息')
  })

  it('临近事件只留未来 7 天且非「低」重要度', () => {
    setup()
    render(<OverviewView />)
    expect(screen.getByText('FOMC 会议')).toBeTruthy()
    expect(screen.queryByText('远期事件')).toBeNull()
    expect(screen.queryByText('低重要度事件')).toBeNull()
  })

  it('不再出现工程指标（已挪到 /ops）', () => {
    setup()
    render(<OverviewView />)
    expect(screen.queryByText('策略信号与超额胜率')).toBeNull()
    expect(screen.queryByText(/市场基线/)).toBeNull()
    expect(screen.queryByText('最近调度任务')).toBeNull()
  })
})
