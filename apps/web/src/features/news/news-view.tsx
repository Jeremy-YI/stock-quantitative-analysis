'use client'

/**
 * 最新消息页（财经日报式）：
 * 每条消息 = 标题 + 影响评级徽标 + 未来导向 + 来源数。
 */
import useNews from './use-news'
import type { NewsItem } from './types'

// 影响评级 → 徽标配色
const IMPACT_STYLE: Record<string, string> = {
  改变定价: 'bg-red-50 text-red-700 border-red-200',
  显著影响: 'bg-amber-50 text-amber-700 border-amber-200',
  结构性关注: 'bg-blue-50 text-blue-700 border-blue-200',
}

export default function NewsView() {
  const { data, loading, error } = useNews()

  return (
    <main className="p-6 max-w-3xl mx-auto">
      <h1 className="text-2xl font-bold mb-1">最新消息</h1>
      {data && <p className="text-sm text-gray-500 mb-5">{data.date} · {data.source}</p>}

      {loading && <p className="text-gray-500">加载中…</p>}
      {error && <p className="text-red-500">加载失败：{error}</p>}

      {data && (
        <div className="space-y-4">
          {data.items.map((item, i) => (
            <NewsCard key={i} item={item} />
          ))}
        </div>
      )}
    </main>
  )
}

function NewsCard({ item }: { item: NewsItem }) {
  return (
    <div className="border border-gray-200 rounded-lg p-4 hover:bg-gray-50">
      <div className="flex items-start justify-between gap-3">
        <h2 className="font-medium text-[15px]">{item.title}</h2>
        <span
          className={`shrink-0 text-xs border rounded px-2 py-0.5 ${IMPACT_STYLE[item.impact] ?? 'bg-gray-50 text-gray-600 border-gray-200'}`}
        >
          {item.impact}
        </span>
      </div>
      <p className="text-sm text-gray-600 mt-2">
        <span className="text-gray-400">未来导向：</span>
        {item.outlook}
      </p>
      <p className="text-xs text-gray-400 mt-1.5">来源 {item.sources} 条</p>
    </div>
  )
}
