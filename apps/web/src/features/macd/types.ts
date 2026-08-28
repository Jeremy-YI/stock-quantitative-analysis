/** 与后端 apps/api/src/schemas/indicator.py 对齐的契约类型。 */

export interface MacdPoint {
  date: string
  close: number
  dif: number
  dea: number
  macd: number
}

export interface MacdBody {
  symbol: string
  series: MacdPoint[]
}

export interface ApiResponse<T> {
  message: string
  body: T | null
}
