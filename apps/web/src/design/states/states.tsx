'use client'

/**
 * States —— 加载 / 空 / 错误 三种页面状态的正式组件。
 *
 * 设计原则（对齐金融终端风格，不用 emoji、不做花哨动画）：
 *  - 加载：细环 spinner + 一行正在做的事（带动态省略号），长列表再叠骨架行
 *  - 空：一个克制的图标 + 标题 + 一句解释 + 可选操作，别让「下面空着」变成留白
 *  - 错误：一条能看懂的话 + 可选重试
 *
 *   <LoadingState label='AI 正在扫描「半导体」' skeleton />
 *   <EmptyState title='还没有解读结果' description='输入股票代码，AI 解读当日战法信号' />
 *   <ErrorState message={error} onRetry={...} />
 */
import * as React from 'react'

import { cn } from '@/lib/utils'

/* ------------------------------- Spinner ------------------------------- */

/** 细环 spinner（纯 CSS，无第三方依赖）。 */
export function Spinner({ className }: { className?: string }) {
  return (
    <span
      aria-hidden
      className={cn(
        'inline-block size-4 animate-spin rounded-full border-2 border-muted-foreground/20 border-t-muted-foreground',
        className,
      )}
    />
  )
}

/* ----------------------------- LoadingState ---------------------------- */

export interface LoadingStateProps {
  /** 正在做的事，省略号会自动补 */
  label: string
  /** 是否叠一排骨架行（表格加载用） */
  skeleton?: boolean
  /** 骨架行数 */
  rows?: number
  className?: string
}

export function LoadingState({ label, skeleton = false, rows = 3, className }: LoadingStateProps) {
  return (
    <div className={cn('flex flex-col gap-3', className)} role='status' aria-live='polite'>
      <div className='flex items-center gap-2.5 text-body-sm text-muted-foreground'>
        <Spinner />
        <span>{label}</span>
        <AnimatedDots />
      </div>
      {skeleton && (
        <div className='space-y-2'>
          {Array.from({ length: rows }, (_, i) => (
            <div
              key={i}
              className='h-9 animate-pulse rounded-md bg-muted'
              style={{ opacity: 1 - i * 0.12 }}
            />
          ))}
        </div>
      )}
    </div>
  )
}

/** 三个点循环淡入的省略号（比静态「…」更像在干活）。 */
function AnimatedDots() {
  return (
    <span className='inline-flex gap-0.5 text-muted-foreground'>
      {[0, 1, 2].map((i) => (
        <span key={i} className='animate-pulse' style={{ animationDelay: `${i * 200}ms` }}>
          .
        </span>
      ))}
    </span>
  )
}

/* ------------------------------ EmptyState ----------------------------- */

export interface EmptyStateProps {
  title: string
  description?: string
  action?: React.ReactNode
  className?: string
  compact?: boolean
}

export function EmptyState({
  title,
  description,
  action,
  className,
  compact = false,
}: EmptyStateProps) {
  return (
    <div
      className={cn(
        'flex flex-col items-center justify-center rounded-lg border border-dashed border-border bg-surface/50 text-center',
        compact ? 'px-4 py-8' : 'px-6 py-12',
        className,
      )}
    >
      <span className='flex size-10 items-center justify-center rounded-full border border-border bg-background'>
        <EmptyIcon className='size-5 text-muted-foreground' />
      </span>
      <p className={cn('mt-3 font-medium', compact ? 'text-body-sm' : 'text-body')}>{title}</p>
      {description && (
        <p className='mt-1 max-w-sm text-caption text-muted-foreground'>{description}</p>
      )}
      {action && <div className='mt-4'>{action}</div>}
    </div>
  )
}

function EmptyIcon({ className }: { className?: string }) {
  return (
    <svg viewBox='0 0 24 24' fill='none' className={className} aria-hidden>
      <path
        d='M4 6h16M4 12h16M4 18h10'
        stroke='currentColor'
        strokeWidth='1.5'
        strokeLinecap='round'
      />
    </svg>
  )
}

/* ------------------------------ ErrorState ----------------------------- */

export interface ErrorStateProps {
  message: string
  onRetry?: () => void
  className?: string
}

export function ErrorState({ message, onRetry, className }: ErrorStateProps) {
  return (
    <div
      role='alert'
      className={cn(
        'flex flex-col items-center justify-center gap-3 rounded-lg border border-danger-border bg-danger-soft px-6 py-8 text-center',
        className,
      )}
    >
      <span className='flex size-10 items-center justify-center rounded-full border border-danger-border bg-background'>
        <svg viewBox='0 0 24 24' fill='none' className='size-5 text-danger' aria-hidden>
          <path
            d='M12 8v5M12 16.5v.5'
            stroke='currentColor'
            strokeWidth='1.8'
            strokeLinecap='round'
          />
          <circle cx='12' cy='12' r='9' stroke='currentColor' strokeWidth='1.5' />
        </svg>
      </span>
      <p className='max-w-sm text-body-sm text-danger'>{message}</p>
      {onRetry && (
        <button
          type='button'
          onClick={onRetry}
          className='rounded-md border border-danger-border px-3 py-1.5 text-body-sm text-danger hover:bg-danger-soft'
        >
          重试
        </button>
      )}
    </div>
  )
}
