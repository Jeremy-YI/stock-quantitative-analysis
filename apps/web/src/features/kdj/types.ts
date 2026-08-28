/** 与后端 apps/api/src/schemas/indicator.py 对齐的 KDJ 契约类型。 */

export interface KdjPoint {
  date: string
  close: number
  k: number
  d: number
  j: number
}

export interface KdjBody {
  symbol: string
  series: KdjPoint[]
}
