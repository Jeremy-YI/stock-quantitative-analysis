/**
 * 长 class 组合集中到这里（对应 STYLE：拆 xxx-styles.ts，导出命名常量字符串），
 * 组件里引用常量，不内联一长串 class。
 */

export const pageWrapper = 'flex min-h-screen flex-col items-center gap-6 bg-background p-6'

export const header = 'flex w-full max-w-4xl items-end justify-between'

export const pageTitle = 'text-2xl font-semibold'

export const form = 'flex w-full max-w-4xl flex-wrap items-end gap-3'

export const field = 'flex w-64 flex-col gap-1.5'

export const chartCard = 'w-full max-w-4xl'

export const chartContainer = 'h-[520px] w-full'

export const legendHint = 'flex items-center gap-4 text-sm text-muted-foreground'
