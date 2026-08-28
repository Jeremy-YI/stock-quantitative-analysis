import { defineConfig } from 'vitest/config'
import path from 'node:path'

// vitest 配置：jsdom 环境跑组件测试，@ 别名解析到 src。
// 测试文件里的 JSX 用 automatic runtime（React 19），避免手动 import React。
export default defineConfig({
  test: {
    environment: 'jsdom',
    setupFiles: ['./vitest.setup.ts'],
    globals: true,
  },
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  esbuild: {
    jsx: 'automatic',
    jsxImportSource: 'react',
  },
})
