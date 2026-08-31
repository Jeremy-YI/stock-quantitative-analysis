'use client'

import ReactECharts from 'echarts-for-react'
import type { EChartsOption } from 'echarts'

import { tailZoom } from '@/lib/chart-zoom'
import { colors } from '@/styles/colors'

import type { PricingLinePoint } from '../types'

export interface PricingLinesChartProps {
  series: PricingLinePoint[]
}

/**
 * 单图：收盘价 + 三条定价线（生命线 / 阴量定价线 / 进攻K防线）。
 * 定价线未定义的日子值为 null，用 connectNulls 忽略。
 */
export default function PricingLinesChart({ series }: PricingLinesChartProps) {
  const dates = series.map((p) => p.date)
  const closes = series.map((p) => p.close)
  const lifeline = series.map((p) => p.lifeline)
  const yin = series.map((p) => p.yin_volume_line)
  const attack = series.map((p) => p.attack_defense)

  const option: EChartsOption = {
    tooltip: { trigger: 'axis' },
    legend: { data: ['收盘价', '生命线', '阴量定价线', '进攻K防线'] },
    grid: { left: 60, right: 20, top: 40, bottom: 40 },
    xAxis: { type: 'category', data: dates },
    yAxis: { scale: true },
    // 初始停在最近约 2 个月，滚轮/双指往外缩可看更早历史
    dataZoom: tailZoom(dates.length, { axes: [0] }),
    series: [
      {
        name: '收盘价',
        type: 'line',
        data: closes,
        showSymbol: false,
        lineStyle: { color: colors.neutral, width: 1.5 },
      },
      {
        name: '生命线',
        type: 'line',
        data: lifeline,
        showSymbol: false,
        connectNulls: true,
        lineStyle: { color: colors.lifeline, type: 'dashed' },
      },
      {
        name: '阴量定价线',
        type: 'line',
        data: yin,
        showSymbol: false,
        connectNulls: true,
        lineStyle: { color: colors.yinVolumeLine },
      },
      {
        name: '进攻K防线',
        type: 'line',
        data: attack,
        showSymbol: false,
        step: 'end',
        connectNulls: true,
        lineStyle: { color: colors.attackDefense },
      },
    ],
  }

  return <ReactECharts option={option} style={{ height: 420 }} notMerge />
}
