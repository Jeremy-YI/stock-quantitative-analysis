'use client'

/**
 * 顶部导航（响应式）：
 *  - < lg：汉堡按钮在左、标题居中，点开抽屉式菜单（手机主路径）
 *  - >= lg：标题居中 + 下方一行导航链接（桌面不用点两次）
 * 当前页高亮走 usePathname，不写死。
 */
import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { useEffect, useState } from 'react'

import { Container } from '@/design'
import { cn } from '@/lib/utils'

const PAGES = [
  { href: '/', label: '概览' },
  { href: '/sectors', label: '板块资金' },
  { href: '/recommendations', label: '个股推荐' },
  { href: '/news', label: '最新消息' },
  { href: '/events', label: '事件日历' },
  { href: '/ai', label: 'AI 解读' },
]

export default function Nav() {
  const pathname = usePathname()
  const [open, setOpen] = useState(false)

  // 路由变化自动收起抽屉
  useEffect(() => {
    setOpen(false)
  }, [pathname])

  const isActive = (href: string) => (href === '/' ? pathname === '/' : pathname.startsWith(href))

  return (
    <header className='sticky top-0 z-50 border-b border-border bg-background/90 backdrop-blur'>
      <Container size='xl' className='relative'>
        {/* 顶行：汉堡（小屏） + 居中标题 */}
        <div className='relative flex h-14 items-center justify-center'>
          <button
            type='button'
            onClick={() => setOpen((v) => !v)}
            aria-label='打开菜单'
            aria-expanded={open}
            className='absolute left-0 flex size-10 items-center justify-center rounded-md text-muted-foreground hover:bg-surface-hover hover:text-foreground desktop:hidden'
          >
            <svg width='18' height='18' viewBox='0 0 16 16' fill='none' aria-hidden>
              {open ? (
                <path
                  d='M3.5 3.5l9 9m0-9l-9 9'
                  stroke='currentColor'
                  strokeWidth='1.5'
                  strokeLinecap='round'
                />
              ) : (
                <path
                  d='M2 4h12M2 8h12M2 12h12'
                  stroke='currentColor'
                  strokeWidth='1.5'
                  strokeLinecap='round'
                />
              )}
            </svg>
          </button>

          <Link href='/' className='text-h3 font-bold tracking-wide'>
            股市量化平台
          </Link>
        </div>

        {/* 桌面：标题下方的导航行 */}
        <nav className='hidden justify-center gap-1 pb-2 desktop:flex'>
          {PAGES.map((p) => (
            <Link
              key={p.href}
              href={p.href}
              className={cn(
                'rounded-md px-3 py-1.5 text-body-sm transition-colors',
                isActive(p.href)
                  ? 'bg-accent-soft font-medium text-accent'
                  : 'text-muted-foreground hover:bg-surface-hover hover:text-foreground',
              )}
            >
              {p.label}
            </Link>
          ))}
        </nav>
      </Container>

      {/* 小屏抽屉 */}
      {open && (
        <nav className='border-t border-border bg-background shadow-lg desktop:hidden'>
          <Container size='xl' className='py-2'>
            <ul className='grid grid-cols-2 gap-1 mobile-portrait:grid-cols-3'>
              {PAGES.map((p) => (
                <li key={p.href}>
                  <Link
                    href={p.href}
                    onClick={() => setOpen(false)}
                    className={cn(
                      'block rounded-md px-3 py-2.5 text-body-sm',
                      isActive(p.href)
                        ? 'bg-accent-soft font-medium text-accent'
                        : 'text-foreground hover:bg-surface-hover',
                    )}
                  >
                    {p.label}
                  </Link>
                </li>
              ))}
            </ul>
          </Container>
        </nav>
      )}
    </header>
  )
}
