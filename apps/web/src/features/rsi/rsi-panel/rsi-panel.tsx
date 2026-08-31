'use client'

import dynamic from 'next/dynamic'

import IndicatorPanel from '@/features/indicators/indicator-panel'
import { colors } from '@/styles/colors'

import useRsi from '../use-rsi'

// ECharts 依赖浏览器 API，SSR 阶段无法执行，用 ssr:false 只在客户端渲染
const RsiChart = dynamic(() => import('../rsi-chart'), { ssr: false })

export interface RsiPanelProps {
  symbol: string
  /** 只显示最后 N 个交易日（指标仍按全量历史计算） */
  limit?: number
}

export default function RsiPanel({ symbol, limit }: RsiPanelProps) {
  const { data, loading, error } = useRsi(symbol, limit)

  return (
    <IndicatorPanel
      title={data ? `${data.symbol} 日线 RSI(14)` : 'RSI'}
      legend={
        <>
          <span style={{ color: colors.rsi }}>● RSI</span>
          <span className='text-muted-foreground'>— 70 超买 / 30 超卖</span>
        </>
      }
      loading={loading}
      error={error}
    >
      {data && <RsiChart series={data.series} />}
    </IndicatorPanel>
  )
}
