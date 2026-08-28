'use client'

import ReactECharts from 'echarts-for-react'
import type { EChartsOption } from 'echarts'

import { colors } from '@/styles/colors'

import type { DecayPoint } from './types'

export interface DecayChartProps {
  points: DecayPoint[]
}

/** 策略衰减曲线：滚动窗口胜率随时间变化（50% 画参考线）。 */
export default function DecayChart({ points }: DecayChartProps) {
  const dates = points.map((p) => p.date)
  const winRates = points.map((p) => p.win_rate * 100)

  const option: EChartsOption = {
    tooltip: {
      trigger: 'axis',
      valueFormatter: (v) => `${Number(v).toFixed(1)}%`,
    },
    grid: { left: 50, right: 20, top: 30, bottom: 40 },
    xAxis: { type: 'category', data: dates },
    yAxis: { type: 'value', min: 0, max: 100, axisLabel: { formatter: '{value}%' } },
    series: [
      {
        name: '滚动胜率',
        type: 'line',
        data: winRates,
        showSymbol: false,
        lineStyle: { color: colors.up },
        markLine: {
          silent: true,
          symbol: 'none',
          lineStyle: { color: colors.neutral, type: 'dashed' },
          data: [{ yAxis: 50 }],
          label: { formatter: '50%' },
        },
      },
    ],
  }

  return (
    <ReactECharts
      option={option}
      notMerge
      style={{ height: '100%', width: '100%' }}
    />
  )
}
