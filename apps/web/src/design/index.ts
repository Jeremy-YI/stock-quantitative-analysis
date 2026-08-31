/**
 * 设计系统统一出口。
 *
 * 业务代码只从这里 import：
 *   import { Page, PageHeader, Section, Grid, Stack, Row, Heading, Text, Num,
 *            Button, Badge, Table, TableScroll, Field, Select, Show, useBreakpoint } from '@/design'
 *
 * 目录职责：
 *   tokens.ts      断点/字号/容器宽度/图表高度（JS 侧唯一来源）
 *   color.ts       语义色 tone → class
 *   breakpoint.tsx 断点 Hook + CSS 版显示隐藏
 *   typography.tsx Heading / Text / Caption / Mono / Num
 *   container.tsx  Container（最大宽度 + 响应式留白）
 *   grid.tsx       Grid（断点列数）+ GAP
 *   stack.tsx      Stack / Row
 *   page.tsx       Page / PageHeader / Section / StateHint
 *   button.tsx     Button
 *   badge.tsx      Badge
 *   table.tsx      TableScroll / Table / THead / TBody / TR / TH / TD
 *   field.tsx      FilterBar / Field / TextInput / Select
 */

export {
  BREAKPOINTS,
  BREAKPOINT_ORDER,
  BREAKPOINT_PREFIX,
  CHART_HEIGHT,
  COLOR_TOKENS,
  CONTAINER_MAX,
  SPACING,
  TEXT_SCALE,
  breakpointLabel,
  spacing,
  isBreakpointAtLeast,
  mediaAbove,
  mediaBelow,
  mediaBetween,
  normalizeResponsive,
  resolveBreakpoint,
  type Breakpoint,
  type ContainerSize,
  type Responsive,
  type ResponsiveKey,
} from './tokens'

export {
  BreakpointIndicator,
  ResponsiveBreakPoints,
  Show,
  cellVisibleFrom,
  pickResponsive,
  useBreakpoint,
  useChartHeight,
  useMediaQuery,
  useResponsiveValue,
  type BreakpointState,
  type ShowProps,
} from './breakpoint'

export {
  BLOCK_VISIBLE_FROM,
  CELL_VISIBLE_FROM,
  HIDDEN_FROM,
} from './visibility'

export {
  SOFT_TONE,
  SOLID_TONE,
  TEXT_TONE,
  changeTextClass,
  toneForChange,
  toneForStatus,
  type Tone,
} from './color'

export {
  Caption,
  Heading,
  Mono,
  Num,
  Text,
  headingVariants,
  textVariants,
  type HeadingProps,
  type NumProps,
  type TextProps,
} from './typography'

export { Container, containerVariants, type ContainerProps } from './container'
export { GAP, Grid, gridColsClass, type GapSize, type GridCols, type GridProps } from './grid'
export { Row, Stack, type StackDirection, type StackProps } from './stack'
export {
  Page,
  PageHeader,
  Section,
  StateHint,
  type PageHeaderProps,
  type PageProps,
  type SectionProps,
} from './page'
export { Button, buttonVariants, type ButtonProps } from './button'
export { Badge, badgeVariants, type BadgeProps } from './badge'
export {
  TBody,
  TD,
  TH,
  THead,
  TR,
  Table,
  TableScroll,
  type TableProps,
  type TableScrollProps,
} from './table'
export {
  Field,
  FilterBar,
  Select,
  TextInput,
  controlBase,
  type FieldProps,
} from './field'

// shadcn 侧基础件也从设计系统出口暴露，业务不用记两个路径
export {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
export { Skeleton } from '@/components/ui/skeleton'
export { default as Tabs, type TabItem, type TabsProps } from '@/components/ui/tabs'
