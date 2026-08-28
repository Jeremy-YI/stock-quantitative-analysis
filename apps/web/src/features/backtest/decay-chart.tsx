'use client'

import ReactECharts from 'echarts-for-react'
import type { EChartsOption } from 'echarts'

import { colors } from '@/styles/colors'

import type { DecayPoint } from './types'

export interface DecayChartProps {
  points: DecayPoint[]
}

/** 策略衰减曲线：超额胜率（主，左轴，0 参考线）+ 滚动胜率（次，右轴，50% 参考线）。

  原始胜率下降可能只是市场变差；超额胜率（策略 − 同期市场基线）才反映策略是否失效。 */
export default function DecayChart({ points }: DecayChartProps) {
  const dates = points.map((p) => p.date)
  const winRates = points.map((p) => p.win_rate * 100)
  const excess = points.map((p) =>
    p.excess_win_rate === null ? null : +(p.excess_win_rate * 100).toFixed(1)
  )

  const option: EChartsOption = {
    tooltip: {
      trigger: 'axis',
      valueFormatter: (v) => `${Number(v).toFixed(1)}`,
    },
    legend: { top: 0 },
    grid: { left: 50, right: 50, top: 30, bottom: 40 },
    xAxis: { type: 'category', data: dates },
    yAxis: [
      {
        type: 'value',
        name: '超额(pp)',
        axisLabel: { formatter: '{value}' },
      },
      {
        type: 'value',
        name: '胜率(%)',
        min: 0,
        max: 100,
        axisLabel: { formatter: '{value}%' },
      },
    ],
    series: [
      {
        name: '超额胜率',
        type: 'line',
        yAxisIndex: 0,
        data: excess,
        showSymbol: false,
        lineStyle: { color: colors.up },
        itemStyle: { color: colors.up },
        markLine: {
          silent: true,
          symbol: 'none',
          lineStyle: { color: colors.neutral, type: 'dashed' },
          data: [{ yAxis: 0 }],
          label: { formatter: '0pp' },
        },
      },
      {
        name: '滚动胜率',
        type: 'line',
        yAxisIndex: 1,
        data: winRates,
        showSymbol: false,
        lineStyle: { color: colors.dif, opacity: 0.7 },
        itemStyle: { color: colors.dif },
        markLine: {
          silent: true,
          symbol: 'none',
          lineStyle: { color: colors.neutral, type: 'dashed', opacity: 0.6 },
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
