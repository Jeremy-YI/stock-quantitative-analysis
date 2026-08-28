import { describe, expect, it } from 'vitest'

import { cn } from '@/lib/utils'

describe('cn', () => {
  it('should merge conflicting tailwind classes (later wins)', () => {
    expect(cn('bg-red-500', 'bg-blue-500')).toBe('bg-blue-500')
  })

  it('should drop falsy values', () => {
    expect(cn('p-4', false && 'm-4', null, undefined, '')).toBe('p-4')
  })

  it('should keep unique classes', () => {
    expect(cn('rounded-lg', 'border')).toBe('rounded-lg border')
  })
})
