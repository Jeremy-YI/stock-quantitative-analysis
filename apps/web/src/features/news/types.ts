/** 最新消息契约（与后端 schemas/market.py 对齐）。 */

export interface NewsItem {
  title: string
  impact: string // 改变定价 / 显著影响 / 结构性关注
  level: string // P0 / P1 / P2
  outlook: string // 未来导向
  sources: number // 来源数
}

export interface NewsBody {
  date: string
  source: string
  items: NewsItem[]
}
