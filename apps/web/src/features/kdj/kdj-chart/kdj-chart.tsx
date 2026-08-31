'use client'

import ReactECharts from 'echarts-for-react'
import type { EChartsOption } from 'echarts'

import { colors } from '@/styles/colors'

import type { KdjPoint } from '../types'

export interface KdjChartProps {
  series: KdjPoint[]
}

/**
 * 双图联动：上图收盘价，下图 K/D/J 三线（y 轴固定 0~100）。
 * 配色从 styles/colors.ts 取，不散落 hex。
 */
export default function KdjChart({ series }: KdjChartProps) {
  const dates = series.map((p) => p.date)
  const closes = series.map((p) => p.close)
  const k = series.map((p) => p.k)
  const d = series.map((p) => p.d)
  const j = series.map((p) => p.j)

  const option: EChartsOption = {
    tooltip: { trigger: 'axis' },
    legend: { data: ['收盘价', 'K', 'D', 'J'] },
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
      { min: 0, max: 100, gridIndex: 1 },
    ],
    // 滚轮/双指可缩放，默认铺满当前周期
    dataZoom: [{ type: 'inside', xAxisIndex: [0, 1] }],
    series: [
      {
        name: '收盘价',
        type: 'line',
        data: closes,
        showSymbol: false,
        lineStyle: { color: colors.neutral },
      },
      {
        name: 'K',
        type: 'line',
        xAxisIndex: 1,
        yAxisIndex: 1,
        data: k,
        showSymbol: false,
        lineStyle: { color: colors.kdjK },
      },
      {
        name: 'D',
        type: 'line',
        xAxisIndex: 1,
        yAxisIndex: 1,
        data: d,
        showSymbol: false,
        lineStyle: { color: colors.kdjD },
      },
      {
        name: 'J',
        type: 'line',
        xAxisIndex: 1,
        yAxisIndex: 1,
        data: j,
        showSymbol: false,
        lineStyle: { color: colors.kdjJ },
      },
    ],
  }

  return <ReactECharts option={option} notMerge style={{ height: '100%', width: '100%' }} />
}
