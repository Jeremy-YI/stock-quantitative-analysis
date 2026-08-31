import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import fs from 'node:fs'
import path from 'node:path'

import {
  Badge,
  Button,
  Container,
  Grid,
  Heading,
  Num,
  Show,
  Stack,
  TD,
  TH,
  Table,
  TableScroll,
  Text,
  gridColsClass,
} from '@/design'
import {
  BREAKPOINTS,
  BREAKPOINT_PREFIX,
  SPACING,
  isBreakpointAtLeast,
  mediaAbove,
  mediaBelow,
  normalizeResponsive,
  resolveBreakpoint,
  spacing,
} from '@/design/tokens'
import { pickResponsive } from '@/design/breakpoint'
import { cellVisibleFrom } from '@/design/visibility'
import { changeTextClass, toneForChange, toneForStatus } from '@/design/color'

describe('design tokens · breakpoint', () => {
  it('CSS 与 TS 两侧断点必须一致（globals.css 的 --breakpoint-* 是 rem，16px 基准）', () => {
    const css = fs.readFileSync(path.resolve(__dirname, '../src/styles/globals.css'), 'utf8')
    for (const [name, px] of Object.entries(BREAKPOINTS)) {
      const prefix = BREAKPOINT_PREFIX[name as keyof typeof BREAKPOINTS]
      const m = css.match(new RegExp(`--breakpoint-${prefix}:\\s*([0-9.]+)rem`))
      expect(m, `globals.css 缺少 --breakpoint-${prefix}`).not.toBeNull()
      expect(Number(m![1]) * 16).toBe(px)
    }
  })

  it('断点值与 FreshFarmPicking global-theme 对齐', () => {
    expect(BREAKPOINTS).toEqual({
      mobilePortrait: 448,
      mobileLandscape: 766,
      desktop: 1200,
      largeDevice: 1440,
    })
  })

  it('间距刻度与 FFP theme.spacing 一致', () => {
    expect(SPACING).toEqual([0, 4, 8, 12, 16, 20, 24, 28, 32, 40, 48, 56, 64])
    expect(spacing(4)).toBe(16)
    expect(spacing(9)).toBe(40)
  })

  it('Tailwind 默认断点已清空，避免两套混用', () => {
    const css = fs.readFileSync(path.resolve(__dirname, '../src/styles/globals.css'), 'utf8')
    for (const legacy of ['sm', 'md', 'lg', 'xl', '2xl']) {
      expect(css).toContain(`--breakpoint-${legacy}: initial`)
    }
  })

  it('resolveBreakpoint 按宽度落到正确档位', () => {
    expect(resolveBreakpoint(375)).toBe('base')
    expect(resolveBreakpoint(448)).toBe('mobilePortrait')
    expect(resolveBreakpoint(700)).toBe('mobilePortrait')
    expect(resolveBreakpoint(768)).toBe('mobileLandscape')
    expect(resolveBreakpoint(1200)).toBe('desktop')
    expect(resolveBreakpoint(1600)).toBe('largeDevice')
  })

  it('媒体查询字符串：above/below 不重叠', () => {
    expect(mediaAbove('mobileLandscape')).toBe('(min-width: 766px)')
    expect(mediaBelow('mobileLandscape')).toBe('(max-width: 765.9px)')
  })

  it('isBreakpointAtLeast 比较大小（base 最小）', () => {
    expect(isBreakpointAtLeast('desktop', 'mobileLandscape')).toBe(true)
    expect(isBreakpointAtLeast('mobilePortrait', 'desktop')).toBe(false)
    expect(isBreakpointAtLeast('base', 'mobilePortrait')).toBe(false)
  })

  it('normalizeResponsive 把单值当 base', () => {
    expect(normalizeResponsive(2)).toEqual({ base: 2 })
    expect(normalizeResponsive({ base: 1, desktop: 3 })).toEqual({ base: 1, desktop: 3 })
  })

  it('pickResponsive 逐级向下兜底', () => {
    const map = { base: 240, mobileLandscape: 360, largeDevice: 480 }
    expect(pickResponsive(map, 'base')).toBe(240)
    expect(pickResponsive(map, 'mobilePortrait')).toBe(240)
    expect(pickResponsive(map, 'mobileLandscape')).toBe(360)
    expect(pickResponsive(map, 'desktop')).toBe(360)
    expect(pickResponsive(map, 'largeDevice')).toBe(480)
  })
})

describe('Grid', () => {
  it('cols 断点映射翻成完整类名（Tailwind 能扫到的字面量）', () => {
    expect(gridColsClass({ base: 1, mobileLandscape: 2, desktop: 4 })).toBe(
      'grid-cols-1 mobile-landscape:grid-cols-2 desktop:grid-cols-4',
    )
    expect(gridColsClass(3)).toBe('grid-cols-3')
  })

  it('渲染时带上 grid 与响应式列数、响应式间距', () => {
    const { container } = render(<Grid cols={{ base: 1, desktop: 2 }} gap='lg' />)
    const el = container.firstElementChild!
    expect(el.className).toContain('grid')
    expect(el.className).toContain('grid-cols-1')
    expect(el.className).toContain('desktop:grid-cols-2')
    // 间距本身也是响应式的：手机紧、桌面松
    expect(el.className).toContain('gap-4')
    expect(el.className).toContain('mobile-portrait:gap-6')
  })
})

