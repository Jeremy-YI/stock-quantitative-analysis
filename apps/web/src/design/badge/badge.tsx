/**
 * Badge —— 徽标/标签（信号名、影响评级、重要度、任务状态都用它）。
 *
 *   <Badge tone="up">改变定价</Badge>
 *   <Badge tone="accent" variant="soft">单针</Badge>
 *   <Badge tone="down" variant="solid" size="sm">失败</Badge>
 */
import * as React from 'react'
import { cva, type VariantProps } from 'class-variance-authority'

import { cn } from '@/lib/utils'

import { SOFT_TONE, SOLID_TONE, TEXT_TONE, type Tone } from '../color'

const badgeVariants = cva(
  'inline-flex max-w-full items-center gap-1 truncate rounded-md border font-medium',
  {
    variants: {
      tone: SOFT_TONE,
      size: {
        sm: 'px-1.5 py-0 text-caption',
        default: 'px-2 py-0.5 text-caption',
        lg: 'px-2.5 py-1 text-body-sm',
      },
    },
    defaultVariants: { tone: 'default', size: 'default' },
  },
)

export interface BadgeProps
  extends
    Omit<React.HTMLAttributes<HTMLSpanElement>, 'color'>,
    Omit<VariantProps<typeof badgeVariants>, 'tone'> {
  tone?: Tone
  /** soft = 浅底描边（默认）；solid = 实底；outline = 只描边 */
  variant?: 'soft' | 'solid' | 'outline'
}

export function Badge({
  tone = 'default',
  variant = 'soft',
  size,
  className,
  ...rest
}: BadgeProps) {
  const toneClass =
    variant === 'solid'
      ? cn('border-transparent', SOLID_TONE[tone])
      : variant === 'outline'
        ? cn('border-border bg-transparent', TEXT_TONE[tone])
        : SOFT_TONE[tone]

  return <span className={cn(badgeVariants({ size }), toneClass, className)} {...rest} />
}

export { badgeVariants }
