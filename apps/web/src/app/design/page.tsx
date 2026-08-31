'use client'

/**
 * 设计系统展示页（内部文档，/design）。
 *
 * 作用有两个：
 *  1. 改组件时先在这看一眼，别去业务页里试
 *  2. 缩放窗口就能验证响应式：断点角标 + 各组件在不同宽度下的表现
 *
 * 断点命名与 FreshFarmPicking 一致：
 *   mobilePortrait 448 / mobileLandscape 766 / desktop 1200 / largeDevice 1440
 */
import { useState } from 'react'

import {
  Badge,
  Button,
  COLOR_TOKENS,
  Caption,
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  Field,
  FilterBar,
  Grid,
  Heading,
  Num,
  Page,
  PageHeader,
  ResponsiveBreakPoints,
  Row,
  SPACING,
  Section,
  Select,
  Show,
  Stack,
  TBody,
  TD,
  TEXT_SCALE,
  TH,
  THead,
  TR,
  Table,
  TableScroll,
  Tabs,
  Text,
  TextInput,
  useBreakpoint,
  type Tone,
} from '@/design'

const TONES: Tone[] = [
  'default',
  'muted',
  'accent',
  'up',
  'down',
  'neutral',
  'warn',
  'danger',
  'info',
]

// 字号预览类名必须字面量（Tailwind 不扫拼接类）
const SCALE_CLASS: Record<string, string> = {
  display: 'text-display',
  h1: 'text-h1',
  h2: 'text-h2',
  h3: 'text-h3',
  h4: 'text-h4',
  'body-lg': 'text-body-lg',
  body: 'text-body',
  'body-sm': 'text-body-sm',
  caption: 'text-caption',
}

