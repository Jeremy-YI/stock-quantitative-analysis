/**
 * Color —— 语义色的 TS 侧映射。
 *
 * 规则：业务代码只用 tone（'up' / 'down' / 'accent' …），不写 text-red-600 这种调色板类。
 * 真实色值在 globals.css（工具类）和 styles/colors.ts（ECharts）里，这里只做 tone → class。
 */

export type Tone =
  'default' | 'muted' | 'accent' | 'up' | 'down' | 'neutral' | 'warn' | 'danger' | 'info'

/** 文字色。 */
export const TEXT_TONE: Record<Tone, string> = {
  default: 'text-foreground',
  muted: 'text-muted-foreground',
  accent: 'text-accent',
  up: 'text-up',
  down: 'text-down',
  neutral: 'text-neutral',
  warn: 'text-warn',
  danger: 'text-danger',
  info: 'text-info',
}

/** 浅底 + 描边（徽标、提示条）。 */
export const SOFT_TONE: Record<Tone, string> = {
  default: 'bg-surface text-foreground border-border',
  muted: 'bg-muted text-muted-foreground border-border',
  accent: 'bg-accent-soft text-accent border-accent-border',
  up: 'bg-up-soft text-up border-up/30',
  down: 'bg-down-soft text-down border-down/30',
  neutral: 'bg-surface text-neutral border-border',
  warn: 'bg-warn-soft text-warn border-warn-border',
  danger: 'bg-danger-soft text-danger border-danger-border',
  info: 'bg-info-soft text-info border-info-border',
}

/** 实底（主按钮、强调标签）。 */
export const SOLID_TONE: Record<Tone, string> = {
  default: 'bg-primary text-primary-foreground',
  muted: 'bg-muted text-muted-foreground',
  accent: 'bg-accent text-accent-foreground',
  up: 'bg-up text-white',
  down: 'bg-down text-white',
  neutral: 'bg-neutral text-white',
  warn: 'bg-warn text-white',
  danger: 'bg-danger text-white',
  info: 'bg-info text-white',
}

/** 涨跌 → tone（A股口径：正红负绿，0/空为中性）。 */
export function toneForChange(value: number | null | undefined): Tone {
  if (value === null || value === undefined || Number.isNaN(value)) return 'neutral'
  if (value > 0) return 'up'
  if (value < 0) return 'down'
  return 'neutral'
}

/** 涨跌 → 文字色类，最常用的一行。 */
export function changeTextClass(value: number | null | undefined): string {
  return TEXT_TONE[toneForChange(value)]
}

/** 任务/请求状态 → tone。 */
export function toneForStatus(status: string | null | undefined): Tone {
  switch (status) {
    case 'success':
      return 'up'
    case 'failed':
    case 'timeout':
      return 'down'
    case 'running':
      return 'accent'
    default:
      return 'neutral'
  }
}
