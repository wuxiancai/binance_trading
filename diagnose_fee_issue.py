#!/usr/bin/env python3

import sqlite3
import os
import sys

# 添加当前目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    import config
    print("=== 配置检查 ===")
    fee_rate = getattr(config.config, 'FEE_RATE', None)
    if fee_rate is not None:
        print(f"✓ FEE_RATE 配置存在: {fee_rate} ({fee_rate * 100:.3f}%)")
    else:
        print("✗ FEE_RATE 配置不存在")
except Exception as e:
    print(f"✗ 配置检查失败: {e}")

print("\n=== 数据库结构检查 ===")
try:
    conn = sqlite3.connect('data/trading.db')
    cursor = conn.cursor()
    
    # 检查 daily_profits 表结构
    cursor.execute("PRAGMA table_info(daily_profits)")
    daily_profits_columns = [row[1] for row in cursor.fetchall()]
    print(f"daily_profits 表字段: {daily_profits_columns}")
    
    if 'total_fees' in daily_profits_columns:
        print("✓ daily_profits 表包含 total_fees 字段")
    else:
        print("✗ daily_profits 表缺少 total_fees 字段")
    
    # 检查 trades 表结构
    cursor.execute("PRAGMA table_info(trades)")
    trades_columns = [row[1] for row in cursor.fetchall()]
    print(f"trades 表字段: {trades_columns}")
    
    if 'fee' in trades_columns:
        print("✓ trades 表包含 fee 字段")
    else:
        print("✗ trades 表缺少 fee 字段")
    
    conn.close()
except Exception as e:
    print(f"✗ 数据库检查失败: {e}")

print("\n=== WebApp代码检查 ===")
try:
    with open('webapp.py', 'r', encoding='utf-8') as f:
        content = f.read()
        
    # 检查是否包含手续费率配置显示
    if '手续费率:' in content:
        print("✓ webapp.py 包含手续费率配置显示")
    else:
        print("✗ webapp.py 缺少手续费率配置显示")
        
    # 检查是否包含total_fees字段
    if 'total_fees' in content:
        print("✓ webapp.py 包含 total_fees 字段处理")
    else:
        print("✗ webapp.py 缺少 total_fees 字段处理")
        
except Exception as e:
    print(f"✗ WebApp代码检查失败: {e}")

print("\n=== Trader代码检查 ===")
try:
    with open('trader.py', 'r', encoding='utf-8') as f:
        content = f.read()
        
    # 检查是否使用config.FEE_RATE
    if 'config.FEE_RATE' in content:
        print("✓ trader.py 使用 config.FEE_RATE")
    else:
        print("✗ trader.py 未使用 config.FEE_RATE")
        
    # 检查是否还有硬编码的0.0005
    if '0.0005' in content:
        print("⚠ trader.py 仍包含硬编码的 0.0005")
    else:
        print("✓ trader.py 没有硬编码的手续费率")
        
except Exception as e:
    print(f"✗ Trader代码检查失败: {e}")

print("\n诊断完成！")