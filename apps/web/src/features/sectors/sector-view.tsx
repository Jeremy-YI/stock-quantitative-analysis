'use client'

/**
 * 板块资金页：
 * - 上半：窗口选择（即时 / 3日 / 5日 / 10日 / 20日）
 * - 主区：左侧 Top20 资金流入，右侧 Top20 资金流出
 * 每行显示：行业名、净额（亿，红涨绿跌）、行业涨跌幅、领涨股。
 */
import { useState } from 'react'
import Link from 'next/link'

import useSectors from './use-sectors'
import type { SectorFlow } from './types'

const DAYS = ['即时', '3日排行', '5日排行', '10日排行', '20日排行']

export default function SectorView() {
  const [days, setDays] = useState('即时')
  const { data, loading, error } = useSectors(days)

  return (
    <div className="p-6 max-w-5xl mx-auto">
      <h1 className="text-2xl font-bold mb-4">板块资金</h1>

      {/* 窗口选择 */}
      <div className="mb-5 flex gap-2">
        {DAYS.map((d) => (
          <button
            key={d}
            onClick={() => setDays(d)}
            className={`px-4 py-1.5 rounded text-sm border ${
              days === d
                ? 'bg-blue-600 text-white border-blue-600'
                : 'bg-white text-gray-700 border-gray-300 hover:bg-gray-50'
            }`}
          >
            {d}
          </button>
        ))}
      </div>

      {loading && <p className="text-gray-500">加载中…</p>}
      {error && <p className="text-red-500">加载失败：{error}</p>}

      {data && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <FlowColumn title="Top20 资金流入" rows={data.top_inflow} positive />
          <FlowColumn title="Top20 资金流出" rows={data.top_outflow} positive={false} />
        </div>
      )}
    </div>
  )
}

/** 一列（流入或流出）的排行表。 */
function FlowColumn({
  title,
  rows,
  positive,
}: {
  title: string
  rows: SectorFlow[]
  positive: boolean
}) {
  return (
    <div className="rounded-lg border border-gray-200 overflow-hidden">
      <h2 className="bg-gray-50 px-4 py-2 font-semibold text-sm border-b border-gray-200">
        {title}
      </h2>
      <table className="w-full text-sm">
        <thead>
          <tr className="text-gray-500 text-xs border-b border-gray-100">
            <th className="text-left px-3 py-2">行业</th>
            <th className="text-right px-3 py-2">净额(亿)</th>
            <th className="text-right px-3 py-2">涨跌幅</th>
            <th className="text-left px-3 py-2">领涨股</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((s) => (
            <tr key={s.sector} className="border-b border-gray-50 hover:bg-gray-50">
              <td className="px-3 py-1.5 font-medium">
                <Link
                  href={`/recommendations?sector=${encodeURIComponent(s.sector)}`}
                  className="text-blue-700 hover:underline"
                  title="点开看成分股 + 信号"
                >
                  {s.sector}
                </Link>
              </td>
              <td className={`px-3 py-1.5 text-right font-mono ${s.net >= 0 ? 'text-red-600' : 'text-green-600'}`}>
                {s.net >= 0 ? '+' : ''}
                {s.net.toFixed(2)}
              </td>
              <td className={`px-3 py-1.5 text-right ${s.change_pct >= 0 ? 'text-red-600' : 'text-green-600'}`}>
                {s.change_pct >= 0 ? '+' : ''}
                {s.change_pct.toFixed(2)}%
              </td>
              <td className="px-3 py-1.5 text-gray-600">
                {s.leader}
                <span className="text-red-600 ml-1">{s.leader_pct > 0 ? `+${s.leader_pct.toFixed(2)}%` : ''}</span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
