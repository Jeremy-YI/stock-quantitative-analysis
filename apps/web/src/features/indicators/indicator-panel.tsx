import type { ReactNode } from 'react'

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'

import { chartCard, chartContainer, legendHint } from './indicator-styles'

export interface IndicatorPanelProps {
  title: string
  legend?: ReactNode
  loading: boolean
  error: string | null
  children: ReactNode
}

/**
 * 指标展示面板（四个指标共用）：标题 + 图例 + 骨架屏 / 错误 / 图表容器。
 * 纯展示组件，不拉数据，便于单测错误分支与容器渲染。
 */
export default function IndicatorPanel({
  title,
  legend,
  loading,
  error,
  children,
}: IndicatorPanelProps) {
  return (
    <Card className={chartCard}>
      <CardHeader>
        <CardTitle>{title}</CardTitle>
        {legend && <div className={legendHint}>{legend}</div>}
      </CardHeader>
      <CardContent>
        {loading && <Skeleton className="h-[520px] w-full" />}
        {!loading && error && (
          <p className="py-10 text-center text-down">{error}</p>
        )}
        {!loading && !error && (
          <div className={chartContainer} data-testid="indicator-chart">
            {children}
          </div>
        )}
      </CardContent>
    </Card>
  )
}
