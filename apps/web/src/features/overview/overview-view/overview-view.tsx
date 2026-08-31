'use client'

/**
 * 概览页（首页）。
 *
 * 只回答一个问题：**今天怎么做**。每一块都是后面某个页面的入口，
 * 不再放策略超额胜率/基线/调度耗时那种工程指标（已挪到 /ops）。
 *
 * 六块：
 *   1 市场状态   大盘位置与是否建议开仓（regime，本地数据算）
 *   2 资金主线   板块资金 即时 + 5日 TOP3，标出两窗口同向
 *   3 主题龙头   ETF 资金流里可直接买的标的
 *   4 今日精选   资金最强板块里的信号股（已过滤 ST），点名字进 K 线
 *   5 要闻速览   影响评级最高的几条
 *   6 临近事件   未来 7 天高重要度
 */
import Link from 'next/link'

import {
  Badge,
  Caption,
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  Grid,
  Num,
  Page,
  PageHeader,
  Row,
  Section,
  Skeleton,
  StateHint,
  Stack,
  Text,
  type Tone,
} from '@/design'
import useDashboard from '@/features/dashboard/use-dashboard'
import useEvents from '@/features/events/use-events'
import useNews from '@/features/news/use-news'
import useEtfFlow from '@/features/sectors/use-etf-flow'
import useSectors from '@/features/sectors/use-sectors'
import { useRecommendations } from '@/features/recommendations/use-recommendations'
import { strategyLabel } from '@/features/stocks/strategy-label'
import { formatPct } from '@/lib/format'

const DEFAULT_SCAN_DATE = '2026-08-28'
const TOP_N = 3

// 影响评级 / 重要度 → 语义 tone
const IMPACT_TONE: Record<string, Tone> = {
  改变定价: 'danger',
  显著影响: 'warn',
  结构性关注: 'info',
  高: 'danger',
  中: 'warn',
  低: 'neutral',
}

