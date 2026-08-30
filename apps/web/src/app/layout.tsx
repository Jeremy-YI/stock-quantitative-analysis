import type { Metadata } from 'next'
import Link from 'next/link'

import '@/styles/globals.css'

export const metadata: Metadata = {
  title: '股市量化平台',
  description: 'A股板块资金与个股推荐看板',
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="zh-CN">
      <body>
        <nav className="flex items-center gap-4 border-b border-border bg-background px-6 py-3">
          <span className="text-sm font-semibold">股市量化平台</span>
          <Link
            href="/"
            className="text-sm text-muted-foreground hover:text-foreground"
          >
            概览
          </Link>
          <Link
            href="/sectors"
            className="text-sm text-muted-foreground hover:text-foreground"
          >
            板块资金
          </Link>
          <Link
            href="/recommendations"
            className="text-sm text-muted-foreground hover:text-foreground"
          >
            个股推荐
          </Link>
          <Link
            href="/news"
            className="text-sm text-muted-foreground hover:text-foreground"
          >
            最新消息
          </Link>
          <Link
            href="/events"
            className="text-sm text-muted-foreground hover:text-foreground"
          >
            事件日历
          </Link>
          <Link
            href="/ai"
            className="text-sm text-muted-foreground hover:text-foreground"
          >
            AI 解读
          </Link>
        </nav>
        {children}
      </body>
    </html>
  )
}
