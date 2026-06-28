# 🛒 智汇优品 (SmartPick)

> 网络应用架构设计与开发 课程设计 — 华南理工大学 计算机科学与工程学院

[![Python](https://img.shields.io/badge/Python-3.13-blue)](https://python.org)
[![Flask](https://img.shields.io/badge/Flask-3.1-green)](https://flask.palletsprojects.com/)
[![Docker](https://img.shields.io/badge/Docker-27.5-blue)](https://docker.com)
[![Deploy](https://img.shields.io/badge/live-online-brightgreen)](http://114.132.89.114)

**在线地址**：[http://114.132.89.114](http://114.132.89.114) ｜ **代码仓库**：[GitHub](https://github.com/June0615o/SmartPick)

---

## 📋 项目简介

智汇优品是一个完整的电子商务平台，在基础电商功能之上集成了**大数据采集、用户行为分析、个性化推荐系统**及**数据可视化大屏**，支持三类用户角色的协同工作。

## ✨ 功能特性

### 🛒 用户端（Customer）
- 用户注册/登录/注销，密码 PBKDF2-SHA256 加密
- 商品浏览、搜索、分类筛选、价格/销量排序、分页
- 购物车管理（添加/修改数量/删除）
- 下单结算 → 库存自动扣减 → 邮件确认
- 订单历史查看
- 未登录用户可浏览商品

### 📦 销售端（Sales）
- 商品 CRUD（上架/下架/编辑）
- 商品类别管理（添加/删除）
- 销售仪表盘（今日订单、总收入、库存预警）
- 用户浏览/购买日志查看
- 销售趋势监控

### 👑 管理端（Admin）
- 用户管理（添加销售/禁用/删除）
- 密码重置
- 全局操作日志审计
- 销售统计报表（按类别/状态）

### 📊 数据分析与推荐
- **用户画像**：地域、购买力、偏好分类
- **销售趋势**：日/周/月粒度聚合
- **异常检测**：2σ 标准差实时判别
- **商品排行榜**：TOP 15 热销榜单
- **推荐系统**：偏好推荐 + 协同过滤 + 冷启动
- **数据大屏**：Chart.js 可视化仪表盘

### 🔧 运维特性
- Docker Compose 一键部署（Nginx + Waitress 双容器）
- systemd 开机自启
- CSV 数据导出
- 响应式设计（桌面/平板/手机）

---

## 🛠 技术栈

| 层级 | 技术 |
|------|------|
| 后端框架 | Python Flask 3.1 |
| ORM | Flask-SQLAlchemy 3.1 |
| 认证 | Flask-Login 0.6 |
| 数据库 | SQLite（开发）/ 可切换 PostgreSQL |
| 前端 | Bootstrap 5 + Chart.js 4.4 |
| WSGI 服务器 | Waitress（跨平台）/ Gunicorn（Linux） |
| 反向代理 | Nginx 1.27 |
| 容器化 | Docker CE 27.5 + Docker Compose v2 |
| 云平台 | 腾讯云轻量应用服务器 (Ubuntu 22.04) |

---

## 🚀 快速开始

### 本地开发

```bash
# 1. 克隆仓库
git clone git@github.com:June0615o/SmartPick.git
cd SmartPick

# 2. 安装依赖
pip install -r requirements.txt

# 3. 初始化数据库（含示例数据）
PYTHONIOENCODING=utf-8 flask init-db

# 4. 启动开发服务器
python app.py

# 5. 浏览器访问
# http://localhost:5000
```

### Docker 部署

```bash
# 构建并启动
docker compose up -d --build

# 查看状态
docker compose ps

# 查看日志
docker logs smartpick-app -f

# 重启
docker compose restart
```

---

## 🔑 测试账号

| 角色 | 用户名 | 密码 |
|------|--------|------|
| 👑 管理员 | `admin` | `admin123` |
| 📦 销售人员 | `merchant1` | `merchant123` |
| 🛒 普通用户 | `user1` | `user123` |

> 冷启动模拟数据包含 30 个用户（密码均为 `123456`），覆盖 heavy/medium/light/browser 四个消费层级，已生成 402 条购买记录。

---

## 📁 项目结构

```
SmartPick/
├── app.py                 # 主应用（路由、业务逻辑、API）
├── wsgi.py                # 生产环境 WSGI 入口
├── models.py              # 数据模型（10 张表）
├── config.py              # 应用配置
├── seed_data.py           # 冷启动数据生成器
├── Dockerfile             # Docker 镜像构建
├── docker-compose.yml     # 容器编排
├── docker-entrypoint.sh   # 容器启动脚本
├── requirements.txt       # Python 依赖
├── .dockerignore
├── .gitignore
├── DEPLOY.md              # 详细部署文档
├── deploy/
│   ├── deploy.sh          # 裸机一键部署
│   ├── nginx.conf          # 裸机 Nginx 配置
│   ├── nginx-docker.conf   # Docker Nginx 配置
│   └── smartpick.service   # systemd 服务单元
├── data/                  # SQLite 数据库（Git 忽略）
├── static/                # 静态资源
└── templates/             # Jinja2 模板（18 个 HTML）
    ├── base.html          # 基础模板
    ├── index.html         # 首页
    ├── product_detail.html
    ├── login.html / register.html
    ├── cart.html / checkout.html
    ├── orders.html / order_detail.html
    ├── analytics.html     # 数据大屏
    ├── sales/             # 销售管理
    │   ├── dashboard.html
    │   ├── products.html / product_form.html
    │   ├── categories.html
    │   └── logs.html
    └── admin/             # 管理后台
        ├── dashboard.html
        ├── users.html
        └── operation_logs.html
```

---

## 📊 数据采集设计

系统自动采集四类日志数据：

| 日志类型 | 表名 | 采集内容 |
|----------|------|----------|
| 浏览行为 | `browse_logs` | 用户ID、商品ID、类别、IP、停留时长 |
| 购买记录 | `purchase_logs` | 用户ID、商品ID、数量、单价、总价 |
| 登录记录 | `login_logs` | 用户ID、IP、登录时间 |
| 操作日志 | `operation_logs` | 用户ID、操作描述、IP、时间 |

---

## 📄 相关文档

- [DEPLOY.md](DEPLOY.md) — 云服务器部署详细指南
- 课程设计报告：`202330451441_潘昊.docx`
- 课程设计 PDF 要求：`《网络应用开发》课程设计.pdf`

---

> 🤖 本项目在开发过程中使用了 Claude Code (Anthropic) 作为 AI 编程助手，详见课程设计报告中的「AI 工具使用记录」章节。
