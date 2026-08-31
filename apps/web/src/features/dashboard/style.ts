/**
 * 概览页共享样式。
 *
 * 全部基于设计系统令牌（text-h1 / bg-surface / gap 响应式），不写死宽度：
 * pageWrapper 自己就是容器（max-w 是上限不是固定宽），子块一律 w-full。
 */

export const pageWrapper =
  'mx-auto flex w-full max-w-[75rem] flex-col gap-4 px-4 py-5 mobile-portrait:gap-6 mobile-portrait:px-6 mobile-portrait:py-7 desktop:px-8 desktop:py-8'

export const header =
  'flex w-full flex-col gap-2 mobile-landscape:flex-row mobile-landscape:items-end mobile-landscape:justify-between'

export const pageTitle = 'text-h1'

export const sectionTitle = 'text-h4 text-muted-foreground'

export const grid =
  'grid w-full grid-cols-1 gap-3 mobile-portrait:gap-4 mobile-landscape:grid-cols-2'

export const card = 'w-full'

export const strategyCard =
  'flex flex-col gap-2 rounded-lg border border-border bg-card p-3 text-card-foreground mobile-portrait:p-4'

export const strategyName = 'text-h4'

export const strategyDesc = 'line-clamp-2 text-caption text-muted-foreground'

export const metricRow = 'flex items-baseline justify-between gap-2'

export const metricLabel = 'text-caption text-muted-foreground'

export const metricValue = 'text-h4 font-semibold tabular-nums'

export const statGrid = 'grid w-full grid-cols-2 gap-2.5 mobile-portrait:gap-3 desktop:grid-cols-4'

export const statCard = 'rounded-lg border border-border bg-card p-3 text-card-foreground'

export const statLabel = 'text-caption text-muted-foreground'

export const statValue = 'mt-1 text-h3 font-semibold tabular-nums'

/** 表格必须套一层横滚容器，小屏不顶宽整页。 */
export const tableWrap = 'w-full max-w-full overflow-x-auto'

export const baselineTable = 'w-full min-w-[20rem] text-body-sm tabular-nums'

export const th =
  'px-2 py-1.5 text-left text-caption font-medium whitespace-nowrap text-muted-foreground'

export const td = 'px-2 py-1.5 text-body-sm'

export const runRow =
  'flex flex-col gap-0.5 border-b border-border py-2 text-body-sm last:border-0 mobile-portrait:flex-row mobile-portrait:items-center mobile-portrait:justify-between mobile-portrait:gap-3'

export const runJob = 'font-medium'

export const runTime = 'text-caption text-muted-foreground'

export const emptyHint = 'py-8 text-center text-body-sm text-muted-foreground'

export const navGrid =
  'grid w-full grid-cols-2 gap-2.5 mobile-portrait:grid-cols-3 mobile-portrait:gap-3 desktop:grid-cols-4'

export const navCard =
  'flex flex-col gap-1 rounded-lg border border-border bg-card p-3 text-card-foreground transition-colors hover:bg-surface-hover mobile-portrait:p-4'

export const navTitle = 'text-h4'

export const navDesc = 'text-caption text-muted-foreground'
