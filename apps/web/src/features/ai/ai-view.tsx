'use client'

/**
 * AI 解读 demo 页：
 * 输入股票代码 + 日期 → 点「AI 解读」→ 后端扫信号 → LLM 生成自然语言解读。
 */
import { useState } from 'react'

import { useInterpret } from './use-interpret'

export default function AiView() {
  const [symbol, setSymbol] = useState('600519')
  const [date, setDate] = useState('2026-08-28')
  const { result, loading, error, interpret } = useInterpret()

  return (
    <main className="p-6 max-w-3xl mx-auto">
      <h1 className="text-2xl font-bold mb-4">AI 解读（demo）</h1>

      <div className="mb-5 flex gap-3 items-end">
        <div>
          <label className="block text-sm text-gray-500 mb-1">股票代码</label>
          <input
            value={symbol}
            onChange={(e) => setSymbol(e.target.value)}
            placeholder="6 位代码，如 600519"
            maxLength={6}
            className="border border-gray-300 rounded px-3 py-1.5 text-sm"
          />
        </div>
        <div>
          <label className="block text-sm text-gray-500 mb-1">日期</label>
          <input
            type="date"
            value={date}
            onChange={(e) => setDate(e.target.value)}
            className="border border-gray-300 rounded px-3 py-1.5 text-sm"
          />
        </div>
        <button
          onClick={() => interpret(symbol, date)}
          disabled={loading}
          className="bg-blue-600 text-white rounded px-4 py-1.5 text-sm disabled:opacity-50"
        >
          {loading ? '解读中…' : 'AI 解读'}
        </button>
      </div>

      {error && <p className="text-red-500 mb-3">解读失败：{error}</p>}

      {result && (
        <div className="border border-gray-200 rounded-lg p-4">
          <h2 className="font-semibold mb-2">解读结果（{result.symbol}）</h2>
          <p className="text-[15px] leading-relaxed whitespace-pre-wrap">{result.interpretation}</p>

          <h3 className="font-medium text-sm text-gray-500 mt-4 mb-1">触发的信号：</h3>
          <div className="flex flex-wrap gap-1.5">
            {result.signals.map((s, i) => (
              <span key={i} className="text-xs bg-blue-50 text-blue-700 border border-blue-200 rounded px-1.5 py-0.5">
                {s.strategy}:{s.signal_type}（{s.score.toFixed(0)}）
              </span>
            ))}
          </div>
        </div>
      )}
    </main>
  )
}
