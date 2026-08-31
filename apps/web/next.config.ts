import type { NextConfig } from 'next'
import path from 'node:path'

// 后端地址（本地开发默认 8000；生产由 nginx 直接反代 /api/，这里的 rewrite
// 只在请求真正落到 Next.js 时兜底，与 nginx 行为一致、不冲突）
const API_ORIGIN = process.env.API_ORIGIN ?? 'http://localhost:8000'

const nextConfig: NextConfig = {
  reactStrictMode: true,
  // 构建产物目录可用环境变量切开：`NEXT_DIST_DIR=.next-build next build`
  // 这样生产构建不会覆盖 dev server 正在用的 .next（覆盖会让开发页面报
  // "Cannot find module './vendor-chunks/xxx.js'" 然后 500）
  distDir: process.env.NEXT_DIST_DIR ?? '.next',
  // 显式指定本目录为构建根，避免 Next.js 误把上层目录（存在别的 lockfile）当 workspace 根
  outputFileTracingRoot: path.join(__dirname),
  async rewrites() {
    // 开发环境：把 /api/v1/** 转发到 FastAPI，让前端用同源相对路径即可联调，
    // 与 nginx 的 location /api/ 反代行为保持一致（同源访问、无跨域）。
    return [
      {
        source: '/api/:path*',
        destination: `${API_ORIGIN}/api/:path*`,
      },
    ]
  },
}

export default nextConfig
