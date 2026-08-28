'use client'

import ReactECharts from 'echarts-for-react'
import type { EChartsOption } from 'echarts'

import { colors } from '@/styles/colors'

import type { StrategyResult } from './types'

export interface ExcessChartProps {
  results: StrategyResult[]
  holdDays: number
}

/** 策略胜率 vs 同期基线胜率（分组柱状）+ 超额胜率（正负用 up/down 语义色）。 */
export default function ExcessChart({ results, holdDays }: ExcessChartProps) {
  const names = results.map((r) => r.strategy)
  const winRates = results.map((r) => {
    const h = r.holds.find((x) => x.hold_days === holdDays)
    return h ? h.win_rate * 100 : null
  })
  const baselines = results.map((r) => {
    const h = r.holds.find((x) => x.hold_days === holdDays)
    return h ? h.baseline_win_rate : null
  })
  const baselinePct = baselines.map((v) => (v === null ? null : v * 100))
  const excess = results.map((r) => {
    const h = r.holds.find((x) => x.hold_days === holdDays)
    return h ? h.excess_win_rate : null
  })

  const option: EChartsOption = {
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'shadow' },
      valueFormatter: (v) =>
        `${Number(v) >= 0 ? '+' : ''}${Number(v).toFixed(1)}%`,
    },
    legend: { top: 0 },
    grid: { left: 50, right: 20, top: 40, bottom: 60 },
    xAxis: {
      type: 'category',
      data: names,
      axisLabel: { rotate: 30 },
    },
    yAxis: {
      type: 'value',
      axisLabel: { formatter: '{value}%' },
    },
    series: [
      {
        name: '策略胜率',
        type: 'bar',
        data: winRates,
        itemStyle: { color: colors.dif },
        barGap: '10%',
      },
      {
        name: '基线胜率',
        type: 'bar',
        data: baselinePct,
        itemStyle: { color: colors.neutral },
      },
      {
        name: '超额胜率',
        type: 'bar',
        data: excess.map((v) => ({
          value: v === null ? null : +(v * 100).toFixed(1),
          itemStyle: {
            color: v === null || v === 0 ? colors.neutral : v > 0 ? colors.up : colors.down,
          },
        })),
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
