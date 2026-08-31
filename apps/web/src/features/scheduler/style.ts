/** 调度器看板共享样式。 */

export const pageWrapper =
  'mx-auto flex w-full max-w-[75rem] flex-col gap-4 px-4 py-5 mobile-portrait:gap-6 mobile-portrait:px-6 mobile-portrait:py-7 desktop:px-8 desktop:py-8'

export const header =
  'flex w-full flex-col gap-2 mobile-landscape:flex-row mobile-landscape:items-end mobile-landscape:justify-between'

export const pageTitle = 'text-h1'

export const cardWrap = 'w-full'

export const tableWrap = 'w-full max-w-full overflow-x-auto overscroll-x-contain'

export const th =
  'cursor-pointer select-none whitespace-nowrap px-3 py-2 text-left text-body-sm font-medium text-muted-foreground hover:text-foreground'

export const td = 'px-3 py-2 text-body-sm'

export const rowHover = 'hover:bg-surface-hover'

export const emptyHint = 'py-10 text-center text-body-sm text-muted-foreground'

/** 状态徽标：成功/失败/超时/跳过 → 语义色（复用 @theme 的 up/down/neutral）。 */
export function statusClass(status: string | null): string {
  switch (status) {
    case 'success':
      return 'text-up'
    case 'failed':
    case 'timeout':
      return 'text-down'
    case 'skipped':
      return 'text-neutral'
    default:
      return 'text-neutral'
  }
}

export function statusLabel(status: string | null): string {
  switch (status) {
    case 'success':
      return '成功'
    case 'failed':
      return '失败'
    case 'timeout':
      return '超时'
    case 'skipped':
      return '跳过'
    default:
      return status ?? '—'
  }
}
