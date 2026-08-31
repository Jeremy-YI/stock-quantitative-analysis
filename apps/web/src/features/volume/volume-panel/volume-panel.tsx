'use client'

import dynamic from 'next/dynamic'

import IndicatorPanel from '@/features/indicators/indicator-panel'
import { colors } from '@/styles/colors'

import useVolume from '../use-volume'

// ECharts 依赖浏览器 API，SSR 阶段无法执行，用 ssr:false 只在客户端渲染
const VolumeChart = dynamic(() => import('../volume-chart'), { ssr: false })

export interface VolumePanelProps {
  symbol: string
  /** 只显示最后 N 个交易日（指标仍按全量历史计算） */
  limit?: number
}

export default function VolumePanel({ symbol, limit }: VolumePanelProps) {
  const { data, loading, error } = useVolume(symbol, limit)

  return (
    <IndicatorPanel
      title={data ? `${data.symbol} 日线 量能` : '量能'}
      legend={
        <>
          <span style={{ color: colors.mavol1 }}>● MAVOL1(5)</span>
          <span style={{ color: colors.mavol2 }}>● MAVOL2(10)</span>
          <span className='text-up'>● 涨</span>
          <span className='text-down'>● 跌</span>
        </>
      }
      loading={loading}
      error={error}
    >
      {data && <VolumeChart series={data.series} />}
    </IndicatorPanel>
  )
}
