# 股市量化平台（阶段 1：MACD 垂直切片）

前后端分离的最小可运行版本：**FastAPI 后端** 读本地通达信 hsjday 日线数据算 MACD，
**Next.js + Tailwind + ECharts 前端** 展示 K 线 + MACD 图，中间用 **nginx** 收口、**MySQL** 预留数据通道。

## 目录结构

```
stock-platform/
├── apps/
│   ├── api/                      # FastAPI 后端
│   │   ├── src/
│   │   │   ├── main.py           # 入口：create_app 工厂 + 异常映射
│   │   │   ├── config/           # pydantic-settings 配置（STOCK_ 前缀）
│   │   │   ├── errors/           # 领域异常（SymbolNotFound → 404 等）
│   │   │   ├── routers/          # 路由薄层
│   │   │   ├── schemas/          # Pydantic 契约
│   │   │   ├── services/         # 业务服务（算指标）
│   │   │   └── repositories/     # 数据仓储（读 hsjday 文件）
│   │   ├── migrations/           # MySQL 建表 SQL（阶段 2 用）
│   │   ├── tests/                # API 集成测试
│   │   ├── pyproject.toml
│   │   └── Dockerfile
│   └── web/                      # Next.js 前端
│       ├── src/
│       │   ├── app/              # 页面 + 布局
│       │   ├── components/ui/    # shadcn 风格基础组件
│       │   ├── features/macd/    # MACD 功能（图表/请求/样式）
│       │   ├── lib/              # cn 工具 + HTTP 封装
│       │   └── styles/           # 全局样式 + 语义色
│       ├── tests/                # vitest 测试
│       ├── package.json
│       └── Dockerfile
├── packages/
│   ├── indicators/               # 指标库（MACD，纯函数）
│   ├── datasource/               # 数据源（通达信 hsjday 只读解析）
│   └── market/                   # A股业务规则（交易日历/涨跌停/复权）
├── tests/                        # 后端单元 + 集成测试 + fixtures
├── scripts/                      # 生成测试 fixtures 的脚本
├── docker-compose.yml            # 一键起整套服务
├── nginx.conf                    # 反向代理网关配置
├── Makefile                      # 开发命令入口
└── pyproject.toml                # 根目录 pytest 配置
```

## 快速开始（本地开发）

### 后端

```bash
# 1. 建虚拟环境 + 装依赖（清华源，顺序别乱：先三个基础库再 api）
make install

# 2. 跑测试
make test

# 3. 起开发服务器（热重载）
make api
# 打开 http://localhost:8000/docs 看 Swagger
```

### 前端

```bash
cd apps/web
npm install        # 安装依赖（.npmrc 已配 npmmirror 镜像源）
npm run dev        # 打开 http://localhost:3000
```

前端默认请求 `/api/v1`，本地开发时 `next.config.ts` 里没配代理，需要后端跑在 8000
再用 nginx 或改 `NEXT_PUBLIC_API_BASE_URL` 指向后端地址（生产用 nginx 收口，见下文）。

## API

统一响应结构 `{ message, body }`：

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/v1/health` | 健康检查（返回状态 + 上海时区时间） |
| GET | `/api/v1/indicators/macd?symbol=600519&start=&end=` | MACD 序列 |

`symbol` 必须 6 位数字；`start`/`end` 为可选日期（`YYYY-MM-DD`，闭区间）。

- 正常 → `200`，`body.series` 是 `[{ date, close, dif, dea, macd }, ...]`
- 代码不存在 → `404`
- 参数校验失败 → `422`

### 业务规则（写进代码，不是注释）

- **时区**：`market/calendar.py` 的 `MARKET_TIMEZONE = Asia/Shanghai`，全站统一。
- **交易日历**：阶段 1 只排除周末，法定节假日休市表为 TODO。
- **涨跌停**：`market/price_limit.py`——主板 ±10%、创业板/科创板 ±20%、ST ±5%、北交所 ±30%。
- **复权**：`market/adjust.py`——`AdjustMode` 枚举，默认前复权；阶段 1 的 hsjday `.day` 为不复权原始数据。

## 测试

```bash
# 后端（单元 + 集成，共 23 个用例）
make test

