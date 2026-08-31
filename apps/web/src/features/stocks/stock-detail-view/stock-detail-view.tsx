'use client'

/**
 * 个股详情页：K 线（含买点标记）+ 当日买入信号 + 指标切换。
 *
 * 入口是「个股推荐」里点股票名字，所以这里要一眼回答三个问题：
 *   1. 它是什么（代码 + 名称 + 最新价 / 涨跌）
 *   2. 为什么被推荐（触发了哪些战法，各自的关键指标）
 *   3. 图形对不对（K 线 + 成交量 + 买点位置，再切 MACD/KDJ/RSI/定价线细看）
 */
import dynamic from 'next/dynamic'
import Link from 'next/link'
import { useState } from 'react'

import {
  Badge,
  Button,
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
  TBody,
  TD,
  TH,
  THead,
  TR,
  Table,
  TableScroll,
  Tabs,
  Text,
  useChartHeight,
} from '@/design'
import KdjPanel from '@/features/kdj/kdj-panel'
import MacdPanel from '@/features/macd/macd-panel'
import PricingLinesPanel from '@/features/pricing-lines/pricing-lines-panel'
import RsiPanel from '@/features/rsi/rsi-panel'
import VolumePanel from '@/features/volume/volume-panel'

import { HISTORY_BARS } from '../range'
import { strategyLabel } from '../strategy-label'
import useCandles from '../use-candles'
import useStockSignals from '../use-stock-signals'
import type { Signal } from '../types'

const CandleChart = dynamic(() => import('../candle-chart'), { ssr: false })

const INDICATORS = [
  { value: 'macd', label: 'MACD' },
  { value: 'kdj', label: 'KDJ' },
  { value: 'rsi', label: 'RSI' },
  { value: 'volume', label: '量能' },
  { value: 'pricing', label: '定价线' },
]

export interface StockDetailViewProps {
  symbol: string
  /** 信号扫描日（默认取推荐页的扫描日） */
  date?: string
}

const DEFAULT_DATE = '2026-08-28'

/** 场内基金代码前缀（与后端 StockMetaService.is_fund 同口径） */
const FUND_PREFIXES = ['50', '51', '52', '56', '58', '15', '16', '18']

function isFund(symbol: string): boolean {
  return FUND_PREFIXES.some((p) => symbol.startsWith(p))
}

