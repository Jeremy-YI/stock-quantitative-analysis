import { defineConfig } from 'vitest/config'
import path from 'node:path'

// vitest 配置：jsdom 环境跑组件测试，@ 别名解析到 src。
// 测试文件里的 JSX 用 automatic runtime（React 19），避免手动 import React。
export default defineConfig({
  test: {
    environment: 'jsdom',
    setupFiles: ['./vitest.setup.ts'],
    globals: true,
    // 组件/单测只跑 tests/ 目录；e2e/ 是 Playwright 的，交给 npx playwright test
    include: ['tests/**/*.test.{ts,tsx}'],
    exclude: ['e2e/**', 'node_modules/**', '**/test-results/**', '**/playwright-report/**'],
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