export default function OverviewView() {
  const { data: dash, loading: dashLoading } = useDashboard()
  const { data: intraday, loading: flowLoading } = useSectors('即时')
  const { data: fiveDay } = useSectors('5日排行')
  const { data: etf } = useEtfFlow(6)
  const { data: news } = useNews()
  const { data: events } = useEvents()

  // 资金最强板块 → 拿它的成分股信号当「今日精选」（资金主线与个股逻辑自洽）
  const leadSector = intraday?.top_inflow?.[0]?.sector ?? ''
  const { data: picks, loading: picksLoading } = useRecommendations(leadSector, DEFAULT_SCAN_DATE)

  const regime = dash?.regime
  const allow = regime?.allow_open
  const inflow = (intraday?.top_inflow ?? []).slice(0, TOP_N)
  const outflow = (intraday?.top_outflow ?? []).slice(0, TOP_N)
  // 两个窗口同向的板块才是「持续」的资金主线
  const fiveDayInflow = new Set((fiveDay?.top_inflow ?? []).map((s) => s.sector))
  const topPicks = (picks?.stocks ?? []).slice(0, 6)
  const hotNews = (news?.items ?? [])
    .slice()
    .sort((a, b) => impactRank(b.impact) - impactRank(a.impact))
    .slice(0, 3)
  const soonEvents = upcoming(events?.events ?? [], 7)

  return (
    <Page size='lg'>
      <PageHeader
        title='概览'
        description={`今天怎么做：市场状态 → 资金主线 → 个股 → 消息与事件${
          dash?.as_of ? ` · 快照日 ${dash.as_of}` : ''
        }`}
      />

      {/* 1 市场状态 */}
      <Section title='市场状态' description='大盘位置与开仓建议（本地日线计算，非实时）'>
        {dashLoading && <Skeleton className='h-24 w-full' />}
        {!dashLoading && !regime && <StateHint kind='empty'>暂无市场环境快照</StateHint>}
        {regime && (
          <Grid cols={{ base: 2, mobileLandscape: 4 }} gap='sm'>
            <Metric
              label='大盘 20 日'
              value={formatPct(regime.index_20d_return)}
              hint={regime.index_20d_label}
            />
            <Metric
              label='市场活跃度'
              value={regime.activity === null ? '—' : regime.activity.toFixed(2)}
              hint={regime.activity_label}
            />
            <Metric
              label='距 120 日高点'
              value={formatPct(regime.drawdown)}
              hint={regime.drawdown_label}
            />
            <Metric
              label='开仓建议'
              value={
                allow === null || allow === undefined ? '—' : allow ? '允许开仓' : '不建议开仓'
              }
              tone={allow === true ? 'up' : allow === false ? 'down' : 'neutral'}
            />
          </Grid>
        )}
      </Section>

      {/* 2 资金主线 + 3 主题龙头 */}
      <Grid cols={{ base: 1, desktop: 2 }} gap='lg'>
        <Card className='shadow-none'>
          <CardHeader>
            <CardTitle>资金主线</CardTitle>
            <Link href='/sectors' className='text-caption text-accent hover:underline'>
              看全部板块 →
            </Link>
          </CardHeader>
          <CardContent>
            {flowLoading && <Skeleton className='h-32 w-full' />}
            {!flowLoading && inflow.length === 0 && (
              <StateHint kind='empty'>暂无资金流快照</StateHint>
            )}
            {inflow.length > 0 && (
              <Stack gap='sm'>
                <Caption>净流入 TOP{inflow.length}</Caption>
                {inflow.map((s) => (
                  <FlowRow
                    key={s.sector}
                    sector={s.sector}
                    net={s.net}
                    change={s.change_pct}
                    persistent={fiveDayInflow.has(s.sector)}
                  />
                ))}
                <Caption className='mt-2'>净流出 TOP{outflow.length}</Caption>
                {outflow.map((s) => (
                  <FlowRow key={s.sector} sector={s.sector} net={s.net} change={s.change_pct} />
                ))}
              </Stack>
            )}
          </CardContent>
        </Card>

        <Card className='shadow-none'>
          <CardHeader>
            <CardTitle>主题龙头 ETF</CardTitle>
            <Link href='/sectors' className='text-caption text-accent hover:underline'>
              看 ETF 资金流 →
            </Link>
          </CardHeader>
          <CardContent>
            {!etf && <Skeleton className='h-32 w-full' />}
            {etf && etf.leaders.length === 0 && <StateHint kind='empty'>暂无 ETF 快照</StateHint>}
            {etf && etf.leaders.length > 0 && (
              <Stack gap='sm'>
                {etf.leaders.slice(0, 6).map((e) => (
                  <div key={e.code} className='flex items-baseline justify-between gap-2'>
                    <span className='min-w-0 truncate'>
                      <span className='text-body-sm text-muted-foreground'>{e.theme}</span>
                      <span className='ml-2 font-medium'>{e.name}</span>
                    </span>
                    <span className='flex shrink-0 items-baseline gap-3 font-mono text-body-sm'>
                      <span className='text-muted-foreground'>{e.mcap.toFixed(0)}亿</span>
                      <Num value={e.change_pct} suffix='%' />
                    </span>
                  </div>
                ))}
              </Stack>
            )}
          </CardContent>
        </Card>
      </Grid>

      {/* 4 今日精选 */}
      <Section
        title='今日精选'
        description={
          leadSector ? `资金最强板块「${leadSector}」里触发战法的个股（已剔除 ST）` : '等资金流快照'
        }
        actions={
          <Link href='/recommendations' className='text-body-sm text-accent hover:underline'>
            看全部推荐 →
          </Link>
        }
      >
        {picksLoading && <Skeleton className='h-24 w-full' />}
        {!picksLoading && topPicks.length === 0 && (
          <StateHint kind='empty'>该板块当日没有触发信号</StateHint>
        )}
        {topPicks.length > 0 && (
          <Grid cols={{ base: 1, mobilePortrait: 2, desktop: 3 }} gap='sm'>
            {topPicks.map((p) => (
              <Link
                key={p.symbol}
                href={`/stocks/${p.symbol}?date=${DEFAULT_SCAN_DATE}`}
                className='rounded-lg border border-border bg-card p-3 transition-colors hover:bg-surface-hover'
              >
                <div className='flex items-baseline justify-between gap-2'>
                  <span className='font-medium'>{p.name || p.symbol}</span>
                  <span className='font-mono text-caption text-muted-foreground'>{p.symbol}</span>
                </div>
                <Row gap='tight' className='mt-1.5'>
                  {p.signals.slice(0, 3).map((s, i) => (
                    <Badge key={i} tone='accent' size='sm'>
                      {strategyLabel(s.strategy)}
                    </Badge>
                  ))}
                </Row>
              </Link>
            ))}
          </Grid>
        )}
      </Section>

      {/* 5 要闻 + 6 事件 */}
      <Grid cols={{ base: 1, desktop: 2 }} gap='lg'>
        <Card className='shadow-none'>
          <CardHeader>
            <CardTitle>要闻速览</CardTitle>
            <Link href='/news' className='text-caption text-accent hover:underline'>
              看全部消息 →
            </Link>
          </CardHeader>
          <CardContent>
            {!news && <Skeleton className='h-32 w-full' />}
            {news && (
              <Stack gap='sm'>
                {hotNews.map((n, i) => (
                  <div key={i} className='flex items-start justify-between gap-3'>
                    <Text size='body-sm' className='min-w-0'>
                      {n.title}
                    </Text>
                    <Badge tone={IMPACT_TONE[n.impact] ?? 'neutral'} size='sm' className='shrink-0'>
                      {n.impact}
                    </Badge>
                  </div>
                ))}
                <Caption>
                  {news.date} · {news.source}
                </Caption>
              </Stack>
            )}
          </CardContent>
        </Card>

        <Card className='shadow-none'>
          <CardHeader>
            <CardTitle>临近事件</CardTitle>
            <Link href='/events' className='text-caption text-accent hover:underline'>
              看事件日历 →
            </Link>
          </CardHeader>
          <CardContent>
            {!events && <Skeleton className='h-32 w-full' />}
            {events && soonEvents.length === 0 && (
              <StateHint kind='empty'>未来 7 天没有高重要度事件</StateHint>
            )}
            {soonEvents.length > 0 && (
              <Stack gap='sm'>
                {soonEvents.map((e, i) => (
                  <div key={i} className='flex items-baseline justify-between gap-3'>
                    <span className='min-w-0 truncate'>
                      <span className='font-mono text-caption text-muted-foreground'>{e.date}</span>
                      <span className='ml-2 text-body-sm'>{e.name}</span>
                    </span>
                    <Badge
                      tone={IMPACT_TONE[e.importance] ?? 'neutral'}
                      size='sm'
                      className='shrink-0'
                    >
                      {e.importance}
                    </Badge>
                  </div>
                ))}
              </Stack>
            )}
          </CardContent>
        </Card>
      </Grid>

      <Caption>
        数据口径：市场状态与个股信号来自本地日线计算；板块资金 / ETF 为收盘后快照；
        消息与事件目前是种子数据，接入真实源后此处会显示采集时间。AI 一句话结论等消息真实化后再上，
        不拿假数据生成结论。
      </Caption>
    </Page>
  )
}

