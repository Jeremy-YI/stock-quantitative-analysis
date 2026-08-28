import { defineConfig } from 'vitest/config'
import path from 'node:path'

// vitest 配置：让测试里也能用 @/ 别名
export default defineConfig({
  test: {
    environment: 'node',
  },
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
})
