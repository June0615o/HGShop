# 惠购商城 — Docker 镜像
FROM python:3.13-slim

WORKDIR /app

# 安装依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt -q

# 复制应用代码
COPY . .

# 启动脚本 + 权限
RUN chmod +x docker-entrypoint.sh && mkdir -p /app/data

VOLUME ["/app/data"]

EXPOSE 8000

ENTRYPOINT ["/app/docker-entrypoint.sh"]
