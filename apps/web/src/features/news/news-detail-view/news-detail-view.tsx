'use client'

/**
 * 单条消息详情页：全文 + 相关标的 + 相关消息。
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
  Row,
  Section,
  Stack,
  Text,
  type Tone,
} from '@/design'

import { useNewsDetail } from '../use-news'

const IMPACT_TONE: Record<string, Tone> = {
  改变定价: 'danger',
  显著影响: 'warn',
  结构性关注: 'info',
}

export default function NewsDetailView({ id }: { id: string }) {
  const { data, loading, error } = useNewsDetail(id)
  const item = data?.item

  return (
    <Page size='md'>
      {loading && <LoadingState label='加载消息详情' skeleton rows={4} />}
      {!loading && error && <ErrorState message={error} />}
      {!loading && !error && !item && (
        <EmptyState title='消息不存在' description='可能已下线，返回列表看看其他消息' />
      )}

      {item && (
        <>
          <PageHeader
            title={item.title}
            description={
              <span className='flex flex-wrap items-center gap-2'>
                <Badge tone={IMPACT_TONE[item.impact] ?? 'neutral'} size='sm'>
                  {item.impact}
                </Badge>
                <Badge tone='muted' size='sm'>
                  {item.level}
                </Badge>
                <Caption>
                  {data?.date} · 来源 {item.sources} 条
                </Caption>
              </span>
            }
            actions={
              <Link href='/news' className='text-body-sm text-accent hover:underline'>
                返回最新消息
              </Link>
            }
          />

          {/* 全文 */}
          <Card className='shadow-none'>
            <CardContent className='space-y-3 pt-4 mobile-portrait:pt-5'>
              {item.detail.split('\n').map((para, i) =>
                para.trim() ? (
                  <Text key={i} size='body-lg' className='leading-relaxed'>
                    {para.trim()}
                  </Text>
                ) : null,
              )}
            </CardContent>
          </Card>

          {/* 未来导向 */}
          <Section title='未来导向'>
            <Card className='shadow-none'>
              <CardContent className='pt-4 mobile-portrait:pt-5'>
                <Text size='body'>{item.outlook}</Text>
              </CardContent>
            </Card>
          </Section>

          {/* 相关标的 */}
          {item.related_symbols.length > 0 && (
            <Section title='相关标的' description='受这条消息影响的方向（点代码进 K 线）'>
              <Stack gap='sm'>
                {item.related_symbols.map((s) => (
                  <Link
                    key={s.symbol}
                    href={`/stocks/${s.symbol}`}
                    className='flex items-baseline justify-between gap-3 rounded-lg border border-border bg-card px-4 py-3 transition-colors hover:bg-surface-hover'
                  >
                    <span className='min-w-0'>
                      <span className='font-mono text-caption text-muted-foreground'>
                        {s.symbol}
                      </span>
                      <span className='ml-2 font-medium'>{s.name}</span>
                      <span className='ml-2 text-body-sm text-muted-foreground'>{s.reason}</span>
                    </span>
                  </Link>
                ))}
              </Stack>
            </Section>
          )}

          {/* 相关消息 */}
          {data && data.related_news.length > 0 && (
            <Section title='相关内容' description='同主题的其他消息'>
              <Stack gap='sm'>
                {data.related_news.map((n) => (
                  <Link
                    key={n.id}
                    href={`/news/${n.id}`}
                    className='rounded-lg border border-border bg-card px-4 py-3 transition-colors hover:bg-surface-hover'
                  >
                    <div className='flex items-start justify-between gap-3'>
                      <Text size='body-sm' className='min-w-0'>
                        {n.title}
                      </Text>
                      <Badge
                        tone={IMPACT_TONE[n.impact] ?? 'neutral'}
                        size='sm'
                        className='shrink-0'
                      >
                        {n.impact}
                      </Badge>
                    </div>
                  </Link>
                ))}
              </Stack>
            </Section>
          )}
        </>
      )}
    </Page>
  )
}
