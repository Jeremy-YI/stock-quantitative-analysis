/**
 * Button —— 按钮。
 *
 * 变体走语义（accent = 交互主色 / danger = 危险操作），尺寸对触屏友好：
 * 手机上高度 40px（h-10），md 起收到 36px（h-9），符合最小点击区。
 *
 *   <Button variant="accent">扫描</Button>
 *   <Button variant="outline" size="sm">重置</Button>
 *   <Button block>手机撑满、桌面自适应</Button>
 */
import * as React from 'react'
import { cva, type VariantProps } from 'class-variance-authority'

import { cn } from '@/lib/utils'

const buttonVariants = cva(
  [
    'inline-flex shrink-0 items-center justify-center gap-2 whitespace-nowrap rounded-md',
    'font-medium transition-colors select-none',
    'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-1',
    'disabled:pointer-events-none disabled:opacity-50',
  ].join(' '),
  {
    variants: {
      variant: {
        /** 深色主按钮（沿用 shadcn default，保持既有调用不变） */
        default: 'bg-primary text-primary-foreground hover:bg-primary/90',
        /** 交互主色：新页面的主操作用这个 */
        accent: 'bg-accent text-accent-foreground hover:bg-accent/90',
        secondary: 'bg-muted text-foreground hover:bg-surface-hover',
        outline: 'border border-border bg-background hover:bg-surface-hover',
        ghost: 'hover:bg-surface-hover',
        subtle: 'bg-accent-soft text-accent hover:bg-accent-soft/70',
        danger: 'bg-danger text-white hover:bg-danger/90',
        link: 'text-accent underline-offset-4 hover:underline',
      },
      size: {
        sm: 'h-8 rounded-md px-2.5 text-caption mobile-portrait:text-body-sm',
        default: 'h-10 px-4 text-body-sm mobile-landscape:h-9',
        lg: 'h-11 px-5 text-body mobile-landscape:h-10',
        icon: 'size-10 mobile-landscape:size-9',
      },
      /** 手机撑满一行、md 起回到自适应宽度（表单主操作常用） */
      block: {
        true: 'w-full mobile-landscape:w-auto',
        false: '',
      },
    },
    defaultVariants: { variant: 'default', size: 'default', block: false },
  },
)

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>, VariantProps<typeof buttonVariants> {}

const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, block, type = 'button', ...props }, ref) => (
    <button
      ref={ref}
      type={type}
      className={cn(buttonVariants({ variant, size, block, className }))}
      {...props}
    />
  ),
)
Button.displayName = 'Button'

export { Button, buttonVariants }
