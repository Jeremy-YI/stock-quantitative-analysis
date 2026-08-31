import type { Metadata, Viewport } from 'next'

import Nav from '@/components/nav'

import '@/styles/globals.css'

export const metadata: Metadata = {
  title: '股市量化平台',
  description: 'A股板块资金与个股推荐看板',
}

/** 移动端必须的视口声明（没有它手机上会按 980px 缩放渲染，响应式全废）。 */
export const viewport: Viewport = {
  width: 'device-width',
  initialScale: 1,
  viewportFit: 'cover',
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang='zh-CN'>
      <body className='flex min-h-screen flex-col antialiased'>
        <Nav />
        <div className='flex-1'>{children}</div>
      </body>
    </html>
  )
}
