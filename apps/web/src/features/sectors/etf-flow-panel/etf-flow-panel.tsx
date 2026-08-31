'use client'

/**
 * ETF 资金流面板（独立模块，挂在板块资金页下面）。
 *
 * 参考 wangwang-etf 的信息组织，但**每个主题只看资金最集中的那一只**：
 * 同一指数下十几只 ETF 对决策没有增量，只需要盯龙头。
 *
 * 三个视图：
 *   主题龙头  按大类分组（宽基→科技成长→医药消费→金融地产→周期资源→红利防御→跨境）
 *   净流入    当日主力净流入 TOP
 *   净流出    当日主力净流出 TOP
 *
 * 排序：规模 / 最新价 / 涨跌幅 / 净额 / 成交额 五列都能点表头排（大→小→小→大→取消），
 * 走设计系统的 useTableSort + SortableTH。主题龙头视图一旦自定义排序，
 * 会自动去掉大类分组行（跨类比较才有意义）。
 *
 * 口径（脚注也写着，避免误读）：
 *   净额     主力净流入，东财大单口径，只有交易日当天有
 *   净申赎   份额变化 × 最新价，申赎的真金白银，需要隔日对比份额
 */
import Link from 'next/link'
import { useState } from 'react'

import {
  Caption,
  Card,
  Num,
  Section,
  SortableTH,
  StateHint,
  TBody,
  TD,
  TH,
  THead,
  TR,
  Table,
  TableScroll,
  Tabs,
  useTableSort,
} from '@/design'

import useEtfFlow from '../use-etf-flow'
import type { EtfFlow, EtfLeader } from '../types'

type View = 'leaders' | 'inflow' | 'outflow'

/** 可排序的数值列（key 与数据字段同名） */
type SortKey = 'mcap' | 'price' | 'change_pct' | 'net' | 'turnover'

const VIEWS = [
  { value: 'leaders', label: '主题龙头' },
  { value: 'inflow', label: '净流入' },
  { value: 'outflow', label: '净流出' },
]

