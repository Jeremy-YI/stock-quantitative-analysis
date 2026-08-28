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
        'inline-flex items-center gap-1 rounded-lg bg-muted p-1',
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
              'rounded-md px-4 py-1.5 text-sm font-medium transition-colors',
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
