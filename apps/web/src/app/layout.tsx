import type { Metadata } from 'next'

import Nav from '@/components/nav'

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
        <Nav />
        {children}
      </body>
    </html>
  )
}
