'use client'

import ReactECharts from 'echarts-for-react'
import type { EChartsOption } from 'echarts'

import { colors } from '@/styles/colors'

import type { EquityPoint } from '../types'

export interface EquityChartProps {
  series: EquityPoint[]
}

/** 组合净值曲线（起点归一为初始资金）。 */
export default function EquityChart({ series }: EquityChartProps) {
  const dates = series.map((p) => p.date)
  const values = series.map((p) => p.equity)

  const option: EChartsOption = {
    tooltip: { trigger: 'axis' },
    grid: { left: 70, right: 20, top: 30, bottom: 40 },
    xAxis: { type: 'category', data: dates },
    yAxis: { type: 'value', scale: true },
    series: [
      {
        name: '净值',
        type: 'line',
        data: values,
        showSymbol: false,
        lineStyle: { color: colors.dif },
        areaStyle: { opacity: 0.08 },
      },
    ],
  }

  return <ReactECharts option={option} notMerge style={{ height: '100%', width: '100%' }} />
}
