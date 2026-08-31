'use client'

/**
 * 最新消息页（财经日报式）：
 * 每条 = 标题 + 影响评级徽标 + 未来导向 + 来源数。
 * 阅读流页面用 Container size="sm"（Page size 传下去），行宽控制在易读区间。
 */
import Link from 'next/link'

import {
  Badge,
  LoadingState,
  Caption,
  Heading,
  Page,
  PageHeader,
  StateHint,
  Stack,
  Text,
  type Tone,
} from '@/design'

import useNews from '../use-news'
import type { NewsItem } from '../types'

// 影响评级 → 语义 tone（不再散落 bg-red-50 这类调色板类）
const IMPACT_TONE: Record<string, Tone> = {
  改变定价: 'danger',
  显著影响: 'warn',
  结构性关注: 'info',
}

export default function NewsView() {
  const { data, loading, error } = useNews()

  return (
    <Page size='md'>
      <PageHeader
        title='最新消息'
        description={
          data ? `${data.date} · ${data.source}` : '财经日报：标题 + 影响评级 + 未来导向'
        }
      />

      {loading && <LoadingState label='加载最新消息' skeleton rows={4} />}
      {error && <StateHint kind='error'>加载失败：{error}</StateHint>}

      {data && data.items.length === 0 && <StateHint kind='empty'>今天还没有消息</StateHint>}

      {data && data.items.length > 0 && (
        <Stack gap='md' as='ul'>
          {data.items.map((item, i) => (
            <NewsCard key={i} item={item} />
          ))}
        </Stack>
      )}
    </Page>
  )
}

function NewsCard({ item }: { item: NewsItem }) {
  return (
    <li>
      <Link
        href={`/news/${item.id}`}
        className='block rounded-lg border border-border bg-card p-4 transition-colors hover:bg-surface-hover mobile-portrait:p-5'
      >
        {/* 手机上徽标掉到标题下面，桌面上贴右侧 */}
        <div className='flex flex-col gap-2 mobile-portrait:flex-row mobile-portrait:items-start mobile-portrait:justify-between mobile-portrait:gap-4'>
          <Heading level={3} className='min-w-0'>
            {item.title}
          </Heading>
          <Badge
            tone={IMPACT_TONE[item.impact] ?? 'neutral'}
            className='self-start mobile-portrait:shrink-0'
          >
            {item.impact}
          </Badge>
        </div>
        <Text size='body' tone='muted' className='mt-2'>
          <span className='text-foreground/60'>未来导向：</span>
          {item.outlook}
        </Text>
        <Caption className='mt-1.5'>来源 {item.sources} 条 · 点开看详情与相关标的</Caption>
      </Link>
    </li>
  )
}
