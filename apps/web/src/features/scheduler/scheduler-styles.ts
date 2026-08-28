/** 调度器看板共享样式。 */

export const pageWrapper =
  'flex min-h-screen flex-col items-center gap-6 bg-background p-6'

export const header = 'flex w-full max-w-6xl items-end justify-between'

export const pageTitle = 'text-2xl font-semibold'

export const cardWrap = 'w-full max-w-6xl'

export const tableWrap = 'w-full overflow-x-auto'

export const th =
  'cursor-pointer select-none px-3 py-2 text-left text-sm font-medium text-muted-foreground hover:text-foreground'

export const td = 'px-3 py-2 text-sm'

export const rowHover = 'hover:bg-muted/60'

export const emptyHint = 'py-10 text-center text-sm text-muted-foreground'

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
