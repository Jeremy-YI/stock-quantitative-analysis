import EventDetailView from '@/features/events/event-detail-view'

export const metadata = {
  title: '事件详情 · 股市量化平台',
}

export default async function Page({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params
  return <EventDetailView id={id} />
}
