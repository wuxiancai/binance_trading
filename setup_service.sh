#!/bin/bash
# systemd 服务配置脚本
# 用于创建和配置币安交易系统的 systemd 服务

set -e  # 遇到错误立即退出

# 配置变量
PROJECT_NAME="binance_trading"
DEPLOY_USER="$(whoami)"
DEPLOY_DIR="$HOME/${PROJECT_NAME}"
SERVICE_NAME="${PROJECT_NAME}"

echo "=== 配置 systemd 服务 ==="

# 创建 systemd 服务文件
echo "[1/3] 创建 systemd 服务文件..."
sudo tee "/etc/systemd/system/${SERVICE_NAME}.service" > /dev/null << EOF
[Unit]
Description=Binance Trading Service
After=network.target
Wants=network.target

[Service]
Type=simple
User=${DEPLOY_USER}
Group=${DEPLOY_USER}
WorkingDirectory=${DEPLOY_DIR}
Environment=PYTHONPATH=${DEPLOY_DIR}
Environment=PYTHONUNBUFFERED=1
ExecStart=${DEPLOY_DIR}/.venv/bin/python ${DEPLOY_DIR}/webapp.py
Environment="PATH=/usr/local/bin:/usr/bin:/bin"
ExecReload=/bin/kill -HUP \$MAINPID
Restart=always
RestartSec=10
KillMode=mixed
TimeoutStopSec=30

# 日志配置
StandardOutput=journal
StandardError=journal
SyslogIdentifier=${SERVICE_NAME}

# 资源限制
LimitNOFILE=65536
LimitNPROC=4096

[Install]
WantedBy=multi-user.target
EOF

echo "systemd 服务文件已创建: /etc/systemd/system/${SERVICE_NAME}.service"

# 重新加载 systemd 配置
echo "[2/3] 重新加载 systemd 配置..."
sudo systemctl daemon-reload

# 启用服务（开机自启）
echo "[3/3] 启用服务开机自启..."
sudo systemctl enable "${SERVICE_NAME}"

echo "=== systemd 服务配置完成 ==="
echo "服务名称: ${SERVICE_NAME}"
echo "服务状态: $(sudo systemctl is-enabled ${SERVICE_NAME})"
echo ""
echo "常用命令:"
echo "  启动服务: sudo systemctl start ${SERVICE_NAME}"
echo "  停止服务: sudo systemctl stop ${SERVICE_NAME}"
echo "  重启服务: sudo systemctl restart ${SERVICE_NAME}"
echo "  查看状态: sudo systemctl status ${SERVICE_NAME}"
echo "  查看日志: sudo journalctl -u ${SERVICE_NAME} -f"
echo "  禁用自启: sudo systemctl disable ${SERVICE_NAME}"
echo ""
echo "💡 提示："
echo "  - 应用默认运行在端口 5000"
echo "  - 如需配置 NGINX 反向代理和 HTTPS，请运行 auto_deploy.sh"
echo "  - NGINX 配置将自动处理 SSL 证书申请和更新"
echo "  - 配置完成后可通过域名访问应用，无需指定端口"