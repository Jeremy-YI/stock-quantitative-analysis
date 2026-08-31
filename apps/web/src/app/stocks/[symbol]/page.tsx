import StockDetailView from '@/features/stocks/stock-detail-view'

export const metadata = {
  title: '个股详情 · 股市量化平台',
}

/** 个股详情：/stocks/600519?date=2026-08-28 */
export default async function Page({
  params,
  searchParams,
}: {
  params: Promise<{ symbol: string }>
  searchParams: Promise<{ date?: string }>
}) {
  const { symbol } = await params
  const { date } = await searchParams
  return <StockDetailView symbol={symbol} date={date} />
}
