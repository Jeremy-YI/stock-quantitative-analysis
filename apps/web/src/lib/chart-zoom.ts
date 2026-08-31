/**
 * 图表缩放窗口（ECharts dataZoom 配置）。
 *
 * 思路：**数据多拉、视窗只给近端**。
 *   - 一次拉近 2 年（HISTORY_BARS）的数据，够用户往外缩
 *   - 初始视窗落在最后 VISIBLE_BARS 根（≈2 个月），一屏看清结构
 *   - 用户滚轮 / 拖滑块自己决定看多长，不给固定档位按钮
 *
 * 为什么不是「按周期重新请求」：那样每换一次周期都要等一次网络，
 * 而且缩放这件事本来就是图表自己的交互。
 */

/** 一次加载多少根日线（≈2 年交易日） */
export const HISTORY_BARS = 500

/** 初始可见多少根（≈2 个月交易日） */
export const VISIBLE_BARS = 44

export interface TailZoomOptions {
  /** 关联的 xAxis 序号（双图联动传 [0, 1]） */
  axes?: number[]
  /** 初始可见根数 */
  visible?: number
  /** 是否附带底部滑块（主图给，副图靠滚轮即可，避免压住坐标轴） */
  slider?: boolean
}

/** 生成「初始停在尾部、可自由缩放」的 dataZoom 配置。 */
export function tailZoom(total: number, options: TailZoomOptions = {}) {
  const { axes = [0, 1], visible = VISIBLE_BARS, slider = false } = options
  const endValue = Math.max(total - 1, 0)
  const startValue = Math.max(0, total - visible)

  const inside = { type: 'inside' as const, xAxisIndex: axes, startValue, endValue }
  if (!slider) return [inside]

  return [
    inside,
    {
      type: 'slider' as const,
      xAxisIndex: axes,
      startValue,
      endValue,
      height: 16,
      bottom: 4,
    },
  ]
}
