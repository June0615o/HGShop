#!/bin/bash
# Docker 容器启动脚本 — 初始化数据库 + 启动应用
set -e

cd /app

# 确保表结构存在（幂等）
python -c "
from app import app
from models import db
with app.app_context():
    db.create_all()
    print('Database tables ensured')
"

# 如果数据库为空（无分类），写入示例数据
python -c "
from app import app
from models import db, Category
with app.app_context():
    if Category.query.count() == 0:
        print('Empty database, initializing sample data...')
        import subprocess, os
        os.environ['PYTHONIOENCODING'] = 'utf-8'
        subprocess.run(['flask', 'init-db'], check=True)
    else:
        print(f'Database already has {Category.query.count()} categories, skipping init')
"

# 启动应用
exec python wsgi.py --host 0.0.0.0 --port 8000
