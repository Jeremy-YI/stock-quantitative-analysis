'use client'

import ReactECharts from 'echarts-for-react'
import type { EChartsOption } from 'echarts'

import { colors } from '@/styles/colors'

import type { CandlePoint, Signal } from '../types'
import { strategyLabel } from '../strategy-label'

export interface CandleChartProps {
  series: CandlePoint[]
  /** 买入信号：在对应交易日打标记 */
  signals?: Signal[]
  height?: number
}

/**
 * 日 K 线（蜡烛图）+ 成交量 + 买入信号标记。
 *
 * A股配色：阳线红、阴线绿（与全站 up/down 一致，颜色只从 styles/colors.ts 取）。
 * 买点用 markPoint 落在当日最低价下方，鼠标悬停显示是哪几个战法触发的。
 */
export default function CandleChart({ series, signals = [], height = 420 }: CandleChartProps) {
  const dates = series.map((p) => p.date)
  const ohlc = series.map((p) => [p.open, p.close, p.low, p.high])
  const volumes = series.map((p, i) => ({
    value: p.volume,
    itemStyle: { color: p.close >= p.open ? colors.up : colors.down },
    // 保留索引方便 tooltip 对齐
    name: dates[i],
  }))

  // 同一天可能触发多个战法，合并成一个标记
  const byDate = new Map<string, Signal[]>()
  signals.forEach((s) => {
    const arr = byDate.get(s.triggered_at) ?? []
    arr.push(s)
    byDate.set(s.triggered_at, arr)
  })

  type Mark = { name: string; coord: [number, number]; value: string; itemStyle: { color: string } }
  const marks: Mark[] = []
  byDate.forEach((group, date) => {
    const i = dates.indexOf(date)
    if (i < 0) return
    marks.push({
      name: '买点',
      coord: [i, series[i].low],
      value: group.map((s) => strategyLabel(s.strategy)).join('/'),
      itemStyle: { color: colors.up },
    })
  })

  const option: EChartsOption = {
    animation: false,
    tooltip: { trigger: 'axis', axisPointer: { type: 'cross' } },
    legend: { data: ['日K', '成交量'], top: 0 },
    grid: [
      { left: 56, right: 16, top: 32, height: '58%' },
      { left: 56, right: 16, top: '76%', height: '16%' },
    ],
    xAxis: [
      { type: 'category', data: dates, gridIndex: 0, axisLabel: { hideOverlap: true } },
      { type: 'category', data: dates, gridIndex: 1, axisLabel: { show: false } },
    ],
    yAxis: [
      { scale: true, gridIndex: 0, splitLine: { show: true } },
      { scale: true, gridIndex: 1, splitLine: { show: false }, axisLabel: { show: false } },
    ],
    // 数据已按所选周期截取，默认铺满整窗；滚轮/拖动可继续放大缩小
    dataZoom: [
      { type: 'inside', xAxisIndex: [0, 1], start: 0, end: 100 },
      { type: 'slider', xAxisIndex: [0, 1], height: 16, bottom: 4, start: 0, end: 100 },
    ],
    series: [
      {
        name: '日K',
        type: 'candlestick',
        data: ohlc,
        itemStyle: {
          color: colors.up, // 阳线实体
          color0: colors.down, // 阴线实体
          borderColor: colors.up,
          borderColor0: colors.down,
        },
        markPoint: {
          symbol: 'pin',
          symbolSize: 34,
          label: { formatter: 'B', color: '#fff', fontSize: 10 },
          data: marks,
        },
      },
      {
        name: '成交量',
        type: 'bar',
        xAxisIndex: 1,
        yAxisIndex: 1,
        data: volumes,
      },
    ],
  }

  return (
    <ReactECharts
      option={option}
      notMerge
      style={{ height: `${height}px`, width: '100%' }}
      data-testid='candle-chart'
    />
  )
}
