/** 事件日历契约（与后端 schemas/market.py 对齐）。 */

export interface EventHistory {
  date: string
  note: string
}

export interface EventItem {
  id: string
  date: string
  name: string
  type: string // 央行会议 / 数据 / 财报
  importance: string // 高 / 中 / 低
  description: string
  history: EventHistory[]
}

export interface EventsBody {
  note: string
  events: EventItem[]
}

export interface EventDetailBody {
  event: EventItem
  note: string
}
