import DashboardView from '@/features/dashboard/dashboard-view'

export const metadata = {
  title: '运维看板 · 股市量化平台',
}

/**
 * 运维/研发看板（内部页，不在导航里）：
 * 策略超额胜率、市场基线、最近全市场扫描、调度任务状态。
 * 这些是调参和排障用的工程指标，产品首页不该出现。
 */
export default function Page() {
  return <DashboardView />
}
