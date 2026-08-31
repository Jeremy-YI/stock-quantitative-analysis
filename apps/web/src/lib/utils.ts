import { clsx, type ClassValue } from 'clsx'
import { extendTailwindMerge } from 'tailwind-merge'

/**
 * tailwind-merge 默认不认识我们自定义的字号令牌（text-h1 / text-caption …），
 * 会把它们当成「文字颜色」，于是 cn('text-h1', 'text-muted-foreground') 会把字号吃掉。
 * 这里显式告诉它这些值属于 font-size 组，颜色与字号才能共存。
 * 令牌清单需与 styles/globals.css 的 --text-* 保持一致。
 */
const twMerge = extendTailwindMerge({
  extend: {
    classGroups: {
      'font-size': [
        {
          text: [
            'display',
            'h1',
            'h2',
            'h3',
            'h4',
            'body-lg',
            'body',
            'body-sm',
            'caption',
          ],
        },
      ],
    },
  },
})

/**
 * 合并 className：clsx 负责拼接 + 条件判断，tailwind-merge 负责去重冲突的
 * Tailwind 类（后写的覆盖先写的），避免「两个 bg-* 同时存在」的问题。
 */
export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}
