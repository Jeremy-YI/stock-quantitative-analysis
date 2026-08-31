/**
 * Typography —— 排版组件。
 *
 * 字号全部走 globals.css 的流式令牌（clamp），手机到桌面连续缩放，
 * 所以业务里不需要写 text-xl mobile-landscape:text-2xl desktop:text-3xl 这种阶梯。
 *
 *   <Heading level={1}>页面标题</Heading>
 *   <Text tone="muted" size="body-sm">说明文字</Text>
 *   <Num value={-1.23} suffix="%" />   // 自动红涨绿跌 + 等宽对齐
 */
import * as React from 'react'
import { cva, type VariantProps } from 'class-variance-authority'

import { cn } from '@/lib/utils'

import { TEXT_TONE, changeTextClass, type Tone } from './color'

/* ------------------------------- Heading ------------------------------- */

const headingVariants = cva('text-balance', {
  variants: {
    size: {
      display: 'text-display',
      h1: 'text-h1',
      h2: 'text-h2',
      h3: 'text-h3',
      h4: 'text-h4',
    },
    tone: TEXT_TONE,
  },
  defaultVariants: { size: 'h2', tone: 'default' },
})

export interface HeadingProps
  extends Omit<React.HTMLAttributes<HTMLHeadingElement>, 'color'>,
    Omit<VariantProps<typeof headingVariants>, 'size'> {
  /** 语义层级（决定标签 h1~h4，同时给默认字号） */
  level?: 1 | 2 | 3 | 4
  /** 需要「小标签大字号」或反之时单独覆盖字号 */
  size?: 'display' | 'h1' | 'h2' | 'h3' | 'h4'
}

const LEVEL_SIZE = { 1: 'h1', 2: 'h2', 3: 'h3', 4: 'h4' } as const

export function Heading({
  level = 2,
  size,
  tone,
  className,
  ...rest
}: HeadingProps) {
  const Tag = `h${level}` as 'h1' | 'h2' | 'h3' | 'h4'
  return (
    <Tag
      className={cn(headingVariants({ size: size ?? LEVEL_SIZE[level], tone }), className)}
      {...rest}
    />
  )
}

/* -------------------------------- Text -------------------------------- */

const textVariants = cva('', {
  variants: {
    size: {
      'body-lg': 'text-body-lg',
      body: 'text-body',
      'body-sm': 'text-body-sm',
      caption: 'text-caption',
    },
    tone: TEXT_TONE,
    weight: {
      normal: 'font-normal',
      medium: 'font-medium',
      semibold: 'font-semibold',
      bold: 'font-bold',
    },
    mono: { true: 'font-mono tabular-nums', false: '' },
    truncate: { true: 'truncate', false: '' },
  },
  defaultVariants: {
    size: 'body',
    tone: 'default',
    weight: 'normal',
    mono: false,
    truncate: false,
  },
})

export interface TextProps
  extends Omit<React.HTMLAttributes<HTMLElement>, 'color'>,
    VariantProps<typeof textVariants> {
  as?: 'p' | 'span' | 'div' | 'dd' | 'dt' | 'li' | 'label'
}

export function Text({
  as: Tag = 'p',
  size,
  tone,
  weight,
  mono,
  truncate,
  className,
  ...rest
}: TextProps) {
  return (
    <Tag
      className={cn(textVariants({ size, tone, weight, mono, truncate }), className)}
      {...rest}
    />
  )
}

/** 辅助说明（12px 次要文字），出现频率高，单独给个壳。 */
export function Caption({ className, ...rest }: Omit<TextProps, 'size'>) {
  return <Text size="caption" tone="muted" className={className} {...rest} />
}

/** 等宽数字（表格里代码、价格、分数用，保证列对齐）。 */
export function Mono({ className, ...rest }: Omit<TextProps, 'mono'>) {
  return <Text as="span" mono className={className} {...rest} />
}

/* --------------------------------- Num -------------------------------- */

// 字重必须写成字面量映射，Tailwind 扫不到 `font-${x}` 这种拼接类名
const WEIGHT_CLASS = {
  normal: 'font-normal',
  medium: 'font-medium',
  semibold: 'font-semibold',
  bold: 'font-bold',
} as const

export interface NumProps extends Omit<React.HTMLAttributes<HTMLSpanElement>, 'color'> {
  value: number | null | undefined
  /** 小数位，默认 2 */
  digits?: number
  /** 是否显示 + 号（涨跌场景需要） */
  signed?: boolean
  /** 是否按涨跌上色（红涨绿跌），默认 true */
  colored?: boolean
  suffix?: string
  prefix?: string
  /** 空值占位 */
  fallback?: string
  weight?: 'normal' | 'medium' | 'semibold' | 'bold'
}

/** 涨跌数字：等宽 + 正负号 + 红涨绿跌，一个组件收口所有行情数字。 */
export function Num({
  value,
  digits = 2,
  signed = true,
  colored = true,
  suffix = '',
  prefix = '',
  fallback = '—',
  weight = 'normal',
  className,
  ...rest
}: NumProps) {
  const empty = value === null || value === undefined || Number.isNaN(value)
  const body = empty
    ? fallback
    : `${prefix}${signed && value > 0 ? '+' : ''}${value.toFixed(digits)}${suffix}`

  return (
    <span
      className={cn(
        'font-mono tabular-nums',
        WEIGHT_CLASS[weight],
        colored && !empty ? changeTextClass(value) : 'text-foreground',
        className
      )}
      {...rest}
    >
      {body}
    </span>
  )
}

export type { Tone }
export { headingVariants, textVariants }
