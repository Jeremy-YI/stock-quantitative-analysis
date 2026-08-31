import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'

import IndicatorPanel from '@/features/indicators/indicator-panel'

describe('IndicatorPanel', () => {
  it('should render skeleton when loading', () => {
    render(
      <IndicatorPanel title='MACD' loading error={null}>
        <div>chart</div>
      </IndicatorPanel>,
    )
    expect(screen.getByText('MACD')).toBeTruthy()
    expect(screen.queryByTestId('indicator-chart')).toBeNull()
    expect(screen.queryByText('chart')).toBeNull()
  })

  it('should render error message when not loading and error present', () => {
    render(
      <IndicatorPanel title='MACD' loading={false} error='标的 600519 不存在'>
        <div>chart</div>
      </IndicatorPanel>,
    )
    expect(screen.getByText('标的 600519 不存在')).toBeTruthy()
    expect(screen.queryByTestId('indicator-chart')).toBeNull()
  })

  it('should render chart container when data ready', () => {
    render(
      <IndicatorPanel title='MACD' loading={false} error={null}>
        <div>chart</div>
      </IndicatorPanel>,
    )
    expect(screen.getByTestId('indicator-chart')).toBeTruthy()
    expect(screen.getByText('chart')).toBeTruthy()
  })

  it('should render legend when provided', () => {
    render(
      <IndicatorPanel title='KDJ' loading={false} error={null} legend={<span>K/D/J</span>}>
        <div>chart</div>
      </IndicatorPanel>,
    )
    expect(screen.getByText('K/D/J')).toBeTruthy()
  })
})
