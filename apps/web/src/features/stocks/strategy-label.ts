/** 策略名 → 中文短标签（与后端策略 LABEL 一致，前端多处复用）。 */

export const STRATEGIES: { name: string; label: string }[] = [
  { name: 'b1b2b3', label: '超卖反弹' },
  { name: 'pin30', label: '单针' },
  { name: 'stealth_rally', label: '偷涨' },
  { name: 'double_bottom', label: '双底' },
  { name: 'macd_resonance', label: '月周共振' },
  { name: 'macd_volume_washout', label: '缩量洗盘' },
  { name: 'etf_accumulation', label: 'ETF抄底' },
]

export const STRATEGY_LABEL: Record<string, string> = Object.fromEntries(
  STRATEGIES.map((s) => [s.name, s.label]),
)

export function strategyLabel(name: string): string {
  return STRATEGY_LABEL[name] ?? name
}
