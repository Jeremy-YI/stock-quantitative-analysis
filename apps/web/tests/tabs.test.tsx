import { describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

import Tabs from '@/components/ui/tabs'

const items = [
  { value: 'macd', label: 'MACD' },
  { value: 'kdj', label: 'KDJ' },
  { value: 'rsi', label: 'RSI' },
  { value: 'volume', label: '量能' },
]

describe('Tabs', () => {
  it('should render all tab items', () => {
    render(<Tabs value='macd' onValueChange={() => {}} items={items} />)
    expect(screen.getByRole('tab', { name: 'MACD' })).toBeTruthy()
    expect(screen.getByRole('tab', { name: 'KDJ' })).toBeTruthy()
    expect(screen.getByRole('tab', { name: 'RSI' })).toBeTruthy()
    expect(screen.getByRole('tab', { name: '量能' })).toBeTruthy()
  })

  it('should mark the active tab as selected', () => {
    render(<Tabs value='kdj' onValueChange={() => {}} items={items} />)
    expect(screen.getByRole('tab', { name: 'KDJ' }).getAttribute('aria-selected')).toBe('true')
    expect(screen.getByRole('tab', { name: 'MACD' }).getAttribute('aria-selected')).toBe('false')
  })

  it('should call onValueChange when a tab is clicked', async () => {
    const onValueChange = vi.fn()
    render(<Tabs value='macd' onValueChange={onValueChange} items={items} />)
    await userEvent.click(screen.getByRole('tab', { name: 'KDJ' }))
    expect(onValueChange).toHaveBeenCalledWith('kdj')
  })
})
