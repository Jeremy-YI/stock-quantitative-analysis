'use client'

/**
 * 单个事件详情页：说明 + 历史数据（过去的市场反应）。
 */
import Link from 'next/link'

import {
  Badge,
  Caption,
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  EmptyState,
  ErrorState,
  Heading,
  LoadingState,
  Page,
  PageHeader,
  Section,
  Stack,
  TBody,
  TD,
  TH,
  THead,
  TR,
  Table,
  TableScroll,
  Text,
  type Tone,
} from '@/design'

import { useEventDetail } from '../use-events'

const IMPORTANCE_TONE: Record<string, Tone> = {
  高: 'danger',
  中: 'warn',
  低: 'neutral',
}

export default function EventDetailView({ id }: { id: string }) {
  const { data, loading, error } = useEventDetail(id)
  const event = data?.event

  return (
    <Page size='md'>
      {loading && <LoadingState label='加载事件详情' skeleton rows={4} />}
      {!loading && error && <ErrorState message={error} />}
      {!loading && !error && !event && (
        <EmptyState title='事件不存在' description='返回事件日历看看其他事件' />
      )}

      {event && (
        <>
          <PageHeader
            title={event.name}
            description={
              <span className='flex flex-wrap items-center gap-2'>
                <Badge tone='muted' size='sm'>
                  {event.type}
                </Badge>
                <Badge tone={IMPORTANCE_TONE[event.importance] ?? 'neutral'} size='sm'>
                  {event.importance}重要度
                </Badge>
                <Caption>{event.date}</Caption>
              </span>
            }
            actions={
              <Link href='/events' className='text-body-sm text-accent hover:underline'>
                返回事件日历
              </Link>
            }
          />

          {/* 事件说明 */}
          <Card className='shadow-none'>
            <CardHeader>
              <CardTitle>事件说明</CardTitle>
            </CardHeader>
            <CardContent>
              <Text size='body-lg' className='leading-relaxed'>
                {event.description || '暂无说明'}
              </Text>
            </CardContent>
          </Card>

          {/* 历史数据 */}
          <Section
            title='历史数据'
            description={
              event.history.length > 0
                ? '该事件历史上的发生记录与当时的市场反应'
                : '暂无历史记录（接入真实数据源后自动补）'
            }
          >
            {event.history.length > 0 ? (
              <Card className='overflow-hidden p-0 shadow-none'>
                <TableScroll bare>
                  <Table minWidth='sm'>
                    <THead sticky>
                      <TR>
                        <TH>日期</TH>
                        <TH>当时情况 / 市场反应</TH>
                      </TR>
                    </THead>
                    <TBody>
                      {event.history.map((h, i) => (
                        <TR key={i} hoverable>
                          <TD mono nowrap className='text-muted-foreground'>
                            {h.date}
                          </TD>
                          <TD>
                            <Text size='body-sm'>{h.note}</Text>
                          </TD>
                        </TR>
                      ))}
                    </TBody>
                  </Table>
                </TableScroll>
              </Card>
            ) : (
              <EmptyState
                compact
                title='暂无历史数据'
                description='历史数据为演示占位，后续接真实数据源'
              />
            )}
          </Section>

          <Caption>{data?.note}</Caption>
        </>
      )}
    </Page>
  )
}
