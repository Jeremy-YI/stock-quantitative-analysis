/**
 * Page / PageHeader / Section —— 页面骨架。
 *
 * 所有页面统一走这一层，保证：
 *  - 垂直节奏一致（手机 py-5、桌面 py-8）
 *  - 页头在手机上标题与操作区自动换行，不挤压
 *  - 内容宽度由 Container 的 size 决定，不在页面里散落 max-w-*
 *
 *   <Page size="lg">
 *     <PageHeader title="板块资金" description="同花顺行业资金流" actions={<Button/>} />
 *     <Section title="Top20 流入">…</Section>
 *   </Page>
 */
import * as React from 'react'

import { cn } from '@/lib/utils'

import { Container, type ContainerProps } from '../container'
import { GAP, type GapSize } from '../grid'
import { Heading, Text } from '../typography'

export interface PageProps extends Omit<React.HTMLAttributes<HTMLElement>, 'title'> {
  size?: ContainerProps['size']
  gap?: GapSize
}

export function Page({ size = 'lg', gap = 'lg', className, children, ...rest }: PageProps) {
  return (
    <main
      className={cn('min-h-[60vh] bg-background py-5 mobile-portrait:py-7 desktop:py-8', className)}
      {...rest}
    >
      <Container size={size} className={cn('flex flex-col', GAP[gap])}>
        {children}
      </Container>
    </main>
  )
}

export interface PageHeaderProps {
  title: React.ReactNode
  description?: React.ReactNode
  /** 右侧操作区：手机上会掉到标题下方并撑满 */
  actions?: React.ReactNode
  className?: string
}

export function PageHeader({ title, description, actions, className }: PageHeaderProps) {
  return (
    <header
      className={cn(
        'flex flex-col gap-3 mobile-landscape:flex-row mobile-landscape:items-end mobile-landscape:justify-between',
        className,
      )}
    >
      <div className='min-w-0 space-y-1'>
        <Heading level={1}>{title}</Heading>
        {description ? (
          <Text size='body-sm' tone='muted'>
            {description}
          </Text>
        ) : null}
      </div>
      {actions ? (
        <div className='flex w-full flex-wrap items-center gap-2 mobile-landscape:w-auto mobile-landscape:justify-end'>
          {actions}
        </div>
      ) : null}
    </header>
  )
}

export interface SectionProps extends Omit<React.HTMLAttributes<HTMLElement>, 'title'> {
  title?: React.ReactNode
  description?: React.ReactNode
  actions?: React.ReactNode
  gap?: GapSize
}

export function Section({
  title,
  description,
  actions,
  gap = 'md',
  className,
  children,
  ...rest
}: SectionProps) {
  return (
    <section className={cn('flex flex-col', GAP[gap], className)} {...rest}>
      {title || actions ? (
        <div className='flex flex-col gap-2 mobile-portrait:flex-row mobile-portrait:items-center mobile-portrait:justify-between'>
          <div className='min-w-0 space-y-0.5'>
            {title ? <Heading level={2}>{title}</Heading> : null}
            {description ? (
              <Text size='body-sm' tone='muted'>
                {description}
              </Text>
            ) : null}
          </div>
          {actions ? <div className='flex flex-wrap items-center gap-2'>{actions}</div> : null}
        </div>
      ) : null}
      {children}
    </section>
  )
}

/** 加载中/失败/空态：三种反馈样式统一，别再各页手写 <p class="text-gray-500">。 */
export function StateHint({
  kind = 'loading',
  children,
  className,
}: {
  kind?: 'loading' | 'error' | 'empty'
  children: React.ReactNode
  className?: string
}) {
  const tone =
    kind === 'error'
      ? 'text-danger'
      : kind === 'empty'
        ? 'text-muted-foreground'
        : 'text-muted-foreground'
  return (
    <p
      role={kind === 'error' ? 'alert' : undefined}
      className={cn(
        'rounded-lg border border-border bg-surface px-4 py-6 text-center text-body-sm',
        tone,
        className,
      )}
    >
      {children}
    </p>
  )
}
