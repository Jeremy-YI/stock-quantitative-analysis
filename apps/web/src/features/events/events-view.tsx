'use client'

/**
 * 事件日历页：关键会议 / 数据 / 财报，按日期升序，重要度徽标。
 * 小屏把「类型」列收起（信息密度跟着屏幕给），日期列等宽不换行。
 */
import {
  Badge,
  Card,
  Page,
  PageHeader,
  StateHint,
  TBody,
  TD,
  TH,
  THead,
  TR,
  Table,
  TableScroll,
  type Tone,
} from '@/design'

import useEvents from './use-events'
import type { EventItem } from './types'

// 重要度 → 语义 tone
const IMPORTANCE_TONE: Record<string, Tone> = {
  高: 'danger',
  中: 'warn',
  低: 'neutral',
}

export default function EventsView() {
  const { data, loading, error } = useEvents()

  return (
    <Page size="md">
      <PageHeader title="事件日历" description={data?.note ?? '央行会议 / 关键数据 / 财报'} />

      {loading && <StateHint>加载中…</StateHint>}
      {error && <StateHint kind="error">加载失败：{error}</StateHint>}

      {data && (
        <Card className="overflow-hidden p-0">
          <TableScroll bare>
            <Table minWidth="sm">
              <THead>
                <TR>
                  <TH>日期</TH>
                  <TH>事件</TH>
                  <TH hideBelow='mobilePortrait'>类型</TH>
                  <TH align="right">重要度</TH>
                </TR>
              </THead>
              <TBody>
                {data.events.map((e, i) => (
                  <EventRow key={i} event={e} />
                ))}
              </TBody>
            </Table>
          </TableScroll>
        </Card>
      )}
    </Page>
  )
}

function EventRow({ event }: { event: EventItem }) {
  return (
    <TR hoverable>
      <TD mono nowrap className="text-muted-foreground">
        {event.date}
      </TD>
      <TD className="font-medium">{event.name}</TD>
      <TD hideBelow='mobilePortrait'>
        <Badge tone="muted" size="sm">
          {event.type}
        </Badge>
      </TD>
      <TD align="right">
        <Badge tone={IMPORTANCE_TONE[event.importance] ?? 'neutral'} size="sm">
          {event.importance}
        </Badge>
      </TD>
    </TR>
  )
}
