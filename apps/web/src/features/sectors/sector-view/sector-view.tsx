'use client'

/**
 * 板块资金页：
 *  - 窗口选择（即时 / 3日 / 5日 / 10日 / 20日）→ Tabs（手机横向滚动）
 *  - 主区：Top20 流入 / Top20 流出，手机单列、desktop 起两列
 *  - 底部：ETF 资金流（独立模块，行业看方向、ETF 看能直接买的标的）
 *
 * 两个数据现实（同花顺接口决定的，UI 跟着数据走，不给空占位）：
 *  1. 「对应 ETF」靠名称匹配，命中率不到一半 → 整列去掉，ETF 看下面的模块
 *  2. 多日窗口（3/5/10/20 日）没有领涨股，涨跌幅是阶段涨跌 → 该列按窗口显示/隐藏
 */
import { useState } from 'react'
import Link from 'next/link'

import {
  Badge,
  LoadingState,
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  Grid,
  Num,
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
  Tabs,
  Text,
} from '@/design'

import useSectors from '../use-sectors'
import EtfFlowPanel from '../etf-flow-panel'
import type { SectorFlow } from '../types'

const DAYS = ['即时', '3日排行', '5日排行', '10日排行', '20日排行']

export default function SectorView() {
  const [days, setDays] = useState('即时')
  const { data, loading, error } = useSectors(days)

  const isIntraday = days === '即时'

  return (
    <Page size='lg'>
      <PageHeader
        title='板块资金'
        description='同花顺行业资金流向 · 点行业名跳到该板块的个股信号'
      />

      <Tabs
        value={days}
        onValueChange={setDays}
        items={DAYS.map((d) => ({ value: d, label: d }))}
      />

      {loading && <LoadingState label='加载板块资金流' skeleton rows={4} />}
      {error && <StateHint kind='error'>加载失败：{error}</StateHint>}

      {data && (
        <>
          <Grid cols={{ base: 1, desktop: 2 }} gap='lg'>
            <FlowColumn title='Top20 资金流入' rows={data.top_inflow} isIntraday={isIntraday} />
            <FlowColumn title='Top20 资金流出' rows={data.top_outflow} isIntraday={isIntraday} />
          </Grid>

          {/* ETF 资金流：独立模块 */}
          <EtfFlowPanel />
        </>
      )}
    </Page>
  )
}

/** 一列（流入或流出）的排行表。 */
function FlowColumn({
  title,
  rows,
  isIntraday,
}: {
  title: string
  rows: SectorFlow[]
  isIntraday: boolean
}) {
  // 多日窗口没有领涨股，有数据才给这列
  const hasLeader = rows.some((r) => Boolean(r.leader))

  return (
    <Card className='overflow-hidden shadow-none'>
      <CardHeader className='border-b border-border bg-surface'>
        <CardTitle>{title}</CardTitle>
      </CardHeader>
      <CardContent className='p-0 mobile-portrait:p-0'>
        <TableScroll bare>
          <Table minWidth='sm'>
            <THead>
              <TR>
                <TH>行业</TH>
                <TH align='right'>净额(亿)</TH>
                <TH align='right'>{isIntraday ? '涨跌幅' : '阶段涨跌'}</TH>
                <TH align='right' hideBelow='mobilePortrait'>
                  家数
                </TH>
                {hasLeader && <TH hideBelow='mobileLandscape'>领涨股</TH>}
              </TR>
            </THead>
            <TBody>
              {rows.map((s) => (
                <TR key={s.sector} hoverable>
                  <TD nowrap>
                    <Link
                      href={`/recommendations?sector=${encodeURIComponent(s.sector)}`}
                      className='font-medium text-accent hover:underline'
                      title='点开看成分股 + 信号'
                    >
                      {s.sector}
                    </Link>
                  </TD>
                  <TD align='right'>
                    <Num value={s.net} weight='medium' />
                  </TD>
                  <TD align='right'>
                    <Num value={s.change_pct} suffix='%' />
                  </TD>
                  <TD
                    align='right'
                    hideBelow='mobilePortrait'
                    mono
                    className='text-muted-foreground'
                  >
                    {s.companies}
                  </TD>
                  {hasLeader && (
                    <TD hideBelow='mobileLandscape' nowrap>
                      <span className='inline-flex items-center gap-1.5'>
                        <Text as='span' size='body-sm' tone='muted'>
                          {s.leader || '—'}
                        </Text>
                        {s.leader_pct > 0 && (
                          <Badge tone='up' size='sm'>
                            +{s.leader_pct.toFixed(2)}%
                          </Badge>
                        )}
                      </span>
                    </TD>
                  )}
                </TR>
              ))}
            </TBody>
          </Table>
        </TableScroll>
      </CardContent>
    </Card>
  )
}