# 前端（vitest）
cd apps/web && npm test
```

后端测试覆盖：MACD 黄金值逐点比对（真实 600519 切片，精确到 4 位小数）、空数据/不足 26 根/
停牌跳空等边界、hsjday 二进制解析、涨跌停规则、API 的 200/404/422、仓储读真实 .day 文件。

黄金值 fixtures 由 `scripts/make_fixtures.py` 生成（读真实 hsjday 数据切片 + 用指标库算一遍）。

## 运维文件说明（写给新手）

### Docker 是什么

Docker 把「代码 + 运行环境」打包成一个**镜像（image）**，像一份完整的安装包；
用镜像启动出来的运行实例叫**容器（container）**。好处是：你 Mac 上能跑的，
服务器上也能原样跑，不会「我这好好的、上线就挂」。

- `Dockerfile`：**如何构建镜像**的说明书（装什么依赖、复制哪些文件、启动什么命令）。
- `docker-compose.yml`：**如何编排多个容器**（数据库 + 后端 + 前端 + 网关一起起）。

### docker-compose 里每个 service 的作用

| service | 干什么 | 为什么需要 |
| --- | --- | --- |
| `mysql` | 跑 MySQL 8 数据库 | 阶段 2 存日线数据 `daily_bars` 和指标缓存 `indicator_cache`，阶段 1 先占位 |
| `api` | 跑 FastAPI 后端 | 处理 `/api/v1/**` 请求；挂载宿主机 hsjday 数据目录进来读 |
| `web` | 跑 Next.js 前端 | 渲染页面和图表，只对内暴露 3000 端口 |
| `nginx` | 反向代理网关（唯一对外 80 端口） | 收口端口、按路径转发、解决跨域 |

### nginx 承担什么角色

nginx 在这里不是「网站服务器」，而是**反向代理**：

1. **端口收口**：对外只开 80，内部 8000（后端）/3000（前端）不暴露。
2. **路径分流**：`/api/**` → 转给后端，其余 → 转给前端。
3. **同源访问**：页面和接口都从 `http://localhost` 一个地址出去，天然没有跨域问题。

### npm 常用命令速查（本项目统一用 npm）

```bash
npm install          # 按 package.json 装依赖，会顺便更新 package-lock.json
npm run dev          # 本地开发（Next.js 热更新）
npm run build        # 生产构建，输出到 .next
npm run start        # 用构建产物启动生产服务（需先 build）
npm run test         # 跑 vitest 测试
npm ci               # 严格按 package-lock.json 装（见下面区别）
```

`npm ci` 和 `npm install` 的区别：

- `npm install`：宽松，会按 `^` 范围解析最新版本并**改写 lock 文件**。
- `npm ci`：严格，**完全照 lock 文件**装，删掉 `node_modules` 重来，速度更快、结果可复现。
- **CI 里必须用 `npm ci`**：保证「构建机装的依赖」和「lock 文件记录的」完全一致，避免「本地能跑、CI 挂了」。

镜像源配置在 `apps/web/.npmrc`：`registry=https://registry.npmmirror.com`（国内加速）。

## 技术选型与风格说明

- **前端**：Next.js 15 + React 19 + Tailwind CSS v4 + shadcn 风格组件 + ECharts（echarts-for-react）。
- **样式组织**：长 class 组合抽到 `xxx-styles.ts` 导出常量；语义色集中在 `styles/globals.css` 的
  `@theme`（`up`/`down`/`neutral` = A股红涨绿跌）；条件 class 用 `cn()`（clsx + tailwind-merge）。
  > 注：Tailwind v4 把配置从 v3 的 `tailwind.config.ts` 挪到了 CSS 的 `@theme`（等价物），
  > 语义色写在这里，组件里禁止散落 hex。
- **后端**：FastAPI + Pydantic v2，三层（routers → services → repositories）+ 领域异常映射 HTTP。
- **指标**：`indicators/macd` 纯函数，魔法数字 12/26/9/2 提为命名常量，EMA 首值做种子（与通达信脚本一致）。
- **代码风格**：Python `main()` + UPPER_SNAKE 常量 + 中文注释；TS 无分号/单引号/2 空格，`interface` vs `type` 分工。

## 阶段 2（TODO）

- MySQL 灌入日线数据（ETL），repository 增加 `MySqlDailyBarRepository`。
- 接入法定节假日交易日历、复权因子。
- 更多指标（KDJ / MA / 量能）与策略回测。
