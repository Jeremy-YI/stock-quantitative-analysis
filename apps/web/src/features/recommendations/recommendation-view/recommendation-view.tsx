'use client'

/**
 * 个股推荐页：
 *  - 选板块 + 选策略 + 选日期（FilterBar：手机两列、桌面一行）
 *  - 表格给「代码 + 名称」，点名称进个股详情（K 线 + 买点 + 指标）
 *  - 后端默认剔除 ST / 退市整理期（风险警示股不推荐给客户），页脚如实说明剔除了几只
 */
import { useEffect, useState } from 'react'
import Link from 'next/link'

import {
  Badge,
  Caption,
  Stack,
  Card,
  Field,
  FilterBar,
  Page,
  PageHeader,
  Row,
  Select,
  StateHint,
  TBody,
  TD,
  TH,
  THead,
  TR,
  Table,
  TableScroll,
  Text,
  TextInput,
} from '@/design'
import { ratingMeta } from '@/features/stocks/rating'
import { STRATEGIES, strategyLabel } from '@/features/stocks/strategy-label'

import { useRecommendations, useSectorList } from '../use-recommendations'

const DEFAULT_DATE = '2026-08-28'

export default function RecommendationView() {
  const sectors = useSectorList()
  const [sector, setSector] = useState('半导体')
  const [strategy, setStrategy] = useState('all')
  const [date, setDate] = useState(DEFAULT_DATE)

  // 支持从「板块资金」页带 ?sector=xxx 跳转进来，自动选中该板块
  useEffect(() => {
    const params = new URLSearchParams(window.location.search)
    const s = params.get('sector')
    if (s) setSector(s)
  }, [])

  const { data, loading, error } = useRecommendations(sector, date)

  // 后端已按股票聚合并带上名称；这里只按所选策略过滤
  const stocks = (data?.stocks ?? [])
    .map((item) => ({
      ...item,
      signals: item.signals.filter((s) => strategy === 'all' || s.strategy === strategy),
    }))
    .filter((item) => item.signals.length > 0)
  const signalCount = stocks.reduce((sum, s) => sum + s.signals.length, 0)

  return (
    <Page size='lg'>
      <PageHeader
        title='个股推荐'
        description='三道闸：剔除 ST → 只用回测过关的战法 → 风控排除放量长上影/放量阴线/追高'
      />

      <FilterBar>
        <Field label='板块' htmlFor='rec-sector'>
          <Select id='rec-sector' value={sector} onChange={(e) => setSector(e.target.value)}>
            {sectors.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </Select>
        </Field>
        <Field label='策略' htmlFor='rec-strategy'>
          <Select id='rec-strategy' value={strategy} onChange={(e) => setStrategy(e.target.value)}>
            <option value='all'>全部（仅回测过关）</option>
            {STRATEGIES.filter((s) => (data?.strategies_used ?? []).includes(s.name)).map((s) => (
              <option key={s.name} value={s.name}>
                {s.label}
              </option>
            ))}
          </Select>
        </Field>
        <Field label='扫描日' htmlFor='rec-date'>
          <TextInput
            id='rec-date'
            type='date'
            value={date}
            onChange={(e) => setDate(e.target.value)}
          />
        </Field>
      </FilterBar>

      {loading && <StateHint>扫描中…</StateHint>}
      {error && <StateHint kind='error'>加载失败：{error}</StateHint>}

      {data && !loading && (
        <>
          <Text size='body-sm' tone='muted'>
            {data.sector} · {strategy === 'all' ? '全部策略' : strategyLabel(strategy)} ·{' '}
            {data.date} · {signalCount} 条信号 / {stocks.length} 只股票
          </Text>

          {stocks.length === 0 ? (
            <StateHint kind='empty'>该板块当日没有触发信号</StateHint>
          ) : (
            <Card className='overflow-hidden p-0 shadow-none'>
              <TableScroll bare>
                <Table minWidth='sm'>
                  <THead sticky>
                    <TR>
                      <TH>代码</TH>
                      <TH>名称</TH>
                      <TH>触发的信号</TH>
                      <TH hideBelow='mobileLandscape'>回测评级</TH>
                      <TH align='right'>最高分</TH>
                    </TR>
                  </THead>
                  <TBody>
                    {stocks.map((item) => (
                      <TR key={item.symbol} hoverable>
                        <TD mono nowrap className='text-muted-foreground'>
                          {item.symbol}
                        </TD>
                        <TD nowrap>
                          <Link
                            href={`/stocks/${item.symbol}?date=${data.date}`}
                            className='font-medium text-accent hover:underline'
                            title='点开看 K 线与买入信号'
                          >
                            {item.name || item.symbol}
                          </Link>
                        </TD>
                        <TD>
                          <Row gap='tight'>
                            {item.signals.map((s, i) => (
                              <Badge key={i} tone='accent' size='sm'>
                                {strategyLabel(s.strategy)}:{s.signal_type}
                              </Badge>
                            ))}
                          </Row>
                        </TD>
                        <TD hideBelow='mobileLandscape'>
                          <Row gap='tight'>
                            {item.ratings.map((r) => {
                              const meta = ratingMeta(r)
                              return (
                                <Badge key={r} tone={meta.tone} size='sm' title={meta.hint}>
                                  {meta.label}
                                </Badge>
                              )
                            })}
                          </Row>
                        </TD>
                        <TD align='right' mono>
                          {Math.max(...item.signals.map((s) => s.score)).toFixed(0)}
                        </TD>
                      </TR>
                    ))}
                  </TBody>
                </Table>
              </TableScroll>
            </Card>
          )}

          <Stack gap='sm'>
            <Caption>
              {data.names_available
                ? `闸门一：剔除风险警示股票（ST/*ST/退市整理期）${data.excluded_st} 只。`
                : '闸门一未生效：名称快照缺失（先跑 scripts/fetch_stock_names.py）。'}
            </Caption>
            <Caption>
              闸门二：只用回测过关的战法 —— 本次用了{' '}
              {data.strategies_used.map((s) => strategyLabel(s)).join('、') || '（无）'}
              {data.strategies_blocked.length > 0 &&
                `；被挡掉 ${data.strategies_blocked.map((s) => strategyLabel(s)).join('、')}（四段样本外回测不过关，仅 root 可见）`}
              。
            </Caption>
            {data.excluded_risk.length > 0 && (
              <Caption>
                闸门三：风控剔除 {data.excluded_risk.length} 只 ——{' '}
                {data.excluded_risk
                  .slice(0, 6)
                  .map((e) => `${e.name || e.symbol}（${e.reasons.join('、')}）`)
                  .join('；')}
                {data.excluded_risk.length > 6 && ' 等'}
              </Caption>
            )}
            <Caption>点名称进个股详情看 K 线与买点。</Caption>
          </Stack>
        </>
      )}
    </Page>
  )
}
