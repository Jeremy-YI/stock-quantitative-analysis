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
  kdjK: '#eab308', // KDJ 的 K 线
  kdjD: '#22d3ee', // KDJ 的 D 线
  kdjJ: '#a855f7', // KDJ 的 J 线
  rsi: '#6366f1', // RSI 线
  rsiRef: '#94a3b8', // RSI 30/70 参考线
  mavol1: '#f59e0b', // MAVOL1（5 日量均线）
  mavol2: '#2563eb', // MAVOL2（10 日量均线）
  lifeline: '#a855f7', // 生命线（背离中线）
  yinVolumeLine: '#14b8a6', // 阴量定价线
  attackDefense: '#f97316', // 进攻K防线
} as const
