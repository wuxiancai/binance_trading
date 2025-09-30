#!/bin/bash
# NGINX 反向代理和 HTTPS 自动配置脚本
# 用于配置币安交易系统的 NGINX 反向代理和 SSL 证书

set -e  # 遇到错误立即退出

# 参数检查
if [ $# -ne 2 ]; then
    echo "用法: $0 <域名> <邮箱地址>"
    echo "示例: $0 example.com admin@example.com"
    exit 1
fi

DOMAIN_NAME="$1"
EMAIL_ADDRESS="$2"
PROJECT_NAME="binance_trading"
APP_PORT="5000"

echo "=== NGINX 反向代理和 HTTPS 配置 ==="
echo "域名: $DOMAIN_NAME"
echo "邮箱: $EMAIL_ADDRESS"
echo "应用端口: $APP_PORT"
echo ""

# 检测系统类型
detect_system() {
    if command -v apt >/dev/null 2>&1; then
        echo "ubuntu"
    elif command -v yum >/dev/null 2>&1; then
        echo "centos"
    elif command -v dnf >/dev/null 2>&1; then
        echo "fedora"
    else
        echo "unknown"
    fi
}

# 安装 NGINX
install_nginx() {
    echo "[1/6] 检查并安装 NGINX..."
    
    # 检查 NGINX 是否已安装
    if command -v nginx >/dev/null 2>&1; then
        local nginx_version=$(nginx -v 2>&1 | grep -o 'nginx/[0-9.]*' | cut -d'/' -f2)
        echo "✅ NGINX 已安装 (版本: $nginx_version)，跳过安装步骤"
        return 0
    fi
    
    echo "NGINX 未安装，正在安装..."
    local system_type=$(detect_system)
    
    case $system_type in
        "ubuntu")
            sudo apt update
            sudo apt install -y nginx
            ;;
        "centos")
            sudo yum install -y epel-release
            sudo yum install -y nginx
            ;;
        "fedora")
            sudo dnf install -y nginx
            ;;
        *)
            echo "❌ 不支持的系统类型，请手动安装 NGINX"
            exit 1
            ;;
    esac
    
    # 验证安装是否成功
    if command -v nginx >/dev/null 2>&1; then
        local nginx_version=$(nginx -v 2>&1 | grep -o 'nginx/[0-9.]*' | cut -d'/' -f2)
        echo "✅ NGINX 安装完成 (版本: $nginx_version)"
    else
        echo "❌ NGINX 安装失败，请检查系统配置"
        exit 1
    fi
}

# 安装 Certbot
install_certbot() {
    echo "[2/6] 检查并安装 Certbot..."
    
    # 检查 Certbot 是否已安装
    if command -v certbot >/dev/null 2>&1; then
        local certbot_version=$(certbot --version 2>&1 | grep -o 'certbot [0-9.]*' | cut -d' ' -f2)
        echo "✅ Certbot 已安装 (版本: $certbot_version)，跳过安装步骤"
        return 0
    fi
    
    echo "Certbot 未安装，正在安装..."
    local system_type=$(detect_system)
    
    case $system_type in
        "ubuntu")
            sudo apt install -y certbot python3-certbot-nginx
            ;;
        "centos")
            sudo yum install -y certbot python3-certbot-nginx
            ;;
        "fedora")
            sudo dnf install -y certbot python3-certbot-nginx
            ;;
        *)
            echo "❌ 不支持的系统类型，请手动安装 Certbot"
            exit 1
            ;;
    esac
    
    # 验证安装是否成功
    if command -v certbot >/dev/null 2>&1; then
        local certbot_version=$(certbot --version 2>&1 | grep -o 'certbot [0-9.]*' | cut -d' ' -f2)
        echo "✅ Certbot 安装完成 (版本: $certbot_version)"
    else
        echo "❌ Certbot 安装失败，请检查系统配置"
        exit 1
    fi
}

