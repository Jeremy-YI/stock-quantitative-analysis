'use client'

import dynamic from 'next/dynamic'

import IndicatorPanel from '@/features/indicators/indicator-panel'

import useMacd from '../use-macd'

// ECharts 依赖浏览器 API，SSR 阶段无法执行，用 ssr:false 只在客户端渲染
const MacdChart = dynamic(() => import('../macd-chart'), { ssr: false })

export interface MacdPanelProps {
  symbol: string
  /** 只显示最后 N 个交易日（指标仍按全量历史计算） */
  limit?: number
}

export default function MacdPanel({ symbol, limit }: MacdPanelProps) {
  const { data, loading, error } = useMacd(symbol, limit)

  return (
    <IndicatorPanel
      title={data ? `${data.symbol} 日线 MACD` : 'MACD'}
      legend={
        <>
          <span className='text-up'>● 红柱</span>
          <span className='text-down'>● 绿柱</span>
        </>
      }
      loading={loading}
      error={error}
    >
      {data && <MacdChart series={data.series} />}
    </IndicatorPanel>
  )
}
