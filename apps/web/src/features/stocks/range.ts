/**
 * 图表数据窗口（不是「固定周期档位」）。
 *
 * 交互约定（Jeremy 2026-08-31 定）：
 *   - 一次加载近 2 年日线，**初始视窗只给最近约 2 个月**
 *   - 想看更长，用户在图上往外缩 / 拖底部滑块，自己决定看多少
 *   - 不给 1个月/3个月/1年 这种固定按钮，避免每换一次都要等一次网络
 *
 * 值集中在 lib/chart-zoom.ts（图表侧也要用同一份）。
 */
export { HISTORY_BARS, VISIBLE_BARS } from '@/lib/chart-zoom'

/** 「加载全部历史」时用：不传 limit，后端返回全量 */
export const FULL_HISTORY = undefined
