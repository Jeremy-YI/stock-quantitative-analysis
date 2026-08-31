/**
 * 设计令牌（JS 侧唯一来源）—— 命名与 FreshFarmPicking 的 global-theme.ts 对齐。
 *
 * 断点用语义名（不用 sm/md/lg）：
 *   base            < 448   手机竖屏
 *   mobilePortrait  ≥ 448   大屏手机 / 手机横屏起
 *   mobileLandscape ≥ 766   平板（pad）
 *   desktop         ≥ 1200  桌面
 *   largeDevice     ≥ 1440  大桌面
 *
 * CSS 侧同名令牌在 src/styles/globals.css 的 @theme（kebab-case 变体前缀）：
 *   mobile-portrait: / mobile-landscape: / desktop: / large-device:
 * 两边必须一致，tests/design-system.test.tsx 有一致性断言。
 */

import { breakpoints, containerMax, spacing, spacingScale } from '@/constants'

/** 断点（px，min-width 口径，移动优先）。值来自 constants/global-theme（同 FFP）。 */
export const BREAKPOINTS = {
  mobilePortrait: breakpoints.mobilePortrait,
  mobileLandscape: breakpoints.mobileLandscape,
  desktop: breakpoints.desktop,
  largeDevice: breakpoints.largeDevice,
} as const

export type Breakpoint = keyof typeof BREAKPOINTS

/** 从小到大的断点顺序（遍历/比较用，别依赖对象 key 顺序）。 */
export const BREAKPOINT_ORDER: readonly Breakpoint[] = [
  'mobilePortrait',
  'mobileLandscape',
  'desktop',
  'largeDevice',
]

/** TS 侧 camelCase → Tailwind 变体前缀（CSS 侧 kebab-case）。 */
export const BREAKPOINT_PREFIX: Record<Breakpoint, string> = {
  mobilePortrait: 'mobile-portrait',
  mobileLandscape: 'mobile-landscape',
  desktop: 'desktop',
  largeDevice: 'large-device',
}

/** 响应式取值的 key：base = 无前缀（手机竖屏兜底，等价 FFP 的 xs: 0）。 */
export type ResponsiveKey = 'base' | Breakpoint

/** 响应式属性：单值，或 { base, mobileLandscape, desktop } 这种断点映射（同 MUI sx 写法）。 */
export type Responsive<T> = T | Partial<Record<ResponsiveKey, T>>

/** 把 Responsive<T> 归一成断点映射（单值视为 base）。 */
export function normalizeResponsive<T>(
  value: Responsive<T> | undefined,
): Partial<Record<ResponsiveKey, T>> {
  if (value === undefined) return {}
  if (typeof value === 'object' && value !== null && !Array.isArray(value)) {
    return value as Partial<Record<ResponsiveKey, T>>
  }
  return { base: value as T }
}

/** min-width 媒体查询字符串。 */
export function mediaAbove(bp: Breakpoint): string {
  return `(min-width: ${BREAKPOINTS[bp]}px)`
}

/** max-width 媒体查询字符串（比断点小 0.1px，避免与 above 重叠）。 */
export function mediaBelow(bp: Breakpoint): string {
  return `(max-width: ${BREAKPOINTS[bp] - 0.1}px)`
}

/** 区间媒体查询：[from, to)。 */
export function mediaBetween(from: Breakpoint, to: Breakpoint): string {
  return `${mediaAbove(from)} and ${mediaBelow(to)}`
}

/** 给定视口宽度，返回当前命中的最大断点（比 mobilePortrait 还小返回 base）。 */
export function resolveBreakpoint(width: number): ResponsiveKey {
  let current: ResponsiveKey = 'base'
  for (const bp of BREAKPOINT_ORDER) {
    if (width >= BREAKPOINTS[bp]) current = bp
  }
  return current
}

/** a 是否 >= b（断点大小比较，base 最小）。 */
export function isBreakpointAtLeast(a: ResponsiveKey, b: Breakpoint): boolean {
  const width = a === 'base' ? 0 : BREAKPOINTS[a]
  return width >= BREAKPOINTS[b]
}

/** 视口档位的人话描述（ResponsiveBreakPoints 组件在用，等价 FFP 的 viewText）。 */
export function breakpointLabel(bp: ResponsiveKey): string {
  switch (bp) {
    case 'largeDevice':
      return '大桌面（≥ 1440px）'
    case 'desktop':
      return '桌面（1200 ~ 1440px）'
    case 'mobileLandscape':
      return '平板 / 手机横屏（766 ~ 1200px）'
    case 'mobilePortrait':
      return '大屏手机（448 ~ 766px）'
    default:
      return '手机竖屏（< 448px）'
  }
}

/**
 * 间距刻度（index → px），与 FFP theme.spacing 完全一致：
 * spacing(1)=4px、spacing(4)=16px、spacing(9)=40px…
 * Tailwind 侧对应 gap-1(4px) / gap-4(16px) / gap-10(40px)，换算见 SPACING_CLASS。
 */
export const SPACING = spacingScale

export { spacing }

/**
 * 内容最大宽度（不是固定宽度：宽度始终 100%，只在超宽屏收口）。
 * largeDevice(1440) 是 FFP 的最宽栅格，这里沿用同一口径。
 */
export const CONTAINER_MAX = containerMax

export type ContainerSize = keyof typeof CONTAINER_MAX

/** 排版级别（文档页展示 + Typography 组件的 size 取值）。 */
export const TEXT_SCALE = [
  { token: 'display', usage: '首屏大标题', clamp: '28 → 44px' },
  { token: 'h1', usage: '页面标题', clamp: '24 → 34px' },
  { token: 'h2', usage: '区块标题', clamp: '20 → 26px' },
  { token: 'h3', usage: '卡片标题', clamp: '17 → 20px' },
  { token: 'h4', usage: '小标题/表头', clamp: '15 → 17px' },
  { token: 'body-lg', usage: '正文（阅读流）', clamp: '15 → 17px' },
  { token: 'body', usage: '正文（默认）', clamp: '14 → 15px' },
  { token: 'body-sm', usage: '次要正文/表格', clamp: '13px' },
  { token: 'caption', usage: '辅助说明/角标', clamp: '12px' },
] as const

/** 语义色令牌（文档页展示用；实际取色走 Tailwind 类或 styles/colors.ts）。 */
export const COLOR_TOKENS = [
  { token: 'background', usage: '页面底色' },
  { token: 'foreground', usage: '主文字' },
  { token: 'card', usage: '卡片底色' },
  { token: 'surface', usage: '表头/次级面板' },
  { token: 'muted', usage: '弱化底色' },
  { token: 'muted-foreground', usage: '次要文字' },
  { token: 'border', usage: '描边' },
  { token: 'accent', usage: '交互主色（按钮/链接）' },
  { token: 'up', usage: '涨（红）' },
  { token: 'down', usage: '跌（绿）' },
  { token: 'neutral', usage: '平/中性' },
  { token: 'warn', usage: '提醒' },
  { token: 'danger', usage: '错误' },
  { token: 'info', usage: '信息' },
] as const

/**
 * 图表高度：手机矮、桌面高（ECharts 需要具体像素，不能用百分比）。
 * 配合 useChartHeight() 使用。
 */
export const CHART_HEIGHT = {
  base: 240,
  mobilePortrait: 280,
  mobileLandscape: 360,
  desktop: 420,
  largeDevice: 480,
} as const
