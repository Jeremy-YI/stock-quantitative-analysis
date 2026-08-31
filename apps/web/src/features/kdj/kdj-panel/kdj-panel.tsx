'use client'

import dynamic from 'next/dynamic'

import IndicatorPanel from '@/features/indicators/indicator-panel'
import { colors } from '@/styles/colors'

import useKdj from '../use-kdj'

// ECharts 依赖浏览器 API，SSR 阶段无法执行，用 ssr:false 只在客户端渲染
const KdjChart = dynamic(() => import('../kdj-chart'), { ssr: false })

export interface KdjPanelProps {
  symbol: string
  /** 只显示最后 N 个交易日（指标仍按全量历史计算） */
  limit?: number
}

export default function KdjPanel({ symbol, limit }: KdjPanelProps) {
  const { data, loading, error } = useKdj(symbol, limit)

  return (
    <IndicatorPanel
      title={data ? `${data.symbol} 日线 KDJ` : 'KDJ'}
      legend={
        <>
          <span style={{ color: colors.kdjK }}>● K</span>
          <span style={{ color: colors.kdjD }}>● D</span>
          <span style={{ color: colors.kdjJ }}>● J</span>
        </>
      }
      loading={loading}
      error={error}
    >
      {data && <KdjChart series={data.series} />}
    </IndicatorPanel>
  )
}