# 创建 NGINX 配置文件
create_nginx_config() {
    echo "[3/6] 创建 NGINX 配置文件..."
    
    # 创建临时的 HTTP 配置（用于 SSL 证书验证）
    sudo tee "/etc/nginx/sites-available/$DOMAIN_NAME" > /dev/null << EOF
server {
    listen 80;
    server_name $DOMAIN_NAME www.$DOMAIN_NAME;
    
    # 用于 Let's Encrypt 验证
    location /.well-known/acme-challenge/ {
        root /var/www/html;
    }
    
    # 其他请求重定向到 HTTPS
    location / {
        return 301 https://\$server_name\$request_uri;
    }
}
EOF

    # 启用站点配置
    if [ -d "/etc/nginx/sites-enabled" ]; then
        sudo ln -sf "/etc/nginx/sites-available/$DOMAIN_NAME" "/etc/nginx/sites-enabled/"
    fi
    
    echo "✅ NGINX 配置文件创建完成"
}

# 启动 NGINX 服务
start_nginx() {
    echo "[4/6] 启动 NGINX 服务..."
    
    # 测试配置文件
    sudo nginx -t
    
    # 启动并启用 NGINX
    sudo systemctl start nginx
    sudo systemctl enable nginx
    
    # 检查防火墙设置
    if command -v ufw >/dev/null 2>&1; then
        sudo ufw allow 'Nginx Full' 2>/dev/null || true
    elif command -v firewall-cmd >/dev/null 2>&1; then
        sudo firewall-cmd --permanent --add-service=http 2>/dev/null || true
        sudo firewall-cmd --permanent --add-service=https 2>/dev/null || true
        sudo firewall-cmd --reload 2>/dev/null || true
    fi
    
    echo "✅ NGINX 服务启动完成"
}

# 申请 SSL 证书
obtain_ssl_certificate() {
    echo "[5/6] 申请 SSL 证书..."
    
    # 使用 Certbot 申请证书
    sudo certbot certonly \
        --nginx \
        --non-interactive \
        --agree-tos \
        --email "$EMAIL_ADDRESS" \
        --domains "$DOMAIN_NAME,www.$DOMAIN_NAME"
    
    echo "✅ SSL 证书申请完成"
}

# 创建完整的 NGINX 配置（包含 HTTPS）
create_full_nginx_config() {
    echo "[6/6] 创建完整的 NGINX 配置..."
    
    sudo tee "/etc/nginx/sites-available/$DOMAIN_NAME" > /dev/null << EOF
# HTTP 重定向到 HTTPS
server {
    listen 80;
    server_name $DOMAIN_NAME www.$DOMAIN_NAME;
    
    # 用于 Let's Encrypt 验证
    location /.well-known/acme-challenge/ {
        root /var/www/html;
    }
    
    # 其他请求重定向到 HTTPS
    location / {
        return 301 https://\$server_name\$request_uri;
    }
}

# HTTPS 配置
server {
    listen 443 ssl http2;
    server_name $DOMAIN_NAME www.$DOMAIN_NAME;
    
    # SSL 证书配置
    ssl_certificate /etc/letsencrypt/live/$DOMAIN_NAME/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/$DOMAIN_NAME/privkey.pem;
    
    # SSL 安全配置
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers ECDHE-RSA-AES128-GCM-SHA256:ECDHE-RSA-AES256-GCM-SHA384:ECDHE-RSA-AES128-SHA256:ECDHE-RSA-AES256-SHA384;
    ssl_prefer_server_ciphers on;
    ssl_session_cache shared:SSL:10m;
    ssl_session_timeout 10m;
    
    # 安全头
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
    add_header X-Frame-Options DENY always;
    add_header X-Content-Type-Options nosniff always;
    add_header X-XSS-Protection "1; mode=block" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;
    
    # 反向代理到应用
    location / {
        proxy_pass http://127.0.0.1:$APP_PORT;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_set_header X-Forwarded-Host \$host;
        proxy_set_header X-Forwarded-Port \$server_port;
        
        # WebSocket 支持
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
        
        # 超时设置
        proxy_connect_timeout 60s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;
        
        # 缓冲设置
        proxy_buffering on;
        proxy_buffer_size 4k;
        proxy_buffers 8 4k;
    }
    
    # 静态文件缓存
    location ~* \.(css|js|png|jpg|jpeg|gif|ico|svg|woff|woff2|ttf|eot)$ {
        proxy_pass http://127.0.0.1:$APP_PORT;
        proxy_set_header Host \$host;
        expires 1y;
        add_header Cache-Control "public, immutable";
    }
    
    # 健康检查
    location /health {
        proxy_pass http://127.0.0.1:$APP_PORT/health;
        proxy_set_header Host \$host;
        access_log off;
    }
}
EOF

    # 重新加载 NGINX 配置
    sudo nginx -t
    sudo systemctl reload nginx
    
    echo "✅ 完整的 NGINX 配置创建完成"
}

