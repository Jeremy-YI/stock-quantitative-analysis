/**
 * 指标页共享样式。基于设计系统令牌，宽度不写死：
 * pageWrapper 自己是容器（max-w 是上限），图表高度按断点给三档。
 */

export const pageWrapper =
  'mx-auto flex w-full max-w-[75rem] flex-col gap-4 px-4 py-5 mobile-portrait:gap-6 mobile-portrait:px-6 mobile-portrait:py-7 desktop:px-8 desktop:py-8'

export const header =
  'flex w-full flex-col gap-2 mobile-landscape:flex-row mobile-landscape:items-end mobile-landscape:justify-between'

export const pageTitle = 'text-h1'

/** 手机两列栅格、sm 起一行 flex（与设计系统 FilterBar 一致） */
export const form =
  'grid w-full grid-cols-2 gap-3 mobile-portrait:flex mobile-portrait:flex-wrap mobile-portrait:items-end'

export const field = 'flex min-w-0 w-full flex-col gap-1.5 mobile-portrait:w-56'

export const chartCard = 'w-full'

/** 图表高度：手机 280 → 平板 380 → 桌面 520（ECharts 需要具体高度） */
export const chartContainer = 'h-[280px] w-full mobile-portrait:h-[380px] desktop:h-[520px]'

export const legendHint =
  'flex flex-wrap items-center gap-x-4 gap-y-1 text-body-sm text-muted-foreground'

export const tabsRow = 'flex w-full'
