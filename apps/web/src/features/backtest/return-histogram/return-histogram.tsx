'use client'

import ReactECharts from 'echarts-for-react'
import type { EChartsOption } from 'echarts'

import { colors } from '@/styles/colors'

import type { HistogramBin } from '../types'

export interface ReturnHistogramProps {
  bins: HistogramBin[]
  holdDays: number
}

/** 收益分布直方图（红=正收益区间、绿=负收益区间、灰=含 0 的区间）。 */
export default function ReturnHistogram({ bins, holdDays }: ReturnHistogramProps) {
  const labels = bins.map((b) => `${(b.lower * 100).toFixed(0)}%`)
  const data = bins.map((b) => ({
    value: b.count,
    itemStyle: {
      color: b.lower >= 0 ? colors.up : b.upper <= 0 ? colors.down : colors.neutral,
    },
  }))

  const option: EChartsOption = {
    tooltip: { trigger: 'axis' },
    grid: { left: 50, right: 20, top: 30, bottom: 40 },
    xAxis: { type: 'category', data: labels, name: '收益区间' },
    yAxis: { type: 'value', name: '数量' },
    series: [
      {
        name: `持有 ${holdDays} 日收益`,
        type: 'bar',
        data,
        barCategoryGap: '10%',
      },
    ],
  }

  return <ReactECharts option={option} notMerge style={{ height: '100%', width: '100%' }} />
}
