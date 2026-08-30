'use client'

/**
 * 事件日历页：关键会议 / 数据 / 财报，按日期升序，重要度徽标。
 */
import useEvents from './use-events'
import type { EventItem } from './types'

// 重要度 → 徽标配色
const IMPORTANCE_STYLE: Record<string, string> = {
  高: 'bg-red-50 text-red-700 border-red-200',
  中: 'bg-amber-50 text-amber-700 border-amber-200',
  低: 'bg-gray-50 text-gray-600 border-gray-200',
}

// 类型 → 标签
const TYPE_LABEL: Record<string, string> = {
  央行会议: '央行会议',
  数据: '数据',
  财报: '财报',
}

export default function EventsView() {
  const { data, loading, error } = useEvents()

  return (
    <main className="p-6 max-w-3xl mx-auto">
      <h1 className="text-2xl font-bold mb-1">事件日历</h1>
      {data && <p className="text-sm text-gray-500 mb-5">{data.note}</p>}

      {loading && <p className="text-gray-500">加载中…</p>}
      {error && <p className="text-red-500">加载失败：{error}</p>}

      {data && (
        <div className="border border-gray-200 rounded-lg overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-gray-50 text-gray-500 text-xs">
                <th className="text-left px-3 py-2 w-32">日期</th>
                <th className="text-left px-3 py-2">事件</th>
                <th className="text-left px-3 py-2 w-20">类型</th>
                <th className="text-left px-3 py-2 w-16">重要度</th>
              </tr>
            </thead>
            <tbody>
              {data.events.map((e, i) => (
                <EventRow key={i} event={e} />
              ))}
            </tbody>
          </table>
        </div>
      )}
    </main>
  )
}

function EventRow({ event }: { event: EventItem }) {
  return (
    <tr className="border-t border-gray-100 hover:bg-gray-50">
      <td className="px-3 py-2 font-mono text-gray-700">{event.date}</td>
      <td className="px-3 py-2 font-medium">{event.name}</td>
      <td className="px-3 py-2">
        <span className="text-xs bg-gray-100 text-gray-600 rounded px-1.5 py-0.5">
          {TYPE_LABEL[event.type] ?? event.type}
        </span>
      </td>
      <td className="px-3 py-2">
        <span className={`text-xs border rounded px-1.5 py-0.5 ${IMPORTANCE_STYLE[event.importance] ?? ''}`}>
          {event.importance}
        </span>
      </td>
    </tr>
  )
}
