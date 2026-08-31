'use client'

/**
 * AI 解读 demo 页：
 * 输入股票代码 + 日期 → 后端扫信号 → LLM 生成自然语言解读。
 * 表单用 FilterBar：手机两列栅格 + 按钮撑满，桌面一行。
 */
import { useState } from 'react'

import {
  Badge,
  Button,
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  Field,
  FilterBar,
  Heading,
  Page,
  PageHeader,
  Row,
  StateHint,
  Text,
  TextInput,
} from '@/design'

import { useInterpret } from '../use-interpret'

export default function AiView() {
  const [symbol, setSymbol] = useState('600519')
  const [date, setDate] = useState('2026-08-28')
  const { result, loading, error, interpret } = useInterpret()

  return (
    <Page size='md'>
      <PageHeader title='AI 解读' description='把当日触发的战法信号翻成人话（DeepSeek）' />

      <FilterBar>
        <Field label='股票代码' htmlFor='ai-symbol'>
          <TextInput
            id='ai-symbol'
            value={symbol}
            onChange={(e) => setSymbol(e.target.value)}
            placeholder='6 位代码，如 600519'
            maxLength={6}
            inputMode='numeric'
          />
        </Field>
        <Field label='日期' htmlFor='ai-date'>
          <TextInput
            id='ai-date'
            type='date'
            value={date}
            onChange={(e) => setDate(e.target.value)}
          />
        </Field>
        <Field label='&nbsp;' wide className='justify-end'>
          <Button variant='accent' block onClick={() => interpret(symbol, date)} disabled={loading}>
            {loading ? '解读中…' : 'AI 解读'}
          </Button>
        </Field>
      </FilterBar>

      {error && <StateHint kind='error'>解读失败：{error}</StateHint>}

      {result && (
        <Card>
          <CardHeader>
            <CardTitle>解读结果 · {result.symbol}</CardTitle>
          </CardHeader>
          <CardContent className='space-y-4'>
            <Text size='body-lg' className='whitespace-pre-wrap'>
              {result.interpretation}
            </Text>

            <div className='space-y-2'>
              <Heading level={4} tone='muted'>
                触发的信号
              </Heading>
              {result.signals.length === 0 ? (
                <Text size='body-sm' tone='muted'>
                  当日无信号
                </Text>
              ) : (
                <Row gap='tight'>
                  {result.signals.map((s, i) => (
                    <Badge key={i} tone='accent'>
                      {s.strategy}:{s.signal_type}（{s.score.toFixed(0)}）
                    </Badge>
                  ))}
                </Row>
              )}
            </div>
          </CardContent>
        </Card>
      )}
    </Page>
  )
}
