/** 最新消息契约（与后端 schemas/market.py 对齐）。 */

export interface RelatedSymbol {
  symbol: string
  name: string
  reason: string
}

export interface NewsItem {
  id: string
  title: string
  impact: string // 改变定价 / 显著影响 / 结构性关注
  level: string // P0 / P1 / P2
  outlook: string // 未来导向
  sources: number // 来源数
  detail: string // 详细解读
  topics: string[]
  related_symbols: RelatedSymbol[]
}

export interface NewsBody {
  date: string
  source: string
  items: NewsItem[]
}

export interface NewsDetailBody {
  item: NewsItem
  date: string
  source: string
  related_news: NewsItem[]
}
