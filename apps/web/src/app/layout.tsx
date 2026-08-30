import type { Metadata } from 'next'
import Link from 'next/link'

import '@/styles/globals.css'

export const metadata: Metadata = {
  title: '股市量化平台',
  description: 'A股技术指标与选股策略看板',
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
            href="/indicators"
            className="text-sm text-muted-foreground hover:text-foreground"
          >
            技术指标
          </Link>
          <Link
            href="/strategies"
            className="text-sm text-muted-foreground hover:text-foreground"
          >
            选股策略
          </Link>
          <Link
            href="/backtest"
            className="text-sm text-muted-foreground hover:text-foreground"
          >
            策略回测
          </Link>
          <Link
            href="/research"
            className="text-sm text-muted-foreground hover:text-foreground"
          >
            因子研究
          </Link>
          <Link
            href="/scheduler"
            className="text-sm text-muted-foreground hover:text-foreground"
          >
            任务调度
          </Link>
        </nav>
        {children}
      </body>
    </html>
  )
}