# 设置 SSL 证书自动更新
setup_ssl_auto_renewal() {
    echo "设置 SSL 证书自动更新..."
    
    # 创建更新脚本
    sudo tee "/usr/local/bin/renew-ssl-$PROJECT_NAME.sh" > /dev/null << 'EOF'
#!/bin/bash
# SSL 证书自动更新脚本

# 更新证书
/usr/bin/certbot renew --quiet

# 重新加载 NGINX
/bin/systemctl reload nginx

# 记录日志
echo "$(date): SSL certificate renewal completed" >> /var/log/ssl-renewal.log
EOF

    sudo chmod +x "/usr/local/bin/renew-ssl-$PROJECT_NAME.sh"
    
    # 添加到 crontab（每天检查一次）
    (sudo crontab -l 2>/dev/null; echo "0 2 * * * /usr/local/bin/renew-ssl-$PROJECT_NAME.sh") | sudo crontab -
    
    echo "✅ SSL 证书自动更新设置完成"
}

# 主执行流程
main() {
    echo "开始配置 NGINX 反向代理和 HTTPS..."
    
    # 检查是否以 root 权限运行
    if [ "$EUID" -eq 0 ]; then
        echo "❌ 请不要以 root 用户运行此脚本"
        exit 1
    fi
    
    # 检查域名解析
    echo "检查域名解析..."
    if ! nslookup "$DOMAIN_NAME" >/dev/null 2>&1; then
        echo "⚠️  警告: 域名 $DOMAIN_NAME 可能未正确解析到此服务器"
        read -p "是否继续配置？(y/N): " continue_setup
        if [[ ! "$continue_setup" =~ ^[Yy]$ ]]; then
            echo "配置已取消"
            exit 0
        fi
    fi
    
    # 执行配置步骤
    install_nginx
    install_certbot
    create_nginx_config
    start_nginx
    
    echo ""
    echo "⚠️  重要提示："
    echo "1. 请确保域名 $DOMAIN_NAME 已正确解析到此服务器的公网IP"
    echo "2. 请确保防火墙已开放 80 和 443 端口"
    echo "3. 即将申请 SSL 证书，这需要域名能够正常访问"
    echo ""
    read -p "确认域名解析正确后，按回车键继续申请 SSL 证书..."
    
    obtain_ssl_certificate
    create_full_nginx_config
    setup_ssl_auto_renewal
    
    echo ""
    echo "🎉 NGINX 反向代理和 HTTPS 配置完成！"
    echo ""
    echo "配置信息："
    echo "  域名: https://$DOMAIN_NAME"
    echo "  应用端口: $APP_PORT (内部)"
    echo "  SSL 证书: Let's Encrypt"
    echo "  自动更新: 已启用"
    echo ""
    echo "常用命令："
    echo "  查看 NGINX 状态: sudo systemctl status nginx"
    echo "  重新加载配置: sudo systemctl reload nginx"
    echo "  查看 SSL 证书: sudo certbot certificates"
    echo "  手动更新证书: sudo certbot renew"
    echo "  查看 NGINX 日志: sudo tail -f /var/log/nginx/access.log"
    echo ""
    echo "现在您可以通过 https://$DOMAIN_NAME 访问您的应用了！"
}

# 执行主函数
main "$@"