export default function StockDetailView({ symbol, date = DEFAULT_DATE }: StockDetailViewProps) {
  // 默认加载近 2 年（够往外缩），初始视窗由图表落在最近约 2 个月
  const [fullHistory, setFullHistory] = useState(false)
  const limit = fullHistory ? undefined : HISTORY_BARS
  const { data: candles, loading: candlesLoading, error: candlesError } = useCandles(symbol, limit)
  const { data: signalData, loading: signalsLoading } = useStockSignals(symbol, date)
  const [indicator, setIndicator] = useState('macd')
  const chartHeight = useChartHeight()
  const fund = isFund(symbol)

  const series = candles?.series ?? []
  const last = series[series.length - 1]
  const prev = series[series.length - 2]
  const changePct = last && prev ? ((last.close - prev.close) / prev.close) * 100 : null
  const signals = signalData?.signals ?? []

  return (
    <Page size='lg'>
      <PageHeader
        title={
          <span className='flex flex-wrap items-baseline gap-2'>
            <span>{candles?.name || symbol}</span>
            <span className='font-mono text-h4 text-muted-foreground'>{symbol}</span>
            {fund && (
              <Badge tone='muted' size='sm'>
                场内基金
              </Badge>
            )}
          </span>
        }
        description={`信号扫描日 ${date}`}
        actions={
          <Link
            href={fund ? '/sectors' : '/recommendations'}
            className='text-body-sm text-accent hover:underline'
          >
            {fund ? '返回板块资金' : '返回个股推荐'}
          </Link>
        }
      />

      {/* 关键数字 */}
      <Grid cols={{ base: 2, mobileLandscape: 4 }} gap='sm'>
        <Stat label='最新收盘' value={last ? last.close.toFixed(2) : '—'} />
        <Stat
          label='涨跌幅'
          value={changePct === null ? '—' : ''}
          num={changePct === null ? undefined : changePct}
        />
        <Stat label='成交额(亿)' value={last ? (last.amount / 1e8).toFixed(2) : '—'} />
        <Stat label='触发信号' value={String(signals.length)} />
      </Grid>

      {/* K 线 */}
      <Section
        title='日K 与买点'
        description={
          fullHistory
            ? '买点标记 B = 当日触发的战法信号；已加载全部历史，图上滚轮/滑块自由缩放'
            : '买点标记 B = 当日触发的战法信号；初始看最近约 2 个月，往外缩可看到近 2 年'
        }
        actions={
          <Button
            variant='outline'
            size='sm'
            onClick={() => setFullHistory((v) => !v)}
            title='默认只加载近 2 年，需要更早的历史再点这里'
          >
            {fullHistory ? '只看近 2 年' : '加载全部历史'}
          </Button>
        }
      >
        {candlesLoading && <Skeleton className='h-64 w-full' />}
        {candlesError && <StateHint kind='error'>K 线加载失败：{candlesError}</StateHint>}
        {!candlesLoading && !candlesError && series.length > 0 && (
          <Card className='p-2 shadow-none'>
            <CandleChart series={series} signals={signals} height={chartHeight} />
          </Card>
        )}
      </Section>

      {/* 买入信号 */}
      <Section title='买入信号' description={`扫描日 ${date} 触发的战法`}>
        {signalsLoading && <Skeleton className='h-24 w-full' />}
        {!signalsLoading && signals.length === 0 && (
          <StateHint kind='empty'>该日没有触发任何战法信号</StateHint>
        )}
        {!signalsLoading && signals.length > 0 && (
          <Card className='overflow-hidden p-0 shadow-none'>
            <TableScroll bare>
              <Table minWidth='sm'>
                <THead>
                  <TR>
                    <TH>战法</TH>
                    <TH>信号</TH>
                    <TH align='right'>分数</TH>
                    <TH hideBelow='mobileLandscape'>关键指标</TH>
                  </TR>
                </THead>
                <TBody>
                  {signals.map((s, i) => (
                    <SignalRow key={i} signal={s} />
                  ))}
                </TBody>
              </Table>
            </TableScroll>
          </Card>
        )}
      </Section>

      {/* 指标细看 */}
      <Section
        title='指标'
        description='与上方 K 线同数据窗口；指标按全量历史计算，图上可自由缩放'
        actions={<Tabs value={indicator} onValueChange={setIndicator} items={INDICATORS} />}
      >
        {indicator === 'macd' && <MacdPanel symbol={symbol} limit={limit} />}
        {indicator === 'kdj' && <KdjPanel symbol={symbol} limit={limit} />}
        {indicator === 'rsi' && <RsiPanel symbol={symbol} limit={limit} />}
        {indicator === 'volume' && <VolumePanel symbol={symbol} limit={limit} />}
        {indicator === 'pricing' && <PricingLinesPanel symbol={symbol} limit={limit} />}
      </Section>
    </Page>
  )
}

function Stat({ label, value, num }: { label: string; value: string; num?: number }) {
  return (
    <div className='rounded-lg border border-border bg-card p-3'>
      <Caption>{label}</Caption>
      <div className='mt-0.5 text-h3 font-semibold tabular-nums'>
        {num === undefined ? value : <Num value={num} suffix='%' />}
      </div>
    </div>
  )
}

function SignalRow({ signal }: { signal: Signal }) {
  // metrics 里挑最有信息量的几个展示，避免一屏塞满
  const entries = Object.entries(signal.metrics).slice(0, 4)
  return (
    <TR hoverable>
      <TD nowrap>
        <Badge tone='accent' size='sm'>
          {strategyLabel(signal.strategy)}
        </Badge>
      </TD>
      <TD nowrap>{signal.signal_type}</TD>
      <TD align='right' mono>
        {signal.score.toFixed(0)}
      </TD>
      <TD hideBelow='mobileLandscape'>
        <Row gap='tight'>
          {entries.map(([k, v]) => (
            <Text as='span' key={k} size='caption' tone='muted' className='font-mono'>
              {k}={String(v)}
            </Text>
          ))}
        </Row>
      </TD>
    </TR>
  )
}
