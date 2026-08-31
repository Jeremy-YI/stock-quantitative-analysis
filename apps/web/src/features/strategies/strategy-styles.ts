/** 选股看板共享样式（设计系统令牌 + 响应式，不写死宽度）。 */

export const pageWrapper =
  'mx-auto flex w-full max-w-[75rem] flex-col gap-4 px-4 py-5 mobile-portrait:gap-6 mobile-portrait:px-6 mobile-portrait:py-7 desktop:px-8 desktop:py-8'

export const header =
  'flex w-full flex-col gap-2 mobile-landscape:flex-row mobile-landscape:items-end mobile-landscape:justify-between'

export const pageTitle = 'text-h1'

export const form = 'grid w-full grid-cols-2 gap-3 mobile-portrait:flex mobile-portrait:flex-wrap mobile-portrait:items-end'

export const field = 'flex min-w-0 flex-col gap-1.5'

export const tableCard = 'w-full'

export const tableWrap = 'w-full max-w-full overflow-x-auto overscroll-x-contain'

export const th =
  'cursor-pointer select-none whitespace-nowrap px-3 py-2 text-left text-body-sm font-medium text-muted-foreground hover:text-foreground'

export const td = 'px-3 py-2 text-body-sm'

export const rowHover = 'cursor-pointer hover:bg-surface-hover'

export const emptyHint = 'py-10 text-center text-body-sm text-muted-foreground'
