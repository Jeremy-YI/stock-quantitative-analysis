'use client'

import ReactECharts from 'echarts-for-react'
import type { EChartsOption } from 'echarts'

import { colors } from '@/styles/colors'

import type { OverlayCell } from './types'

export interface OverlayHeatmapProps {
  cells: OverlayCell[]
}

/**
 * 两两策略叠加超额矩阵热力图。
 * 单元格 = 两策略「同标的同日触发」的标的持有 N 日超额胜率（pp，正红负绿）。
 * 矩阵对称（A×B == B×A）；n=0 或无超额数据显示为中性灰。
 */
export default function OverlayHeatmap({ cells }: OverlayHeatmapProps) {
  const names = Array.from(
    new Set(cells.flatMap((c) => [c.strategy_a, c.strategy_b]))
  ).sort()

  // 矩阵值：对称填充，值 = 超额胜率（pp），无数据用 null
  const byPair = new Map<string, number | null>()
  for (const c of cells) {
    const v = c.excess_win_rate === null ? null : c.excess_win_rate * 100
    byPair.set(`${c.strategy_a}×${c.strategy_b}`, v)
  }

  const data: [number, number, number][] = []
  names.forEach((a, ia) => {
    names.forEach((b, ib) => {
      const v =
        byPair.get(`${a}×${b}`) ?? byPair.get(`${b}×${a}`) ?? null
      if (v !== null) {
        data.push([ib, ia, +v.toFixed(1)])
      }
    })
  })

  const option: EChartsOption = {
    tooltip: {
      position: 'top',
      formatter: (params) => {
        const p = params as unknown as { value: [number, number, number] }
        const [ib, ia, v] = p.value
        return `${names[ia]} × ${names[ib]}: ${v >= 0 ? '+' : ''}${v}pp`
      },
    },
    grid: { left: 10, right: 40, top: 10, bottom: 80 },
    xAxis: {
      type: 'category',
      data: names,
      splitArea: { show: true },
      axisLabel: { rotate: 45 },
    },
    yAxis: {
      type: 'category',
      data: names,
      splitArea: { show: true },
    },
    visualMap: {
      min: -15,
      max: 15,
      calculable: true,
      orient: 'horizontal',
      right: 'center',
      bottom: 0,
      inRange: {
        color: [colors.down, '#e5e7eb', colors.up],
      },
      text: ['+pp', '-pp'],
    },
    series: [
      {
        name: '叠加超额胜率',
        type: 'heatmap',
        data,
        label: {
          show: true,
          formatter: (p) => {
            const v = (p.value as number[])[2]
            return typeof v === 'number' ? String(v) : ''
          },
        },
        emphasis: { itemStyle: { shadowBlur: 10, shadowColor: 'rgba(0,0,0,0.3)' } },
      },
    ],
  }

  if (names.length === 0) {
    return (
      <p className="py-10 text-center text-sm text-muted-foreground">
        暂无叠加分析数据（需在含信号的区间内跑回测）
      </p>
    )
  }

  return (
    <ReactECharts
      option={option}
      notMerge
      style={{ height: '100%', width: '100%' }}
    />
  )
}
