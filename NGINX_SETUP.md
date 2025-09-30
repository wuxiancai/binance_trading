# NGINX 反向代理和 HTTPS 配置指南

本项目新增了自动配置 NGINX 反向代理和 HTTPS 的功能，让您可以通过域名安全地访问币安自动交易系统。

## 功能特性

- ✅ **智能安装检查**：自动检查 NGINX 和 Certbot 是否已安装，避免重复安装
- ✅ **自动 NGINX 安装和配置**：支持 Ubuntu、CentOS、Fedora 系统
- ✅ **反向代理配置**：将端口 5000 的应用代理到 80/443 端口
- ✅ **自动 SSL 证书**：使用 Let's Encrypt 免费 SSL 证书
- ✅ **证书自动更新**：设置 cron 任务自动更新证书
- ✅ **安全配置**：包含现代化的 SSL 安全配置和安全头
- ✅ **用户交互确认**：部署时可选择是否启用反向代理

## 使用方法

### 1. 基本部署

运行部署脚本：

```bash
bash auto_deploy.sh
```

在部署过程中，系统会询问是否配置 NGINX 反向代理：

```
=== NGINX 反向代理配置 ===
是否要配置 NGINX 反向代理和 HTTPS？(y/N): y
请输入您的域名 (例如: example.com): your-domain.com
请输入您的邮箱地址 (用于 SSL 证书): your-email@example.com
```

### 2. 手动配置 NGINX

如果您已经完成了基本部署，也可以单独运行 NGINX 配置：

```bash
bash setup_nginx.sh your-domain.com your-email@example.com
```

## 配置前准备

### 1. 域名解析

确保您的域名已正确解析到服务器的公网 IP：

```bash
# 检查域名解析
nslookup your-domain.com
```

### 2. 防火墙设置

确保服务器防火墙已开放必要端口：

```bash
# Ubuntu/Debian (ufw)
sudo ufw allow 80
sudo ufw allow 443

# CentOS/RHEL/Fedora (firewalld)
sudo firewall-cmd --permanent --add-service=http
sudo firewall-cmd --permanent --add-service=https
sudo firewall-cmd --reload
```

### 3. 服务器要求

- 操作系统：Ubuntu 18.04+、CentOS 7+、Fedora 30+
- 权限：具有 sudo 权限的非 root 用户
- 网络：服务器具有公网 IP 和域名解析

## 配置详情

### 智能安装检查

配置脚本会在安装前自动检查软件是否已存在：

1. **NGINX 检查**：使用 `command -v nginx` 检查是否已安装
2. **版本显示**：显示已安装的 NGINX 和 Certbot 版本信息
3. **跳过重复安装**：如果软件已安装，自动跳过安装步骤
4. **安装验证**：安装完成后验证软件是否正确安装

### NGINX 配置特性

1. **HTTP 到 HTTPS 重定向**：自动将 HTTP 请求重定向到 HTTPS
2. **反向代理**：将外部请求代理到内部端口 5000
3. **WebSocket 支持**：支持实时数据传输
4. **静态文件缓存**：优化静态资源加载
5. **安全头配置**：包含 HSTS、XSS 保护等安全头

### SSL 证书管理

1. **自动申请**：使用 Certbot 自动申请 Let's Encrypt 证书
2. **自动更新**：设置 cron 任务每天检查证书更新
3. **多域名支持**：同时支持 `example.com` 和 `www.example.com`

### 目录结构

配置完成后，相关文件位置：

```
/etc/nginx/sites-available/your-domain.com    # NGINX 配置文件
/etc/letsencrypt/live/your-domain.com/        # SSL 证书文件
/usr/local/bin/renew-ssl-binance_auto_trading.sh  # 证书更新脚本
/var/log/ssl-renewal.log                      # 证书更新日志
```

## 常用命令

### NGINX 管理

```bash
# 查看 NGINX 状态
sudo systemctl status nginx

# 重启 NGINX
sudo systemctl restart nginx

# 重新加载配置
sudo systemctl reload nginx

# 测试配置文件
sudo nginx -t

# 查看访问日志
sudo tail -f /var/log/nginx/access.log

# 查看错误日志
sudo tail -f /var/log/nginx/error.log
```

### SSL 证书管理

```bash
# 查看证书信息
sudo certbot certificates

# 手动更新证书
sudo certbot renew

# 测试证书更新
sudo certbot renew --dry-run

# 查看证书更新日志
sudo tail -f /var/log/ssl-renewal.log
```

### 应用服务管理

```bash
# 查看应用状态
sudo systemctl status binance_auto_trading

# 重启应用
sudo systemctl restart binance_auto_trading

# 查看应用日志
sudo journalctl -u binance_auto_trading -f
```

## 故障排除

### 1. 域名解析问题

**问题**：SSL 证书申请失败，提示域名无法访问

**解决方案**：
- 检查域名 DNS 解析是否正确指向服务器 IP
- 确保防火墙已开放 80 和 443 端口
- 等待 DNS 解析生效（可能需要几分钟到几小时）

### 2. 证书申请失败

**问题**：Let's Encrypt 证书申请失败

**解决方案**：
```bash
# 检查 NGINX 配置
sudo nginx -t

# 确保 NGINX 正在运行
sudo systemctl status nginx

# 手动申请证书（调试模式）
sudo certbot certonly --nginx --dry-run -d your-domain.com
```

### 3. 反向代理不工作

**问题**：通过域名无法访问应用

**解决方案**：
```bash
# 检查应用是否在端口 5000 运行
sudo netstat -tlnp | grep 5000

# 检查应用服务状态
sudo systemctl status binance_auto_trading

# 检查 NGINX 配置
sudo nginx -t

# 查看 NGINX 错误日志
sudo tail -f /var/log/nginx/error.log
```

### 4. SSL 证书自动更新失败

**问题**：证书过期或自动更新失败

**解决方案**：
```bash
# 检查 cron 任务
sudo crontab -l

# 手动测试更新
sudo /usr/local/bin/renew-ssl-binance_auto_trading.sh

# 查看更新日志
sudo tail -f /var/log/ssl-renewal.log
```

## 安全建议

1. **定期更新**：保持系统和软件包更新
2. **防火墙配置**：只开放必要的端口
3. **SSL 配置**：使用现代化的 SSL 配置
4. **日志监控**：定期检查访问和错误日志
5. **备份配置**：定期备份 NGINX 配置文件

## 支持的系统

- Ubuntu 18.04 LTS 及以上
- Debian 9 及以上
- CentOS 7 及以上
- RHEL 7 及以上
- Fedora 30 及以上

## 注意事项

1. **域名要求**：必须拥有有效的域名并正确解析到服务器
2. **权限要求**：需要 sudo 权限来安装软件包和配置系统服务
3. **网络要求**：服务器需要能够访问互联网以下载软件包和申请证书
4. **端口要求**：确保 80 和 443 端口未被其他服务占用

配置完成后，您就可以通过 `https://your-domain.com` 安全地访问您的币安自动交易系统了！