export default function DesignSystemPage() {
  const { bp, label, width, isMobile, isPad, isDesktop } = useBreakpoint()
  const [tab, setTab] = useState('grid')

  return (
    <Page size='lg'>
      <PageHeader
        title='设计系统'
        description='断点 / 排版 / 颜色 / 间距 / 组件。缩放窗口即可验证响应式。'
        actions={<ResponsiveBreakPoints />}
      />

      {/* 断点 */}
      <Section
        title='Breakpoint'
        description='语义命名（与 FreshFarmPicking global-theme 一致）：mobilePortrait 448 / mobileLandscape 766 / desktop 1200 / largeDevice 1440'
      >
        <Grid cols={{ base: 2, mobileLandscape: 4 }} gap='sm'>
          <Stat label='当前档位' value={bp} />
          <Stat label='视口宽度' value={`${width}px`} />
          <Stat
            label='设备类'
            value={isMobile ? '手机' : isPad ? '平板' : isDesktop ? '桌面' : '—'}
          />
          <Stat label='容器上限' value='desktop 1200px' />
        </Grid>
        <Caption>{label}</Caption>
        <Row gap='sm'>
          <Show below='mobileLandscape'>
            <Badge tone='warn'>这块只在 &lt; 766（手机）出现</Badge>
          </Show>
          <Show above='desktop'>
            <Badge tone='info'>这块只在 ≥ 1200（桌面）出现</Badge>
          </Show>
        </Row>
      </Section>

      {/* 排版 */}
      <Section title='Typography' description='字号用 clamp 流式缩放，业务里不写字号阶梯'>
        <Card>
          <CardContent className='space-y-3 pt-4 mobile-portrait:pt-5'>
            {TEXT_SCALE.map((t) => (
              <div
                key={t.token}
                className='flex flex-col gap-0.5 border-b border-border pb-3 last:border-0 last:pb-0 mobile-portrait:flex-row mobile-portrait:items-baseline mobile-portrait:justify-between mobile-portrait:gap-4'
              >
                <span className={`${SCALE_CLASS[t.token] ?? 'text-body'} min-w-0`}>{t.usage}</span>
                <Caption className='shrink-0 font-mono'>
                  {t.token} · {t.clamp}
                </Caption>
              </div>
            ))}
          </CardContent>
        </Card>
      </Section>

      {/* 颜色 */}
      <Section title='Color' description='业务只用语义名（up/down/accent…），换皮只改 globals.css'>
        <Grid cols={{ base: 2, mobilePortrait: 3, desktop: 5 }} gap='sm'>
          {COLOR_TOKENS.map((c) => (
            <div key={c.token} className='rounded-lg border border-border p-2'>
              <div
                className='h-8 w-full rounded'
                style={{ backgroundColor: `var(--${c.token})` }}
              />
              <Caption className='mt-1.5 block font-mono'>{c.token}</Caption>
              <Caption className='block'>{c.usage}</Caption>
            </div>
          ))}
        </Grid>
        <Row gap='sm'>
          <Num value={2.35} suffix='%' />
          <Num value={-1.08} suffix='%' />
          <Num value={0} suffix='%' />
          <Num value={null} />
        </Row>
      </Section>

      {/* 间距 */}
      <Section title='Spacing' description='刻度与 FFP theme.spacing 一致：index → px'>
        <Row gap='tight'>
          {SPACING.map((px: number, i: number) => (
            <span
              key={i}
              className='inline-flex items-center gap-1 rounded border border-border px-1.5 py-0.5 font-mono text-caption text-muted-foreground'
            >
              {i}
              <span className='text-foreground'>{px}px</span>
            </span>
          ))}
        </Row>
      </Section>

      {/* 按钮 */}
      <Section title='Button' description='手机 40px 高、平板起 36px；block 让按钮在手机撑满'>
        <Row gap='sm'>
          <Button>default</Button>
          <Button variant='accent'>accent</Button>
          <Button variant='secondary'>secondary</Button>
          <Button variant='outline'>outline</Button>
          <Button variant='ghost'>ghost</Button>
          <Button variant='subtle'>subtle</Button>
          <Button variant='danger'>danger</Button>
          <Button variant='link'>link</Button>
          <Button disabled>disabled</Button>
        </Row>
        <Row gap='sm'>
          <Button size='sm'>sm</Button>
          <Button>default</Button>
          <Button size='lg'>lg</Button>
        </Row>
        <Button variant='accent' block>
          block（手机撑满 / 桌面自适应）
        </Button>
      </Section>

      {/* 徽标 */}
      <Section title='Badge'>
        <Row gap='tight'>
          {TONES.map((t) => (
            <Badge key={t} tone={t}>
              {t}
            </Badge>
          ))}
        </Row>
        <Row gap='tight'>
          {TONES.map((t) => (
            <Badge key={t} tone={t} variant='solid'>
              {t}
            </Badge>
          ))}
        </Row>
      </Section>

      {/* 表单 */}
      <Section title='Field / FilterBar' description='手机两列栅格，448 起一行 flex'>
        <FilterBar>
          <Field label='股票代码' htmlFor='d-symbol'>
            <TextInput id='d-symbol' defaultValue='600519' />
          </Field>
          <Field label='板块' htmlFor='d-sector'>
            <Select id='d-sector' defaultValue='半导体'>
              <option value='半导体'>半导体</option>
              <option value='白酒'>白酒</option>
            </Select>
          </Field>
          <Field label='日期' htmlFor='d-date'>
            <TextInput id='d-date' type='date' defaultValue='2026-08-28' />
          </Field>
        </FilterBar>
      </Section>

      {/* 布局 + 表格 */}
      <Section
        title='Grid / Table'
        description='Grid 列数按断点给；表格自己横滚，次要列小屏收起'
        actions={
          <Tabs
            value={tab}
            onValueChange={setTab}
            items={[
              { value: 'grid', label: '栅格' },
              { value: 'table', label: '表格' },
            ]}
          />
        }
      >
        {tab === 'grid' ? (
          <Grid cols={{ base: 1, mobilePortrait: 2, mobileLandscape: 3, desktop: 6 }} gap='md'>
            {Array.from({ length: 6 }, (_, i) => (
              <Card key={i}>
                <CardHeader>
                  <CardTitle>卡片 {i + 1}</CardTitle>
                </CardHeader>
                <CardContent>
                  <Text size='body-sm' tone='muted'>
                    1 列 → 448:2 → 766:3 → 1200:6
                  </Text>
                </CardContent>
              </Card>
            ))}
          </Grid>
        ) : (
          <TableScroll>
            <Table minWidth='md'>
              <THead>
                <TR>
                  <TH>代码</TH>
                  <TH>名称</TH>
                  <TH align='right'>净额(亿)</TH>
                  <TH align='right' hideBelow='mobilePortrait'>
                    涨跌幅
                  </TH>
                  <TH hideBelow='mobileLandscape'>备注（766 起显示）</TH>
                </TR>
              </THead>
              <TBody>
                {[
                  { code: '510300', name: '沪深300ETF', net: 2.45, pct: -0.26 },
                  { code: '512480', name: '半导体ETF', net: -1.32, pct: -2.9 },
                  { code: '512890', name: '红利低波ETF', net: 0.63, pct: 0.08 },
                ].map((r) => (
                  <TR key={r.code} hoverable>
                    <TD mono>{r.code}</TD>
                    <TD>{r.name}</TD>
                    <TD align='right'>
                      <Num value={r.net} />
                    </TD>
                    <TD align='right' hideBelow='mobilePortrait'>
                      <Num value={r.pct} suffix='%' />
                    </TD>
                    <TD hideBelow='mobileLandscape'>
                      <Caption>次要信息，小屏直接收起</Caption>
                    </TD>
                  </TR>
                ))}
              </TBody>
            </Table>
          </TableScroll>
        )}
      </Section>
    </Page>
  )
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className='rounded-lg border border-border bg-card p-3'>
      <Caption>{label}</Caption>
      <Heading level={3} className='mt-0.5'>
        {value}
      </Heading>
    </div>
  )
}
