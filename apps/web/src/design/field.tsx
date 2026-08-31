/**
 * Field / Select / FilterBar —— 表单控件。
 *
 * 响应式重点：
 *  - 控件高度手机 40px、md 起 36px（触屏可点，桌面紧凑）
 *  - 控件宽度默认撑满父容器，由 FilterBar 决定列数，不写死 px
 *  - FilterBar 在手机是两列栅格、sm 起变成一行 flex（筛选条不再挤成一坨）
 *
 *   <FilterBar>
 *     <Field label="板块"><Select value=… onChange=…>…</Select></Field>
 *     <Field label="扫描日"><TextInput type="date" … /></Field>
 *   </FilterBar>
 */
import * as React from 'react'

import { cn } from '@/lib/utils'

import { Text } from './typography'

/* -------------------------------- Field ------------------------------- */

export interface FieldProps extends React.HTMLAttributes<HTMLDivElement> {
  label?: React.ReactNode
  htmlFor?: string
  hint?: React.ReactNode
  /** 让该项在栅格里占满整行（手机上长输入用） */
  wide?: boolean
}

export function Field({
  label,
  htmlFor,
  hint,
  wide = false,
  className,
  children,
  ...rest
}: FieldProps) {
  return (
    <div
      className={cn('flex min-w-0 flex-col gap-1', wide && 'col-span-2 mobile-portrait:col-span-1', className)}
      {...rest}
    >
      {label ? (
        <label htmlFor={htmlFor} className="text-caption font-medium text-muted-foreground">
          {label}
        </label>
      ) : null}
      {children}
      {hint ? (
        <Text size="caption" tone="muted">
          {hint}
        </Text>
      ) : null}
    </div>
  )
}

/* ------------------------------ FilterBar ----------------------------- */

/** 筛选条：手机两列栅格，sm 起一行 flex 自动换行。 */
export function FilterBar({ className, ...rest }: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn(
        'grid grid-cols-2 gap-3 mobile-portrait:flex mobile-portrait:flex-wrap mobile-portrait:items-end mobile-portrait:gap-3',
        className
      )}
      {...rest}
    />
  )
}

/* ------------------------- 控件基础样式（共享） ------------------------ */

const controlBase = [
  'w-full min-w-0 rounded-md border border-border bg-background',
  'h-10 px-3 text-body-sm mobile-landscape:h-9',
  'transition-colors placeholder:text-muted-foreground',
  'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
  'disabled:cursor-not-allowed disabled:opacity-50',
].join(' ')

export const TextInput = React.forwardRef<
  HTMLInputElement,
  React.InputHTMLAttributes<HTMLInputElement>
>(({ className, ...props }, ref) => (
  <input ref={ref} className={cn(controlBase, className)} {...props} />
))
TextInput.displayName = 'TextInput'

export const Select = React.forwardRef<
  HTMLSelectElement,
  React.SelectHTMLAttributes<HTMLSelectElement>
>(({ className, ...props }, ref) => (
  <select
    ref={ref}
    className={cn(controlBase, 'appearance-none bg-background pr-8', className)}
    style={{
      // 原生 select 的箭头在各平台不一致，用背景图统一（不引额外依赖）
      backgroundImage:
        "url(\"data:image/svg+xml;charset=utf-8,%3Csvg xmlns='http://www.w3.org/2000/svg' width='16' height='16' viewBox='0 0 16 16' fill='none' stroke='%2371717a' stroke-width='1.5'%3E%3Cpath d='M4 6l4 4 4-4'/%3E%3C/svg%3E\")",
      backgroundRepeat: 'no-repeat',
      backgroundPosition: 'right 0.5rem center',
    }}
    {...props}
  />
))
Select.displayName = 'Select'

export { controlBase }
