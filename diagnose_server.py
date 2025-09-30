#!/usr/bin/env python3
"""
云服务器诊断脚本 - 用于排查"加载中..."问题
"""

import sys
import subprocess
import requests
import time
import json
from datetime import datetime

def print_section(title):
    print(f"\n{'='*50}")
    print(f" {title}")
    print(f"{'='*50}")

def check_network():
    """检查网络连接"""
    print_section("网络连接检查")
    
    # 检查基本网络
    try:
        result = subprocess.run(['ping', '-c', '3', '8.8.8.8'], 
                              capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            print("✅ 基本网络连接正常")
        else:
            print("❌ 基本网络连接异常")
            print(result.stderr)
    except Exception as e:
        print(f"❌ 网络检查失败: {e}")
    
    # 检查币安API连接
    apis_to_test = [
        "https://api.binance.com/api/v3/ping",
        "https://fapi.binance.com/fapi/v1/ping",
        "https://testnet.binancefuture.com/fapi/v1/ping"
    ]
    
    for api in apis_to_test:
        try:
            response = requests.get(api, timeout=10)
            if response.status_code == 200:
                print(f"✅ {api} - 连接正常")
            else:
                print(f"❌ {api} - 状态码: {response.status_code}")
        except requests.exceptions.Timeout:
            print(f"❌ {api} - 连接超时")
        except requests.exceptions.ConnectionError:
            print(f"❌ {api} - 连接错误")
        except Exception as e:
            print(f"❌ {api} - 错误: {e}")

def check_python_env():
    """检查Python环境"""
    print_section("Python环境检查")
    
    print(f"Python版本: {sys.version}")
    
    # 检查关键库
    required_packages = [
        'binance', 'websockets', 'pandas', 'numpy', 'flask', 'psutil'
    ]
    
    for package in required_packages:
        try:
            __import__(package)
            print(f"✅ {package} - 已安装")
        except ImportError:
            print(f"❌ {package} - 未安装")

def check_binance_import():
    """检查binance库导入"""
    print_section("Binance库导入检查")
    
    try:
        from binance.client import Client
        print("✅ binance.client.Client 导入成功")
        
        # 测试创建客户端
        client = Client()
        print("✅ Client实例创建成功")
        
        # 测试公共API
        try:
            ticker = client.get_symbol_ticker(symbol="BTCUSDT")
            print(f"✅ 公共API测试成功，BTCUSDT价格: {ticker['price']}")
        except Exception as e:
            print(f"❌ 公共API测试失败: {e}")
            
    except ImportError as e:
        print(f"❌ binance.client.Client 导入失败: {e}")
        
        # 尝试旧版本导入
        try:
            from binance.um_futures import UMFutures
            print("✅ binance.um_futures.UMFutures 导入成功")
        except ImportError as e2:
            print(f"❌ binance.um_futures.UMFutures 导入失败: {e2}")

def check_webapp_status():
    """检查webapp状态"""
    print_section("WebApp状态检查")
    
    # 检查进程
    try:
        result = subprocess.run(['ps', 'aux'], capture_output=True, text=True)
        if 'webapp.py' in result.stdout:
            print("✅ webapp.py 进程正在运行")
            # 提取进程信息
            lines = result.stdout.split('\n')
            for line in lines:
                if 'webapp.py' in line and 'grep' not in line:
                    print(f"   进程信息: {line}")
        else:
            print("❌ webapp.py 进程未运行")
    except Exception as e:
        print(f"❌ 进程检查失败: {e}")
    
    # 检查端口
    try:
        result = subprocess.run(['netstat', '-tlnp'], capture_output=True, text=True)
        if ':5000' in result.stdout:
            print("✅ 端口5000正在监听")
        else:
            print("❌ 端口5000未监听")
    except Exception as e:
        print(f"❌ 端口检查失败: {e}")

def check_api_endpoints():
    """检查API端点"""
    print_section("API端点检查")
    
    base_url = "http://localhost:5000"
    endpoints = [
        "/api/price_and_boll",
        "/api/balance", 
        "/api/positions",
        "/api/system"
    ]
    
    for endpoint in endpoints:
        try:
            response = requests.get(f"{base_url}{endpoint}", timeout=5)
            if response.status_code == 200:
                data = response.json()
                print(f"✅ {endpoint} - 正常响应")
                if endpoint == "/api/price_and_boll":
                    price = data.get('price', 0)
                    if price > 0:
                        print(f"   价格: {price}")
                    else:
                        print("   ⚠️  价格为0，可能存在问题")
            else:
                print(f"❌ {endpoint} - 状态码: {response.status_code}")
        except requests.exceptions.ConnectionError:
            print(f"❌ {endpoint} - 连接失败")
        except Exception as e:
            print(f"❌ {endpoint} - 错误: {e}")

def check_logs():
    """检查日志文件"""
    print_section("日志文件检查")
    
    log_files = [
        "debug_output.txt",
        "webapp.log",
        "error.log"
    ]
    
    for log_file in log_files:
        try:
            with open(log_file, 'r') as f:
                lines = f.readlines()
                if lines:
                    print(f"✅ {log_file} - 最后10行:")
                    for line in lines[-10:]:
                        print(f"   {line.strip()}")
                else:
                    print(f"⚠️  {log_file} - 文件为空")
        except FileNotFoundError:
            print(f"⚠️  {log_file} - 文件不存在")
        except Exception as e:
            print(f"❌ {log_file} - 读取失败: {e}")

def main():
    print(f"云服务器诊断开始 - {datetime.now()}")
    
    check_network()
    check_python_env()
    check_binance_import()
    check_webapp_status()
    check_api_endpoints()
    check_logs()
    
    print_section("诊断完成")
    print("请将以上输出发送给技术支持以获得进一步帮助")

if __name__ == "__main__":
    main()