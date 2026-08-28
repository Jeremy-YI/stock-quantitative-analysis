/**
 * A股语义色（唯一来源：ECharts 等 JS 场景从这里取，禁止在组件里散落 hex）。
 * 注意：Tailwind 工具类的同名语义色定义在 styles/globals.css 的 @theme 里，
 * 两处值保持一致。
 */
export const colors = {
  up: '#ef4444', // 红：涨
  down: '#22c55e', // 绿：跌
  neutral: '#64748b', // 灰：平/中性
  dif: '#2563eb', // DIF 线（快慢线差）
  dea: '#f59e0b', // DEA 线（信号线）
} as const
