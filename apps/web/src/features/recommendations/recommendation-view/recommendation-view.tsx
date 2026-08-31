'use client'

/**
 * 个股推荐页：
 *  - 选板块 + 选策略 + 选日期（FilterBar：手机两列、桌面一行）
 *  - 展示该板块里触发所选策略的股票，按分数降序
 * 表格在小屏横滚，「触发的信号」列在手机上仍保留（这是核心信息），
 * 分数列右对齐等宽。
 */
import { useEffect, useState } from 'react'

import {
  Badge,
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

import { useRecommendations, useSectorList } from '../use-recommendations'
import type { Signal } from '../types'

// 策略名 → 中文标签（与后端策略 LABEL 一致）
const STRATEGIES: { name: string; label: string }[] = [
  { name: 'b1b2b3', label: '超卖反弹' },
  { name: 'pin30', label: '单针' },
  { name: 'stealth_rally', label: '偷涨' },
  { name: 'double_bottom', label: '双底' },
  { name: 'macd_resonance', label: '月周共振' },
  { name: 'macd_volume_washout', label: '缩量洗盘' },
  { name: 'etf_accumulation', label: 'ETF抄底' },
]

const STRATEGY_LABEL: Record<string, string> = Object.fromEntries(
  STRATEGIES.map((s) => [s.name, s.label]),
)

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

  // 先按策略过滤，再按股票分组
  const filtered = data?.signals.filter((s) => strategy === 'all' || s.strategy === strategy) ?? []
  const grouped = new Map<string, Signal[]>()
  filtered.forEach((s) => {
    const arr = grouped.get(s.symbol) ?? []
    arr.push(s)
    grouped.set(s.symbol, arr)
  })
  const stocks = [...grouped.entries()].sort(
    (a, b) => Math.max(...b[1].map((s) => s.score)) - Math.max(...a[1].map((s) => s.score)),
  )

  return (
    <Page size='lg'>
      <PageHeader title='个股推荐' description='板块成分股 × 战法信号，按最高分排序' />

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
            <option value='all'>全部</option>
            {STRATEGIES.map((s) => (
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
            {data.sector} · {strategy === 'all' ? '全部策略' : STRATEGY_LABEL[strategy]} ·{' '}
            {data.date} · {filtered.length} 条信号 / {stocks.length} 只股票
          </Text>

          {stocks.length === 0 ? (
            <StateHint kind='empty'>该板块当日没有触发信号</StateHint>
          ) : (
            <Card className='overflow-hidden p-0'>
              <TableScroll bare>
                <Table minWidth='sm'>
                  <THead>
                    <TR>
                      <TH>股票</TH>
                      <TH>触发的信号</TH>
                      <TH align='right'>最高分</TH>
                    </TR>
                  </THead>
                  <TBody>
                    {stocks.map(([symbol, sigs]) => (
                      <TR key={symbol} hoverable>
                        <TD mono nowrap className='font-medium'>
                          {symbol}
                        </TD>
                        <TD>
                          <Row gap='tight'>
                            {sigs.map((s, i) => (
                              <Badge key={i} tone='accent' size='sm'>
                                {STRATEGY_LABEL[s.strategy] ?? s.strategy}:{s.signal_type}
                              </Badge>
                            ))}
                          </Row>
                        </TD>
                        <TD align='right' mono>
                          {Math.max(...sigs.map((s) => s.score)).toFixed(0)}
                        </TD>
                      </TR>
                    ))}
                  </TBody>
                </Table>
              </TableScroll>
            </Card>
          )}
        </>
      )}
    </Page>
  )
}