describe('Container', () => {
  it('宽度是 100% + 最大宽度上限，不是固定宽度', () => {
    const { container } = render(<Container size='lg' />)
    const el = container.firstElementChild!
    expect(el.className).toContain('w-full')
    expect(el.className).toContain('max-w-[75rem]')
    expect(el.className).toContain('mx-auto')
    // 留白随断点变化
    expect(el.className).toContain('px-4')
    expect(el.className).toContain('mobile-portrait:px-6')
    expect(el.className).toContain('desktop:px-8')
  })

  it('size=full 不限宽', () => {
    const { container } = render(<Container size='full' />)
    expect(container.firstElementChild!.className).toContain('max-w-none')
  })
})

describe('Stack', () => {
  it('col-to-row：手机竖排、平板起横排', () => {
    const { container } = render(<Stack direction='col-to-row' />)
    const cls = container.firstElementChild!.className
    expect(cls).toContain('flex-col')
    expect(cls).toContain('mobile-landscape:flex-row')
  })
})

describe('Typography', () => {
  it('Heading level 决定标签与字号', () => {
    render(<Heading level={1}>标题</Heading>)
    const h1 = screen.getByRole('heading', { level: 1 })
    expect(h1.className).toContain('text-h1')
  })

  it('Text 支持 tone/size/mono', () => {
    const { container } = render(
      <Text size='caption' tone='muted' mono>
        文字
      </Text>,
    )
    const cls = container.firstElementChild!.className
    expect(cls).toContain('text-caption')
    expect(cls).toContain('text-muted-foreground')
    expect(cls).toContain('font-mono')
  })

  it('Num 正红负绿、带符号、空值占位', () => {
    const { rerender, container } = render(<Num value={1.234} suffix='%' />)
    expect(container.textContent).toBe('+1.23%')
    expect(container.firstElementChild!.className).toContain('text-up')

    rerender(<Num value={-1.2} suffix='%' />)
    expect(container.textContent).toBe('-1.20%')
    expect(container.firstElementChild!.className).toContain('text-down')

    rerender(<Num value={null} />)
    expect(container.textContent).toBe('—')
  })
})

describe('Button', () => {
  it('变体/尺寸/block 都落到类名上', () => {
    const { container } = render(
      <Button variant='accent' size='lg' block>
        扫描
      </Button>,
    )
    const cls = container.firstElementChild!.className
    expect(cls).toContain('bg-accent')
    expect(cls).toContain('h-11')
    expect(cls).toContain('w-full')
    expect(cls).toContain('mobile-landscape:w-auto')
  })

  it('默认 type=button（避免误提交表单）', () => {
    render(<Button>点我</Button>)
    expect(screen.getByRole('button')).toHaveAttribute('type', 'button')
  })
})

describe('Badge / color tone', () => {
  it('tone 映射语义色', () => {
    const { container } = render(<Badge tone='up'>涨</Badge>)
    expect(container.firstElementChild!.className).toContain('text-up')
  })

  it('涨跌 → tone（A股红涨绿跌）', () => {
    expect(toneForChange(1)).toBe('up')
    expect(toneForChange(-1)).toBe('down')
    expect(toneForChange(0)).toBe('neutral')
    expect(toneForChange(null)).toBe('neutral')
    expect(changeTextClass(2)).toBe('text-up')
  })

  it('任务状态 → tone', () => {
    expect(toneForStatus('success')).toBe('up')
    expect(toneForStatus('failed')).toBe('down')
    expect(toneForStatus('running')).toBe('accent')
    expect(toneForStatus(null)).toBe('neutral')
  })
})

describe('Show / 单元格可见性', () => {
  it('above：小屏隐藏、达到断点显示', () => {
    const { container } = render(<Show above='desktop'>桌面</Show>)
    const cls = container.firstElementChild!.className
    expect(cls).toContain('hidden')
    expect(cls).toContain('desktop:block')
  })

  it('below：小屏显示、达到断点隐藏', () => {
    const { container } = render(<Show below='mobileLandscape'>手机</Show>)
    const cls = container.firstElementChild!.className
    expect(cls).toContain('block')
    expect(cls).toContain('mobile-landscape:hidden')
  })

  it('表格列用 table-cell 恢复（不能用 block）', () => {
    expect(cellVisibleFrom('mobileLandscape')).toBe('hidden mobile-landscape:table-cell')
  })
})

describe('Table', () => {
  it('TableScroll 负责横滚，表格不顶宽整页', () => {
    const { container } = render(<TableScroll />)
    const cls = container.firstElementChild!.className
    expect(cls).toContain('overflow-x-auto')
    expect(cls).toContain('max-w-full')
  })

  it('minWidth 控制何时开始横滚', () => {
    const { container } = render(<Table minWidth='md' />)
    expect(container.firstElementChild!.className).toContain('min-w-[36rem]')
  })

  it('TH/TD 支持 hideBelow 收起次要列', () => {
    render(
      <table>
        <thead>
          <tr>
            <TH hideBelow='mobileLandscape'>ETF</TH>
          </tr>
        </thead>
        <tbody>
          <tr>
            <TD hideBelow='mobileLandscape' mono align='right'>
              1.23
            </TD>
          </tr>
        </tbody>
      </table>,
    )
    expect(screen.getByText('ETF').className).toContain('mobile-landscape:table-cell')
    const td = screen.getByText('1.23')
    expect(td.className).toContain('mobile-landscape:table-cell')
    expect(td.className).toContain('text-right')
    expect(td.className).toContain('font-mono')
  })
})
