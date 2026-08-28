/**
 * 指标页共享样式（长 class 组合集中到这里，组件里引用常量）。
 * 由 MACD 单页改造为多指标切换后，form/card/图表容器四个指标共用。
 */

export const pageWrapper =
  'flex min-h-screen flex-col items-center gap-6 bg-background p-6'

export const header = 'flex w-full max-w-4xl items-end justify-between'

export const pageTitle = 'text-2xl font-semibold'

export const form = 'flex w-full max-w-4xl flex-wrap items-end gap-3'

export const field = 'flex w-64 flex-col gap-1.5'

export const chartCard = 'w-full max-w-4xl'

export const chartContainer = 'h-[520px] w-full'

export const legendHint = 'flex items-center gap-4 text-sm text-muted-foreground'

export const tabsRow = 'flex w-full max-w-4xl'
