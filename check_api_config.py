#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
API配置检查脚本
检查Binance API密钥配置和连接状态
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from config import config

def check_api_config():
    """检查API配置"""
    print("=== API配置检查 ===")
    
    # 1. 检查配置文件中的API密钥
    print("\n1. 配置文件中的API密钥:")
    print(f"  API_KEY: {config.API_KEY[:10]}...{config.API_KEY[-10:] if len(config.API_KEY) > 20 else config.API_KEY}")
    print(f"  API_SECRET: {config.API_SECRET[:10]}...{config.API_SECRET[-10:] if len(config.API_SECRET) > 20 else config.API_SECRET}")
    print(f"  USE_TESTNET: {config.USE_TESTNET}")
    
    # 2. 检查环境变量
    print("\n2. 环境变量检查:")
    env_api_key = os.getenv("BINANCE_API_KEY")
    env_api_secret = os.getenv("BINANCE_API_SECRET")
    
    if env_api_key:
        print(f"  环境变量 BINANCE_API_KEY: {env_api_key[:10]}...{env_api_key[-10:] if len(env_api_key) > 20 else env_api_key}")
    else:
        print("  环境变量 BINANCE_API_KEY: 未设置")
    
    if env_api_secret:
        print(f"  环境变量 BINANCE_API_SECRET: {env_api_secret[:10]}...{env_api_secret[-10:] if len(env_api_secret) > 20 else env_api_secret}")
    else:
        print("  环境变量 BINANCE_API_SECRET: 未设置")
    
    # 3. 检查API密钥有效性
    print("\n3. API密钥有效性检查:")
    if not config.API_KEY or config.API_KEY == "":
        print("  ❌ API_KEY 为空")
        return False
    
    if not config.API_SECRET or config.API_SECRET == "":
        print("  ❌ API_SECRET 为空")
        return False
    
    if len(config.API_KEY) < 50:
        print("  ⚠️  API_KEY 长度可能不正确")
    else:
        print("  ✅ API_KEY 长度正常")
    
    if len(config.API_SECRET) < 50:
        print("  ⚠️  API_SECRET 长度可能不正确")
    else:
        print("  ✅ API_SECRET 长度正常")
    
    # 4. 尝试导入和初始化Binance客户端
    print("\n4. Binance客户端初始化测试:")
    try:
        from binance.client import Client as UMFutures
        print("  ✅ 成功导入 binance.client.Client")
    except ImportError:
        try:
            from binance.um_futures import UMFutures
            print("  ✅ 成功导入 binance.um_futures.UMFutures")
        except ImportError:
            print("  ❌ 无法导入Binance库")
            print("  请运行: pip install python-binance")
            return False
    
    # 5. 尝试创建客户端实例
    try:
        if config.USE_TESTNET:
            client = UMFutures(api_key=config.API_KEY, api_secret=config.API_SECRET, testnet=True)
            print("  ✅ 测试网客户端创建成功")
        else:
            client = UMFutures(api_key=config.API_KEY, api_secret=config.API_SECRET)
            print("  ✅ 主网客户端创建成功")
        
        # 6. 测试API连接
        print("\n5. API连接测试:")
        try:
            # 测试服务器时间
            server_time = client.get_server_time()
            print(f"  ✅ 服务器时间获取成功: {server_time}")
            
            # 测试账户信息
            try:
                account_info = client.futures_account()
                print("  ✅ 账户信息获取成功")
                
                # 显示账户基本信息
                total_wallet_balance = float(account_info.get('totalWalletBalance', 0))
                available_balance = float(account_info.get('availableBalance', 0))
                print(f"  钱包总余额: {total_wallet_balance:.2f} USDT")
                print(f"  可用余额: {available_balance:.2f} USDT")
                
                return True
                
            except Exception as e:
                print(f"  ❌ 账户信息获取失败: {e}")
                if "Invalid API-key" in str(e):
                    print("  原因: API密钥无效")
                elif "Signature for this request is not valid" in str(e):
                    print("  原因: API密钥签名无效")
                elif "IP address" in str(e):
                    print("  原因: IP地址未加入白名单")
                else:
                    print("  原因: 未知错误")
                return False
                
        except Exception as e:
            print(f"  ❌ 服务器连接失败: {e}")
            return False
            
    except Exception as e:
        print(f"  ❌ 客户端创建失败: {e}")
        return False

def main():
    success = check_api_config()
    
    print("\n=== 诊断结果 ===")
    if success:
        print("✅ API配置正常，可以正常交易")
    else:
        print("❌ API配置有问题，需要修复")
        print("\n修复建议:")
        print("1. 检查config.py中的API_KEY和API_SECRET是否正确")
        print("2. 确保API密钥有合约交易权限")
        print("3. 检查IP白名单设置")
        print("4. 确认是否使用正确的网络(主网/测试网)")
        print("5. 检查API密钥是否过期")

if __name__ == "__main__":
    main()