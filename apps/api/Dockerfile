# ============================================================
# api 的 Dockerfile —— 把 FastAPI 后端打包成一个可运行的容器
#
# 什么是 Dockerfile？一份「说明书」，告诉 Docker 如何一步步构建出
# 一个包含我们代码 + 运行环境的镜像（image），容器(container)就是
# 用镜像启动出来的运行实例。
#
# 下面用「多阶段构建」：第一阶段装依赖并编译，第二阶段只留运行时需要
# 的东西，让最终镜像更小、更安全。
# ============================================================

# ---- 阶段 1：构建环境（装依赖）----
FROM python:3.12-slim AS builder

# 用清华 PyPI 源，国内下载更快
ENV PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple

# 先只复制三个基础库的声明文件，利用 Docker 层缓存：依赖没变就不用重装
WORKDIR /app
COPY packages/indicators /app/packages/indicators
COPY packages/datasource /app/packages/datasource
COPY packages/market /app/packages/market
COPY apps/api/pyproject.toml /app/apps/api/pyproject.toml

# 装成一个虚拟环境（比直接装进系统 Python 更干净）
RUN python -m venv /opt/venv && \
    /opt/venv/bin/pip install --upgrade pip && \
    /opt/venv/bin/pip install -e /app/packages/indicators \
        -e /app/packages/datasource -e /app/packages/market && \
    /opt/venv/bin/pip install -e /app/apps/api

# ---- 阶段 2：运行环境（只留代码 + 虚拟环境）----
FROM python:3.12-slim

# 复制阶段 1 装好的虚拟环境
COPY --from=builder /opt/venv /opt/venv
# 让系统默认使用这个虚拟环境里的 python / 命令行工具
ENV PATH="/opt/venv/bin:$PATH"

WORKDIR /app

# 复制源码（含三个基础库，因为它们是 editable 安装，需要源码在场）
COPY packages /app/packages
COPY apps/api/src /app/apps/api/src
# editable 安装时 pyproject 在 /app/apps/api，把 src 也放到一致的位置
COPY apps/api/pyproject.toml /app/apps/api/pyproject.toml

# 数据目录默认挂载点（由 docker-compose 挂载宿主机 hsjday 到这里）
ENV STOCK_HSJDAY_ROOT=/data/hsjday

# 容器内监听 8000
EXPOSE 8000

# 启动命令：uvicorn 跑 main.py 里的 app 对象
# --host 0.0.0.0 表示接受来自容器外(其他容器/宿主)的连接
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--app-dir", "/app/apps/api/src"]
