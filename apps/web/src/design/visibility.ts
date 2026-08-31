/**
 * 可见性类名映射（纯数据，无 React，服务端/客户端都能 import）。
 * Tailwind 只认字面量类名，所以这里全部展开写。
 * 断点前缀用 FFP 语义命名：mobile-portrait / mobile-landscape / desktop / large-device。
 */
import type { Breakpoint } from './tokens'

/** 表格单元格：低于断点隐藏，达到断点恢复 table-cell。 */
export const CELL_VISIBLE_FROM: Record<Breakpoint, string> = {
  mobilePortrait: 'hidden mobile-portrait:table-cell',
  mobileLandscape: 'hidden mobile-landscape:table-cell',
  desktop: 'hidden desktop:table-cell',
  largeDevice: 'hidden large-device:table-cell',
}

/** 块级元素：低于断点隐藏。 */
export const BLOCK_VISIBLE_FROM: Record<Breakpoint, string> = {
  mobilePortrait: 'hidden mobile-portrait:block',
  mobileLandscape: 'hidden mobile-landscape:block',
  desktop: 'hidden desktop:block',
  largeDevice: 'hidden large-device:block',
}

/** 达到断点后隐藏（只在更小的屏出现）。 */
export const HIDDEN_FROM: Record<Breakpoint, string> = {
  mobilePortrait: 'mobile-portrait:hidden',
  mobileLandscape: 'mobile-landscape:hidden',
  desktop: 'desktop:hidden',
  largeDevice: 'large-device:hidden',
}

/** 给 <th>/<td>：这一列在小屏隐藏。 */
export function cellVisibleFrom(bp: Breakpoint): string {
  return CELL_VISIBLE_FROM[bp]
}
