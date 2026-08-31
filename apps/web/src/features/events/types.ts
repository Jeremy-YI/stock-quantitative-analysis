/** 事件日历契约（与后端 schemas/market.py 对齐）。 */

export interface EventItem {
  date: string
  name: string
  type: string // 央行会议 / 数据 / 财报
  importance: string // 高 / 中 / 低
}

export interface EventsBody {
  note: string
  events: EventItem[]
}
