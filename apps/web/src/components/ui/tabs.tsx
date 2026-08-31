'use client'

import { cn } from '@/lib/utils'

export interface TabItem {
  value: string
  label: string
}

export interface TabsProps {
  value: string
  onValueChange: (value: string) => void
  items: TabItem[]
  className?: string
}

/**
 * 轻量分段控件（shadcn Tabs 的简化替代，无 Radix 依赖）。
 * 受控组件：value 指定当前选中项，onValueChange 回调切换。
 *
 * 响应式：手机上撑满一行并支持横向滚动（选项多了不会挤成一坨或撑破屏幕），
 * sm 起收成 inline-flex 贴合内容宽度。
 */
export default function Tabs({
  value,
  onValueChange,
  items,
  className,
}: TabsProps) {
  return (
    <div
      role="tablist"
      className={cn(
        'flex w-full max-w-full items-center gap-1 overflow-x-auto overscroll-x-contain rounded-lg bg-muted p-1',
        'mobile-portrait:inline-flex mobile-portrait:w-auto',
        className
      )}
    >
      {items.map((item) => {
        const active = item.value === value
        return (
          <button
            key={item.value}
            role="tab"
            type="button"
            aria-selected={active}
            data-active={active || undefined}
            onClick={() => onValueChange(item.value)}
            className={cn(
              'shrink-0 whitespace-nowrap rounded-md px-3 py-1.5 text-body-sm font-medium transition-colors mobile-portrait:px-4',
              active
                ? 'bg-background text-foreground shadow-sm'
                : 'text-muted-foreground hover:text-foreground'
            )}
          >
            {item.label}
          </button>
        )
      })}
    </div>
  )
}
