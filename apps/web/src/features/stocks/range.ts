/**
 * 图表周期（交易日口径）。
 *
 * 为什么默认 2 个月：一屏看几年的日线毫无意义（形态全糊成一团），
 * 短线决策看的是最近 1~2 个月的结构；要看更长用户自己切或在图上缩放。
 * 指标一律用全量历史计算，这里只控制**显示窗口**。
 */

export interface RangeOption {
  value: string
  label: string
  /** 交易日数量；0 = 全部 */
  limit: number
}

export const RANGE_OPTIONS: RangeOption[] = [
  { value: '1m', label: '1个月', limit: 22 },
  { value: '2m', label: '2个月', limit: 44 },
  { value: '3m', label: '3个月', limit: 66 },
  { value: '6m', label: '6个月', limit: 125 },
  { value: '1y', label: '1年', limit: 250 },
  { value: 'all', label: '全部', limit: 0 },
]

/** 默认 2 个月 */
export const DEFAULT_RANGE = '2m'

export function rangeLimit(value: string): number | undefined {
  const found = RANGE_OPTIONS.find((r) => r.value === value)
  return found && found.limit > 0 ? found.limit : undefined
}
