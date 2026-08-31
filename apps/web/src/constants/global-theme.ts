/**
 * 全局主题常量（命名与 FreshFarmPicking 的 src/constants/global-theme.ts 对齐）。
 *
 * 这里只放「值」，不放样式实现：
 *   breakpoints  语义断点（px）
 *   spacing      间距刻度（index → px），spacing(4) = 16px
 *
 * Tailwind 侧的同名令牌在 src/styles/globals.css 的 @theme 里；
 * 组件消费入口统一是 src/design（Container/Grid/Show/useBreakpoint…）。
 */

/** 语义断点（与 FFP 完全一致）。 */
export const breakpoints = {
  largeDevice: 1440,
  desktop: 1200,
  mobileLandscape: 766,
  mobilePortrait: 448,
} as const

/** 间距刻度：theme.spacing(n) 的等价物。 */
export const spacingScale = [0, 4, 8, 12, 16, 20, 24, 28, 32, 40, 48, 56, 64] as const

/** spacing(4) → 16（px）。 */
export function spacing(n: number): number {
  return spacingScale[n] ?? 0
}

/** 内容最大宽度（不是固定宽度：宽度 100%，只在超宽屏收口）。 */
export const containerMax = {
  sm: 640,
  md: 896,
  lg: 1200,
  xl: 1440,
  full: null,
} as const

const theme = { breakpoints, spacing: spacingScale, containerMax } as const

export default theme
