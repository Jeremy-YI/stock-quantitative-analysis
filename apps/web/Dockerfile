# ============================================================
# web 的 Dockerfile —— 把 Next.js 前端打包成可运行容器
# 构建上下文是 apps/web 目录（见 docker-compose.yml 的 build.context）
# ============================================================

# ---- 阶段 1：只装依赖（利用缓存：package.json 不变就不重装）----
FROM node:20-alpine AS deps
WORKDIR /app

# 先复制依赖清单和 .npmrc（配了国内镜像源，加速下载）
COPY package.json package-lock.json .npmrc* ./
# npm ci：严格按 package-lock.json 安装，速度比 npm install 快且结果可复现
RUN npm ci

# ---- 阶段 2：构建生产产物 ----
FROM node:20-alpine AS builder
WORKDIR /app
# 复用阶段 1 装好的 node_modules
COPY --from=deps /app/node_modules ./node_modules
COPY . .
# 跑 Next.js 生产构建，输出到 .next 目录
RUN npm run build

# ---- 阶段 3：运行环境（只保留运行需要的东西）----
FROM node:20-alpine AS runner
WORKDIR /app
# 生产模式：Next.js 会用优化后的产物运行
ENV NODE_ENV=production

COPY --from=builder /app/package.json ./package.json
COPY --from=builder /app/node_modules ./node_modules
COPY --from=builder /app/.next ./.next
COPY --from=builder /app/public ./public
COPY --from=builder /app/next.config.* ./

EXPOSE 3000

# npm start 会跑 next start，以生产模式启动
CMD ["npm", "start"]
