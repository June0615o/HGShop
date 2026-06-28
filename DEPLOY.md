# 智汇优品 — 云服务器部署指南

## 📋 目录

1. [ECS 购买与初始配置](#1-ecs-购买与初始配置)
2. [安全组 / 防火墙配置](#2-安全组--防火墙配置)
3. [上传代码到服务器](#3-上传代码到服务器)
4. [一键部署](#4-一键部署)
5. [验证网站](#5-验证网站)
6. [日常运维](#6-日常运维)
7. [常见问题](#7-常见问题)

---

## 1. ECS 购买与初始配置

### 最低配置要求

| 项目 | 建议 |
|------|------|
| **CPU** | 1 核即可 |
| **内存** | 1 GB（推荐 2 GB） |
| **系统盘** | 20 GB |
| **操作系统** | Ubuntu 22.04 LTS / Ubuntu 24.04 LTS |
| **带宽** | 1 Mbps（按量计费即可） |

### 阿里云购买入口

1. 打开 [阿里云 ECS](https://ecs.console.aliyun.com/) 或 [腾讯云轻量应用服务器](https://cloud.tencent.com/product/lighthouse)
2. 学生认证后可享受 **约 ¥10/月** 的学生优惠
3. 选择 **Ubuntu 22.04** 镜像
4. 设置 root 密码（**牢记！**）
5. 购买后会得到一个 **公网 IP**（类似 `47.xxx.xxx.xxx`）

### 首次 SSH 登录

```bash
# 在本地终端连接服务器（替换为你的 IP）
ssh root@你的公网IP

# 首次登录后，建议更新系统
apt update && apt upgrade -y
```

---

## 2. 安全组 / 防火墙配置

> ⚠️ **关键步骤**：不配置安全组，网站无法从外网访问！

### 阿里云 — 安全组规则

进入 ECS 控制台 → 安全组 → 添加规则：

| 方向 | 端口 | 协议 | 授权对象 | 说明 |
|------|------|------|----------|------|
| 入方向 | 80 | TCP | 0.0.0.0/0 | HTTP 网站访问 |
| 入方向 | 443 | TCP | 0.0.0.0/0 | HTTPS（如需） |
| 入方向 | 22 | TCP | 0.0.0.0/0 | SSH 远程管理 |

### 腾讯云 — 防火墙

轻量应用服务器 → 防火墙 → 添加规则：同上。

### 服务器内部防火墙（Ubuntu）

SSH 登录后执行：

```bash
ufw allow 80/tcp
ufw allow 443/tcp
ufw allow 22/tcp
ufw enable
```

---

## 3. 上传代码到服务器

> 在你的 **本地 Windows 电脑** 上执行以下操作

### 方法一：通过 SCP 上传（推荐）

```bash
# 在 Git Bash 或 PowerShell 中执行
# 替换 YOUR_IP 为你的公网 IP

# 上传整个 webapp 目录到服务器的 /tmp
scp -r "/c/Users/Ayaka/Desktop/网络应用架构课程设计/webapp" root@YOUR_IP:/tmp/

# SSH 登录服务器，移动到正式目录
ssh root@YOUR_IP "mv /tmp/webapp /opt/smartpick"
```

### 方法二：GitHub 中转

```bash
# 在本地 webapp 目录中
cd "/c/Users/Ayaka/Desktop/网络应用架构课程设计/webapp"
git init
git add .
git commit -m "部署版本"

# 推送到 GitHub（先创建仓库）
git remote add origin https://github.com/你的用户名/SmartPick.git
git push -u origin main

# SSH 登录服务器后 clone
ssh root@YOUR_IP
cd /opt
git clone https://github.com/你的用户名/SmartPick.git smartpick
```

---

## 4. 一键部署

SSH 登录服务器后：

```bash
# 进入项目目录
cd /opt/smartpick

# 赋予执行权限
chmod +x deploy/deploy.sh

# 执行一键部署脚本
bash deploy/deploy.sh
```

脚本会自动完成：
1. ✅ 安装 Python 虚拟环境和 Nginx
2. ✅ 安装 Python 依赖
3. ✅ 初始化数据库 + 写入示例数据（默认账号）
4. ✅ 配置 Nginx 反向代理
5. ✅ 创建 systemd 服务（开机自启）

---

## 5. 验证网站

部署完成后：

```bash
# 查看服务状态
systemctl status smartpick

# 看到 "active (running)" 表示成功！
```

在浏览器访问：**`http://你的公网IP`**

### 默认测试账号

| 角色 | 用户名 | 密码 |
|------|--------|------|
| 👑 管理员 | `admin` | `admin123` |
| 📦 销售员 | `merchant1` | `merchant123` |
| 🛒 用户 | `user1` | `user123` |

---

## 6. 日常运维

### 查看日志

```bash
# 应用日志（实时）
journalctl -u smartpick -f

# Nginx 访问日志
tail -f /var/log/nginx/smartpick_access.log

# Nginx 错误日志
tail -f /var/log/nginx/smartpick_error.log
```

### 更新代码后重新部署

```bash
cd /opt/smartpick
git pull                      # 拉取最新代码
systemctl restart smartpick   # 重启服务
```

### 修改 SECRET_KEY（安全建议）

```bash
# 生成随机密钥
openssl rand -hex 32

# 编辑 systemd 服务文件
vi /etc/systemd/system/smartpick.service
# 将 Environment="SECRET_KEY=change-me-to-a-random-string"
# 改为上面生成的随机字符串

# 重载生效
systemctl daemon-reload
systemctl restart smartpick
```

---

## 7. 常见问题

### Q1: 访问网站显示"无法连接"

1. 检查安全组是否开放了 **80 端口**
2. 检查 Nginx 是否运行：`systemctl status nginx`
3. 检查应用是否运行：`systemctl status smartpick`

### Q2: 部署后出现 502 Bad Gateway

```bash
# 通常意味着 Gunicorn 没有正常启动
journalctl -u smartpick -n 50  # 查看最后 50 行日志
```

常见原因：数据库权限问题 → 检查 `/opt/smartpick/data/` 权限。

### Q3: 邮件发送不工作

编辑 `/etc/systemd/system/smartpick.service`，添加你的 QQ 邮箱配置：

```
Environment="MAIL_USERNAME=你的QQ@qq.com"
Environment="MAIL_PASSWORD=QQ邮箱授权码"
```

> QQ 邮箱授权码获取：QQ邮箱 → 设置 → 账户 → POP3/SMTP服务 → 生成授权码

### Q4: 如何绑定域名？

1. 在 DNS 服务商处添加 A 记录，指向你的公网 IP
2. 编辑 `/etc/nginx/sites-available/smartpick`，将 `server_name _;` 改为 `server_name 你的域名;`
3. 重新加载 Nginx：`systemctl reload nginx`

---

## 📎 附录：项目文件结构

```
webapp/
├── app.py              # Flask 主应用（路由、业务逻辑）
├── wsgi.py             # ★ 生产环境入口
├── models.py           # 数据模型
├── config.py           # 配置
├── requirements.txt    # Python 依赖
├── deploy/
│   ├── deploy.sh       # ★ 一键部署脚本
│   ├── nginx.conf      # Nginx 反向代理配置
│   └── smartpick.service  # systemd 服务单元
├── data/               # SQLite 数据库（自动生成）
├── static/             # 静态资源
└── templates/          # Jinja2 模板
    ├── admin/          # 管理员页面
    ├── sales/          # 销售人员页面
    └── *.html          # 前台页面
```
