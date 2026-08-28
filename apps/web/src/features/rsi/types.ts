/** 与后端 apps/api/src/schemas/indicator.py 对齐的 RSI 契约类型。 */

export interface RsiPoint {
  date: string
  close: number
  rsi: number
}

export interface RsiBody {
  symbol: string
  series: RsiPoint[]
}
