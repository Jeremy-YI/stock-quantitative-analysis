/** 定价线契约（与后端 apps/api/src/schemas/indicator.py 对齐）。 */

export interface PricingLinePoint {
  date: string
  close: number
  lifeline: number | null          // 生命线
  yin_volume_line: number | null   // 阴量定价线
  attack_defense: number | null    // 进攻K防线
}

export interface PricingLinesBody {
  symbol: string
  series: PricingLinePoint[]
}
