/**
 * Container —— 页面内容容器。
 *
 * 关键点：**宽度永远是 100%**，size 只控制「最大宽度」和左右留白。
 * 手机上 padding 小、桌面上大；超宽屏收口，避免一行拉到 2000px。
 *
 *   <Container size="lg">…</Container>
 */
import * as React from 'react'
import { cva, type VariantProps } from 'class-variance-authority'

import { cn } from '@/lib/utils'

const containerVariants = cva('mx-auto w-full', {
  variants: {
    size: {
      /** 阅读流：新闻、AI 解读（~640） */
      sm: 'max-w-[40rem]',
      /** 常规内容（~896） */
      md: 'max-w-[56rem]',
      /** 数据看板（~1200） */
      lg: 'max-w-[75rem]',
      /** 宽表格（~1440） */
      xl: 'max-w-[90rem]',
      /** 不限宽（全屏图表） */
      full: 'max-w-none',
    },
    padded: {
      true: 'px-4 mobile-portrait:px-6 desktop:px-8',
      false: '',
    },
  },
  defaultVariants: { size: 'lg', padded: true },
})

export interface ContainerProps
  extends React.HTMLAttributes<HTMLElement>,
    VariantProps<typeof containerVariants> {
  as?: 'div' | 'main' | 'section' | 'header' | 'footer' | 'nav'
}

export function Container({
  as = 'div',
  size,
  padded,
  className,
  ...rest
}: ContainerProps) {
  const Tag = as as React.ElementType
  return <Tag className={cn(containerVariants({ size, padded }), className)} {...rest} />
}

export { containerVariants }
