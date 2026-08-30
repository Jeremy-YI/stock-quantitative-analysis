'use client'

/**
 * 个股推荐页：
 * - 选板块 + 选策略 + 选日期
 * - 展示该板块里触发所选策略的股票，按分数降序
 */
import { useState } from 'react'

import { useRecommendations, useSectorList } from './use-recommendations'
import type { Signal } from './types'

// 策略名 → 中文标签（与后端策略 LABEL 一致）
const STRATEGIES: { name: string; label: string }[] = [
  { name: 'b1b2b3', label: '超卖反弹' },
  { name: 'pin30', label: '单针' },
  { name: 'stealth_rally', label: '偷涨' },
  { name: 'double_bottom', label: '双底' },
  { name: 'macd_resonance', label: '月周共振' },
  { name: 'macd_volume_washout', label: '缩量洗盘' },
  { name: 'etf_accumulation', label: 'ETF抄底' },
]

const STRATEGY_LABEL: Record<string, string> = Object.fromEntries(
  STRATEGIES.map((s) => [s.name, s.label])
)

const DEFAULT_DATE = '2026-08-28'

export default function RecommendationView() {
  const sectors = useSectorList()
  const [sector, setSector] = useState('半导体')
  const [strategy, setStrategy] = useState('all')
  const [date, setDate] = useState(DEFAULT_DATE)
  const { data, loading, error } = useRecommendations(sector, date)

  // 先按策略过滤，再按股票分组
  const filtered = data?.signals.filter(
    (s) => strategy === 'all' || s.strategy === strategy
  ) ?? []
  const grouped = new Map<string, Signal[]>()
  filtered.forEach((s) => {
    const arr = grouped.get(s.symbol) ?? []
    arr.push(s)
    grouped.set(s.symbol, arr)
  })
  const stocks = [...grouped.entries()].sort(
    (a, b) => Math.max(...b[1].map((s) => s.score)) - Math.max(...a[1].map((s) => s.score))
  )

  return (
    <main className="p-6 max-w-5xl mx-auto">
      <h1 className="text-2xl font-bold mb-4">个股推荐</h1>

      <div className="mb-5 flex gap-3 items-end flex-wrap">
        <div>
          <label className="block text-sm text-gray-500 mb-1">板块</label>
          <select
            value={sector}
            onChange={(e) => setSector(e.target.value)}
            className="border border-gray-300 rounded px-3 py-1.5 text-sm bg-white"
          >
            {sectors.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label className="block text-sm text-gray-500 mb-1">策略</label>
          <select
            value={strategy}
            onChange={(e) => setStrategy(e.target.value)}
            className="border border-gray-300 rounded px-3 py-1.5 text-sm bg-white"
          >
            <option value="all">全部</option>
            {STRATEGIES.map((s) => (
              <option key={s.name} value={s.name}>
                {s.label}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label className="block text-sm text-gray-500 mb-1">扫描日</label>
          <input
            type="date"
            value={date}
            onChange={(e) => setDate(e.target.value)}
            className="border border-gray-300 rounded px-3 py-1.5 text-sm"
          />
        </div>
      </div>

      {loading && <p className="text-gray-500">扫描中…</p>}
      {error && <p className="text-red-500">加载失败：{error}</p>}

      {data && !loading && (
        <>
          <p className="text-sm text-gray-500 mb-3">
            {data.sector} · {strategy === 'all' ? '全部策略' : STRATEGY_LABEL[strategy]} · {data.date} ·{' '}
            {filtered.length} 条信号 / {stocks.length} 只股票
          </p>
          <table className="w-full text-sm border border-gray-200 rounded-lg overflow-hidden">
            <thead>
              <tr className="bg-gray-50 text-gray-500 text-xs">
                <th className="text-left px-3 py-2">股票</th>
                <th className="text-left px-3 py-2">触发的信号</th>
                <th className="text-right px-3 py-2">最高分</th>
              </tr>
            </thead>
            <tbody>
              {stocks.map(([symbol, sigs]) => (
                <tr key={symbol} className="border-t border-gray-100 hover:bg-gray-50">
                  <td className="px-3 py-2 font-mono font-medium">{symbol}</td>
                  <td className="px-3 py-2">
                    <div className="flex flex-wrap gap-1">
                      {sigs.map((s, i) => (
                        <span
                          key={i}
                          className="text-xs bg-blue-50 text-blue-700 border border-blue-200 rounded px-1.5 py-0.5"
                        >
                          {STRATEGY_LABEL[s.strategy] ?? s.strategy}:{s.signal_type}
                        </span>
                      ))}
                    </div>
                  </td>
                  <td className="px-3 py-2 text-right font-mono">
                    {Math.max(...sigs.map((s) => s.score)).toFixed(0)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
    </main>
  )
}
