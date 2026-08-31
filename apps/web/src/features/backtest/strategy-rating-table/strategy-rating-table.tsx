'use client'

/**
 * 策略回测评级表（root 内部组件）。
 *
 * 产品规则（Jeremy 2026-08-31）：
 *   「战法不能只用 Obsidian 里的笔记，只有回测好的才能推荐」
 *   「回测必须赚钱，不能大跌」
 *
 * 所以这里把判定摊开给内部看：四段区间（样本内 + 三段样本外）的 20 日超额胜率、
 * 样本量、选择性，以及机械判定出的评级与是否允许进客户推荐。
 * 判定逻辑在 scripts/build_strategy_ratings.py，不在前端做二次解释。
 */
import {
  Badge,
  Caption,
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  Skeleton,
  StateHint,
  TBody,
  TD,
  TH,
  THead,
  TR,
  Table,
  TableScroll,
} from '@/design'
import { ratingMeta } from '@/features/stocks/rating'
import useStrategyRatings from '@/features/stocks/use-strategy-ratings'

const WINDOWS = ['IS', 'OOS-A', 'OOS-B', 'OOS-C']

export default function StrategyRatingTable() {
  const { data, loading } = useStrategyRatings()

  const rows = Object.entries(data?.strategies ?? {}).sort(
    (a, b) => Number(b[1].client_safe) - Number(a[1].client_safe),
  )

  return (
    <Card className='w-full shadow-none'>
      <CardHeader>
        <CardTitle>策略回测评级 · 客户可见门槛</CardTitle>
        <Caption>
          {data?.as_of ? `编译于 ${data.as_of} · ${data.source}` : '来源：四段样本外回测'}
        </Caption>
      </CardHeader>
      <CardContent className='p-0 mobile-portrait:p-0'>
        {loading && <Skeleton className='m-4 h-40' />}
        {!loading && rows.length === 0 && (
          <StateHint kind='empty'>
            暂无评级（先跑 scripts/build_strategy_ratings.py，它读 data/oos_strategies.json）
          </StateHint>
        )}
        {rows.length > 0 && (
          <TableScroll bare>
            <Table minWidth='lg'>
              <THead sticky>
                <TR>
                  <TH>战法</TH>
                  <TH>评级</TH>
                  <TH align='center'>客户可见</TH>
                  {WINDOWS.map((w) => (
                    <TH key={w} align='right'>
                      {w} 超额
                    </TH>
                  ))}
                  <TH hideBelow='desktop'>判定依据</TH>
                </TR>
              </THead>
              <TBody>
                {rows.map(([name, info]) => {
                  const meta = ratingMeta(info.rating)
                  return (
                    <TR key={name} hoverable>
                      <TD nowrap>
                        <span className='font-medium'>{info.label}</span>
                        <span className='ml-2 font-mono text-caption text-muted-foreground'>
                          {name}
                        </span>
                      </TD>
                      <TD nowrap>
                        <Badge tone={meta.tone} size='sm' title={meta.hint}>
                          {meta.label}
                        </Badge>
                      </TD>
                      <TD align='center' nowrap>
                        {info.client_safe ? (
                          <Badge tone='up' size='sm'>
                            可推荐
                          </Badge>
                        ) : (
                          <Badge tone='muted' size='sm'>
                            仅 root
                          </Badge>
                        )}
                      </TD>
                      {WINDOWS.map((w) => {
                        const cell = info.windows?.[w]
                        return (
                          <TD key={w} align='right' mono>
                            {cell ? (
                              <span
                                className={
                                  cell.excess_win_rate > 0
                                    ? 'text-up'
                                    : cell.excess_win_rate < 0
                                      ? 'text-down'
                                      : 'text-neutral'
                                }
                                title={`样本量 n=${cell.n}`}
                              >
                                {cell.excess_win_rate > 0 ? '+' : ''}
                                {(cell.excess_win_rate * 100).toFixed(1)}pp
                              </span>
                            ) : (
                              '—'
                            )}
                          </TD>
                        )
                      })}
                      <TD hideBelow='desktop'>
                        <Caption>{info.reason}</Caption>
                      </TD>
                    </TR>
                  )
                })}
              </TBody>
            </Table>
          </TableScroll>
        )}
      </CardContent>
    </Card>
  )
}
