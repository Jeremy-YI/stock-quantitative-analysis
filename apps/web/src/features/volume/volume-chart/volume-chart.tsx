'use client'

import ReactECharts from 'echarts-for-react'
import type { EChartsOption } from 'echarts'

import { colors } from '@/styles/colors'

import type { VolumePoint } from '../types'

export interface VolumeChartProps {
  series: VolumePoint[]
}

/**
 * 双图联动：上图收盘价，下图成交量柱（红涨绿跌）+ MAVOL1/MAVOL2 两条均线。
 */
export default function VolumeChart({ series }: VolumeChartProps) {
  const dates = series.map((p) => p.date)
  const closes = series.map((p) => p.close)
  const mavol1 = series.map((p) => p.mavol1)
  const mavol2 = series.map((p) => p.mavol2)

  // 柱颜色：收盘价相对前一日，涨红跌绿（首根按中性灰）
  const bars = series.map((p, i) => {
    const up = i === 0 ? true : closes[i] >= closes[i - 1]
    return {
      value: p.volume,
      itemStyle: { color: up ? colors.up : colors.down },
    }
  })

  const option: EChartsOption = {
    tooltip: { trigger: 'axis' },
    legend: { data: ['收盘价', 'MAVOL1', 'MAVOL2'] },
    grid: [
      { left: 60, right: 20, top: 40, height: '45%' },
      { left: 60, right: 20, top: '62%', height: '28%' },
    ],
    xAxis: [
      { type: 'category', data: dates, gridIndex: 0 },
      { type: 'category', data: dates, gridIndex: 1, axisLabel: { show: false } },
    ],
    yAxis: [
      { scale: true, gridIndex: 0 },
      { scale: true, gridIndex: 1 },
    ],
    series: [
      {
        name: '收盘价',
        type: 'line',
        data: closes,
        showSymbol: false,
        lineStyle: { color: colors.neutral },
      },
      {
        name: '成交量',
        type: 'bar',
        xAxisIndex: 1,
        yAxisIndex: 1,
        data: bars,
      },
      {
        name: 'MAVOL1',
        type: 'line',
        xAxisIndex: 1,
        yAxisIndex: 1,
        data: mavol1,
        showSymbol: false,
        lineStyle: { color: colors.mavol1 },
      },
      {
        name: 'MAVOL2',
        type: 'line',
        xAxisIndex: 1,
        yAxisIndex: 1,
        data: mavol2,
        showSymbol: false,
        lineStyle: { color: colors.mavol2 },
      },
    ],
  }

  return <ReactECharts option={option} notMerge style={{ height: '100%', width: '100%' }} />
}