function Metric({
  label,
  value,
  hint,
  tone,
}: {
  label: string
  value: string
  hint?: string | null
  tone?: Tone
}) {
  const toneClass =
    tone === 'up'
      ? 'text-up'
      : tone === 'down'
        ? 'text-down'
        : tone === 'neutral'
          ? 'text-neutral'
          : ''
  return (
    <div className='rounded-lg border border-border bg-card p-3'>
      <Caption>{label}</Caption>
      <div className={`mt-0.5 text-h3 font-semibold tabular-nums ${toneClass}`}>{value}</div>
      {hint ? <Caption className='block'>{hint}</Caption> : null}
    </div>
  )
}

function FlowRow({
  sector,
  net,
  change,
  persistent = false,
}: {
  sector: string
  net: number
  change: number
  persistent?: boolean
}) {
  return (
    <div className='flex items-baseline justify-between gap-2'>
      <span className='flex min-w-0 items-center gap-1.5'>
        <Link
          href={`/recommendations?sector=${encodeURIComponent(sector)}`}
          className='truncate font-medium text-accent hover:underline'
        >
          {sector}
        </Link>
        {persistent && (
          <Badge tone='up' size='sm'>
            5日同向
          </Badge>
        )}
      </span>
      <span className='flex shrink-0 items-baseline gap-3 font-mono text-body-sm'>
        <Num value={net} />
        <Num value={change} suffix='%' />
      </span>
    </div>
  )
}

/** 影响评级排序权重（越大越靠前）。 */
function impactRank(impact: string): number {
  if (impact === '改变定价') return 3
  if (impact === '显著影响') return 2
  if (impact === '结构性关注') return 1
  return 0
}

/** 取未来 N 天内的高/中重要度事件（按日期升序）。 */
function upcoming(
  events: { date: string; name: string; importance: string }[],
  days: number,
): { date: string; name: string; importance: string }[] {
  const today = new Date()
  const until = new Date(today.getTime() + days * 24 * 3600 * 1000)
  return events
    .filter((e) => {
      const d = new Date(e.date)
      if (Number.isNaN(d.getTime())) return false
      return d >= new Date(today.toDateString()) && d <= until && e.importance !== '低'
    })
    .sort((a, b) => a.date.localeCompare(b.date))
    .slice(0, 5)
}
