'use client'

import dynamic from 'next/dynamic'

import IndicatorPanel from '@/features/indicators/indicator-panel'

import usePricingLines from '../use-pricing-lines'

// ECharts 依赖浏览器 API，SSR 阶段无法执行，用 ssr:false 只在客户端渲染
const PricingLinesChart = dynamic(() => import('../pricing-lines-chart'), { ssr: false })

export interface PricingLinesPanelProps {
  symbol: string
  /** 只显示最后 N 个交易日（指标仍按全量历史计算） */
  limit?: number
}

export default function PricingLinesPanel({ symbol, limit }: PricingLinesPanelProps) {
  const { data, loading, error } = usePricingLines(symbol, limit)

  return (
    <IndicatorPanel
      title={data ? `${data.symbol} 定价线（生命线 / 阴量 / 进攻K）` : '定价线'}
      legend={
        <>
          <span style={{ color: '#a855f7' }}>● 生命线</span>
          <span style={{ color: '#14b8a6' }}>● 阴量定价线</span>
          <span style={{ color: '#f97316' }}>● 进攻K防线</span>
        </>
      }
      loading={loading}
      error={error}
    >
      {data && <PricingLinesChart series={data.series} />}
    </IndicatorPanel>
  )
}
