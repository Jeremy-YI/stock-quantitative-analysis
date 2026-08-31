'use client'

import ReactECharts from 'echarts-for-react'
import type { EChartsOption } from 'echarts'

import { colors } from '@/styles/colors'

import type { MacdPoint } from '../types'

export interface MacdChartProps {
  series: MacdPoint[]
}

/**
 * 双图联动：上图收盘价，下图 MACD（红柱=正、绿柱=负）+ DIF/DEA 线。
 * 红涨绿跌配色从 styles/colors.ts 取，不散落 hex。
 */
export default function MacdChart({ series }: MacdChartProps) {
  const dates = series.map((p) => p.date)
  const closes = series.map((p) => p.close)
  const dif = series.map((p) => p.dif)
  const dea = series.map((p) => p.dea)
  const macd = series.map((p) => p.macd)

  const option: EChartsOption = {
    tooltip: { trigger: 'axis' },
    legend: { data: ['收盘价', 'DIF', 'DEA', 'MACD'] },
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
        name: 'MACD',
        type: 'bar',
        xAxisIndex: 1,
        yAxisIndex: 1,
        data: macd.map((value) => ({
          value,
          itemStyle: { color: value >= 0 ? colors.up : colors.down },
        })),
      },
      {
        name: 'DIF',
        type: 'line',
        xAxisIndex: 1,
        yAxisIndex: 1,
        data: dif,
        showSymbol: false,
        lineStyle: { color: colors.dif },
      },
      {
        name: 'DEA',
        type: 'line',
        xAxisIndex: 1,
        yAxisIndex: 1,
        data: dea,
        showSymbol: false,
        lineStyle: { color: colors.dea },
      },
    ],
  }

  return <ReactECharts option={option} notMerge style={{ height: '100%', width: '100%' }} />
}
