'use client'

/**
 * 顶部导航：标题居中 + 左侧下拉菜单（点开列出所有页面）。
 */
import Link from 'next/link'
import { useState } from 'react'

const PAGES = [
  { href: '/', label: '概览' },
  { href: '/sectors', label: '板块资金' },
  { href: '/recommendations', label: '个股推荐' },
  { href: '/news', label: '最新消息' },
  { href: '/events', label: '事件日历' },
  { href: '/ai', label: 'AI 解读' },
]

export default function Nav() {
  const [open, setOpen] = useState(false)

  return (
    <header className="sticky top-0 z-50 border-b border-gray-200 bg-white/90 backdrop-blur">
      <div className="relative flex h-14 items-center justify-center px-4">
        {/* 左侧下拉按钮 */}
        <button
          onClick={() => setOpen((v) => !v)}
          className="absolute left-4 flex items-center gap-1.5 rounded-md px-3 py-1.5 text-sm text-gray-700 hover:bg-gray-100"
        >
          <svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden>
            <path d="M2 4h12M2 8h12M2 12h12" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
          </svg>
          菜单
        </button>

        {/* 居中标题 */}
        <span className="text-lg font-bold tracking-wide">股市量化平台</span>
      </div>

      {/* 下拉菜单 */}
      {open && (
        <nav className="absolute left-0 right-0 border-b border-gray-200 bg-white shadow-lg">
          <div className="mx-auto max-w-md px-2 py-2">
            {PAGES.map((p) => (
              <Link
                key={p.href}
                href={p.href}
                onClick={() => setOpen(false)}
                className="block rounded-md px-4 py-2.5 text-[15px] text-gray-700 hover:bg-gray-50 hover:text-black"
              >
                {p.label}
              </Link>
            ))}
          </div>
        </nav>
      )}
    </header>
  )
}
