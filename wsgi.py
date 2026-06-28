"""WSGI 生产入口 — 支持 Gunicorn（Linux）和 Waitress（跨平台）"""
import os
import sys

# 确保项目目录在 sys.path 中
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import app  # noqa: E402

# ── 环境变量默认值（生产环境请通过 export 设置）─────────────────
# SECRET_KEY  — Flask 密钥（务必修改！）
# DATABASE_URL — 数据库连接（默认 SQLite）
# MAIL_USERNAME / MAIL_PASSWORD — QQ 邮箱 SMTP

if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='智汇优品 WSGI 服务器')
    parser.add_argument('--host', default='0.0.0.0', help='监听地址 (默认 0.0.0.0)')
    parser.add_argument('--port', type=int, default=8000, help='监听端口 (默认 8000)')
    parser.add_argument('--threads', type=int, default=4, help='线程数 (默认 4)')
    args = parser.parse_args()

    # 优先使用 Waitress（Windows/Linux 通用）
    try:
        from waitress import serve
        print(f'🚀 Waitress 启动 → http://{args.host}:{args.port}')
        serve(app, host=args.host, port=args.port, threads=args.threads)
    except ImportError:
        print('⚠ Waitress 未安装，回退到 Flask 开发服务器（仅供测试）')
        app.run(host=args.host, port=args.port, debug=False)
