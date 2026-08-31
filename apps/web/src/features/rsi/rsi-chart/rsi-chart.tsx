'use client'

import ReactECharts from 'echarts-for-react'
import type { EChartsOption } from 'echarts'

import { colors } from '@/styles/colors'

import type { RsiPoint } from '../types'

export interface RsiChartProps {
  series: RsiPoint[]
}

/**
 * 双图联动：上图收盘价，下图 RSI 单线（y 轴固定 0~100）+ 30/70 参考虚线。
 */
export default function RsiChart({ series }: RsiChartProps) {
  const dates = series.map((p) => p.date)
  const closes = series.map((p) => p.close)
  const rsi = series.map((p) => p.rsi)

  const option: EChartsOption = {
    tooltip: { trigger: 'axis' },
    legend: { data: ['收盘价', 'RSI'] },
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
    series: [
      {
        name: '收盘价',
        type: 'line',
        data: closes,
        showSymbol: false,
        lineStyle: { color: colors.neutral },
      },
      {
        name: 'RSI',
        type: 'line',
        xAxisIndex: 1,
        yAxisIndex: 1,
        data: rsi,
        showSymbol: false,
        lineStyle: { color: colors.rsi },
        markLine: {
          silent: true,
          symbol: 'none',
          lineStyle: { color: colors.rsiRef, type: 'dashed' },
          label: { formatter: '{b}' },
          data: [
            { yAxis: 70, name: '超买 70' },
            { yAxis: 30, name: '超卖 30' },
          ],
        },
      },
    ],
  }

  return <ReactECharts option={option} notMerge style={{ height: '100%', width: '100%' }} />
}
