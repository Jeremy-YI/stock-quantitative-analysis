import type { Metadata } from 'next'

import '@/styles/globals.css'

export const metadata: Metadata = {
  title: '股市量化平台',
  description: 'A股 MACD 指标可视化',
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="zh-CN">
      <body>{children}</body>
    </html>
  )
}
