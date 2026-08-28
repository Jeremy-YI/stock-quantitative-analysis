# ============================================================
# 开发常用命令入口（Makefile）
# 用法：在仓库根目录执行 `make 目标名`，例如 `make install`
# 每个目标前面的注释用中文解释它在做什么、什么时候用。
# ============================================================

# 所有目标默认不依赖文件，只要目录里没有同名文件就不会被跳过
.PHONY: install test pytest api web build up down

# ------------------------------------------------------------
# 一、Python 后端
# ------------------------------------------------------------

# 创建虚拟环境：隔离本项目依赖，不污染系统 Python
venv:
	python3 -m venv .venv
	@echo "✅ 已创建虚拟环境 .venv"

# 安装后端依赖（用清华源加速，国内网络更快）
# 顺序很重要：先装三个基础库(indicators/datasource/market)，再装 api，
# 因为 api 的 pyproject 依赖前三个库，必须先存在才能被 pip 解析到。
install: venv
	.venv/bin/python -m pip install -i https://pypi.tuna.tsinghua.edu.cn/simple --upgrade pip
	.venv/bin/python -m pip install -i https://pypi.tuna.tsinghua.edu.cn/simple -e packages/indicators -e packages/datasource -e packages/market
	.venv/bin/python -m pip install -i https://pypi.tuna.tsinghua.edu.cn/simple -e "apps/api[dev]"

# 跑后端单元 + 集成测试（必须在 install 之后执行）
test: pytest

pytest:
	.venv/bin/python -m pytest

# 启动后端开发服务器（热重载，改代码自动重启）
api:
	.venv/bin/uvicorn main:app --reload --app-dir apps/api/src --port 8000

# ------------------------------------------------------------
# 二、前端（Next.js，统一用 npm）
# ------------------------------------------------------------

# 安装前端依赖（CI 里用 npm ci，本地开发用 npm install）
web:
	cd apps/web && npm install

# 启动前端开发服务器（默认 http://localhost:3000）
web-dev:
	cd apps/web && npm run dev

# 前端生产构建（输出到 apps/web/.next）
web-build:
	cd apps/web && npm run build

# ------------------------------------------------------------
# 三、Docker（整套一键起/停，见 README「运维文件说明」）
# ------------------------------------------------------------

# 构建并后台启动所有服务（api + web + nginx + mysql）
up:
	docker compose up -d --build

# 停止并移除所有服务容器
down:
	docker compose down
