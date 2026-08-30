'use client'

/**
 * 个股推荐页：
 * - 选板块（下拉）+ 选日期
 * - 展示该板块成分股触发的战法信号，按股票分组、按分数降序
 */
import { useState } from 'react'

import { useRecommendations, useSectorList } from './use-recommendations'
import type { Signal } from './types'

// 策略名 → 中文标签（展示用）
const STRATEGY_LABEL: Record<string, string> = {
  b1b2b3: 'B1/B2/B3',
  pin30: '单针',
  double_bottom: '双底背离',
  stealth_rally: '偷涨',
  macd_volume_washout: '暴跌洗盘',
  macd_resonance: 'MACD共振',
  etf_accumulation: 'ETF积累',
}

const DEFAULT_DATE = '2026-08-28'

export default function RecommendationView() {
  const sectors = useSectorList()
  const [sector, setSector] = useState('半导体')
  const [date, setDate] = useState(DEFAULT_DATE)
  const { data, loading, error } = useRecommendations(sector, date)

  // 按股票分组：{ symbol: Signal[] }
  const grouped = new Map<string, Signal[]>()
  data?.signals.forEach((s) => {
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

      <div className="mb-5 flex gap-3 items-end">
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
            {data.sector} · {data.date} · {data.signals.length} 条信号 / {stocks.length} 只股票
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