export default function EtfFlowPanel({ top = 15 }: { top?: number }) {
  const [view, setView] = useState<View>('leaders')
  const { data, loading, error } = useEtfFlow(top)

  const leaders = data?.leaders ?? []
  const ranking = view === 'inflow' ? (data?.top_inflow ?? []) : (data?.top_outflow ?? [])
  const source: (EtfFlow | EtfLeader)[] = view === 'leaders' ? leaders : ranking

  const { rows, sortKey, sortDir, onSort, sorted } = useTableSort<EtfFlow | EtfLeader, SortKey>(
    source,
  )
  const sortState = { sortKey, sortDir }

  // 份额口径要隔日对比，首跑没有历史 → 整列不显示（宁可不给，也不给假数据）
  const showShare = Boolean(data?.has_share_flow) && rows.some((r: EtfFlow) => r.share_net !== null)
  const flowAvailable = data?.flow_available !== false
  // 主题龙头视图未自定义排序时保留大类分组
  const grouped = view === 'leaders' && !sorted

  return (
    <Section
      title='ETF 资金流'
      description={
        data
          ? `${data.date || '—'} · ${data.total} 只参与统计 · 每个主题只取资金最集中的一只`
          : '场内 ETF：主题龙头与当日资金流向'
      }
      actions={<Tabs value={view} onValueChange={(v) => setView(v as View)} items={VIEWS} />}
    >
      {loading && <StateHint>加载中…</StateHint>}
      {error && <StateHint kind='error'>加载失败：{error}</StateHint>}

      {data && rows.length === 0 && (
        <StateHint kind='empty'>
          {view === 'leaders'
            ? '暂无 ETF 快照（先跑 scripts/fetch_etf_flow.py）'
            : '当日无大单资金流数据（非交易日只有存量数据）'}
        </StateHint>
      )}

      {rows.length > 0 && (
        <Card className='overflow-hidden p-0 shadow-none'>
          <TableScroll bare className='max-h-[70vh] overflow-y-auto'>
            <Table minWidth='md'>
              <THead sticky>
                <TR>
                  {view === 'leaders' ? <TH>主题</TH> : <TH align='right'>#</TH>}
                  <TH>ETF</TH>
                  <SortableTH
                    sortKey='mcap'
                    state={sortState}
                    onSort={onSort}
                    align='right'
                    hideBelow='mobilePortrait'
                  >
                    规模(亿)
                  </SortableTH>
                  <SortableTH sortKey='price' state={sortState} onSort={onSort} align='right'>
                    最新价
                  </SortableTH>
                  <SortableTH sortKey='change_pct' state={sortState} onSort={onSort} align='right'>
                    涨跌幅
                  </SortableTH>
                  <SortableTH sortKey='net' state={sortState} onSort={onSort} align='right'>
                    净额(亿)
                  </SortableTH>
                  {showShare && (
                    <TH align='right' hideBelow='mobileLandscape'>
                      净申赎(亿)
                    </TH>
                  )}
                  <SortableTH
                    sortKey='turnover'
                    state={sortState}
                    onSort={onSort}
                    align='right'
                    hideBelow='mobileLandscape'
                  >
                    成交额(亿)
                  </SortableTH>
                  <TH align='right' hideBelow='desktop'>
                    换手
                  </TH>
                </TR>
              </THead>
              <TBody>
                {grouped
                  ? renderLeaderRows(rows as EtfLeader[], showShare, data?.date)
                  : rows.map((e: EtfFlow, i: number) => (
                      <EtfRow
                        key={e.code}
                        etf={e}
                        theme={view === 'leaders' ? (e as EtfLeader).theme : undefined}
                        peers={view === 'leaders' ? (e as EtfLeader).peers : undefined}
                        index={view === 'leaders' ? undefined : i + 1}
                        showShare={showShare}
                        date={data?.date}
                      />
                    ))}
              </TBody>
            </Table>
          </TableScroll>
        </Card>
      )}

      {data && rows.length > 0 && (
        <Caption>
          口径：净额 = 主力（大单）净流入，反映当日盘口强弱
          {flowAvailable ? '' : '（当前快照为非交易日，大单数据不可回溯，故留空）'}；
          {showShare
            ? '净申赎 = 份额变化 × 最新价，是申购赎回的真实资金。'
            : '净申赎 = 份额变化 × 最新价，需隔日对比份额，下个交易日起显示。'}
          规模取流通市值，主题龙头按规模选出。点 ETF 名称看 K 线与信号，点表头可排序
          {sorted ? '（已按自定义排序，大类分组已收起）' : ''}。
        </Caption>
      )}
    </Section>
  )
}

/** 主题龙头：按大类插入分组小标题行（正式报表的做法，不用彩色标签堆）。 */
function renderLeaderRows(leaders: EtfLeader[], showShare: boolean, date?: string) {
  const out: React.ReactNode[] = []
  let current = ''

  leaders.forEach((item) => {
    if (item.category !== current) {
      current = item.category
      out.push(
        <TR key={`group-${current}`}>
          <TD
            colSpan={showShare ? 9 : 8}
            className='sticky top-8 z-[5] border-y border-border bg-muted py-1.5 text-caption font-semibold tracking-wide text-foreground/70'
          >
            {current}
          </TD>
        </TR>,
      )
    }
    out.push(
      <EtfRow
        key={item.code}
        etf={item}
        theme={item.theme}
        peers={item.peers}
        showShare={showShare}
        date={date}
      />,
    )
  })

  return out
}

/** 涨跌幅：轻底色色块（金融终端惯用做法，扫表时一眼就能定位强弱）。 */
function ChangeCell({ value }: { value: number }) {
  const tone =
    value > 0
      ? 'bg-up-soft text-up'
      : value < 0
        ? 'bg-down-soft text-down'
        : 'bg-surface text-neutral'
  return (
    <span
      className={`inline-block min-w-[4.25rem] rounded px-1.5 py-0.5 text-right font-mono tabular-nums ${tone}`}
    >
      {value > 0 ? '+' : ''}
      {value.toFixed(2)}%
    </span>
  )
}

function EtfRow({
  etf,
  theme,
  peers,
  index,
  showShare,
  date,
}: {
  etf: EtfFlow
  theme?: string
  peers?: number
  index?: number
  showShare: boolean
  /** 快照日：带进详情页当信号扫描日 */
  date?: string
}) {
  return (
    <TR hoverable>
      {theme !== undefined ? (
        <TD nowrap>
          <span className='font-medium'>{theme}</span>
          {peers && peers > 1 ? (
            <span className='ml-1 font-mono text-caption text-muted-foreground'>/{peers}</span>
          ) : null}
        </TD>
      ) : (
        <TD align='right' mono className='text-muted-foreground'>
          {index}
        </TD>
      )}
      <TD nowrap className='py-2.5'>
        <span className='flex flex-col leading-tight mobile-portrait:flex-row mobile-portrait:items-baseline mobile-portrait:gap-2'>
          <span className='font-mono text-caption text-muted-foreground'>{etf.code}</span>
          <Link
            href={`/stocks/${etf.code}${date ? `?date=${date}` : ''}`}
            className='truncate font-medium text-accent hover:underline'
            title='点开看 K 线与信号'
          >
            {etf.name}
          </Link>
        </span>
      </TD>
      <TD align='right' hideBelow='mobilePortrait' mono>
        {etf.mcap.toFixed(1)}
      </TD>
      <TD align='right' mono>
        {etf.price ? etf.price.toFixed(3) : '—'}
      </TD>
      <TD align='right'>
        <ChangeCell value={etf.change_pct} />
      </TD>
      <TD align='right'>
        <Num value={etf.net} />
      </TD>
      {showShare && (
        <TD align='right' hideBelow='mobileLandscape'>
          <Num value={etf.share_net} />
        </TD>
      )}
      <TD align='right' hideBelow='mobileLandscape' mono>
        {etf.turnover ? etf.turnover.toFixed(2) : '—'}
      </TD>
      <TD align='right' hideBelow='desktop' mono className='text-muted-foreground'>
        {etf.turnover_rate ? `${etf.turnover_rate.toFixed(1)}%` : '—'}
      </TD>
    </TR>
  )
}
