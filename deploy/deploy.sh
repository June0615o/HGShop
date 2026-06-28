#!/bin/bash
# ============================================================
# 惠购商城 — 一键部署脚本 (Ubuntu 20.04/22.04/24.04)
# 在云服务器上以 root 执行: bash deploy.sh
# ============================================================
set -e

APP_DIR="/opt/huigomall"
VENV_DIR="$APP_DIR/venv"
APP_USER="www-data"

echo "========================================"
echo "  惠购商城 — 自动部署脚本"
echo "========================================"

# 1. 系统依赖
echo ">>> [1/7] 安装系统依赖..."
apt-get update -qq
apt-get install -y -qq python3 python3-venv python3-pip nginx sqlite3

# 2. 创建目录
echo ">>> [2/7] 创建应用目录..."
mkdir -p $APP_DIR/data
mkdir -p $APP_DIR/static

# 3. 虚拟环境
echo ">>> [3/7] 创建 Python 虚拟环境..."
if [ ! -d "$VENV_DIR" ]; then
    python3 -m venv $VENV_DIR
fi
$VENV_DIR/bin/pip install --upgrade pip -q
$VENV_DIR/bin/pip install -r $APP_DIR/requirements.txt -q

# 4. 初始化数据库
echo ">>> [4/7] 初始化数据库..."
cd $APP_DIR
$VENV_DIR/bin/python -c "
from app import app
from models import db
with app.app_context():
    db.create_all()
    print('数据库表已创建')
"

# 如果数据库为空，初始化示例数据
if [ ! -f "$APP_DIR/data/ecommerce.db" ] || [ $(stat -c%s "$APP_DIR/data/ecommerce.db" 2>/dev/null || echo 0) -lt 1024 ]; then
    echo ">>> 写入示例数据..."
    cd $APP_DIR && PYTHONIOENCODING=utf-8 $VENV_DIR/bin/flask init-db
fi

# 5. 权限
echo ">>> [5/7] 设置文件权限..."
chown -R $APP_USER:$APP_USER $APP_DIR
chmod -R 755 $APP_DIR

# 6. Nginx
echo ">>> [6/7] 配置 Nginx..."
cp $APP_DIR/deploy/nginx.conf /etc/nginx/sites-available/huigomall
ln -sf /etc/nginx/sites-available/huigomall /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default
nginx -t && systemctl reload nginx

# 7. systemd 服务
echo ">>> [7/7] 配置 systemd 服务..."
cp $APP_DIR/deploy/huigomall.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable huigomall
systemctl restart huigomall

echo ""
echo "========================================"
echo "  ✅ 部署完成！"
echo "========================================"
echo "  网站: http://$(curl -s ifconfig.me 2>/dev/null || echo 'YOUR_IP')"
echo "  管理员: admin / admin123"
echo "  销售员: merchant1 / merchant123"
echo "  用户:   user1 / user123"
echo ""
echo "  常用命令:"
echo "    systemctl status huigomall   # 查看服务状态"
echo "    journalctl -u huigomall -f   # 实时日志"
echo "    systemctl restart huigomall  # 重启服务"
echo "========================================"
