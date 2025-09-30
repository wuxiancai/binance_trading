#!/usr/bin/env python3

import sqlite3
import os
import sys
from datetime import datetime

# 添加当前目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

print("=== 深度诊断：检查实际数据 ===")

try:
    conn = sqlite3.connect('data/trading.db')
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    print("\n1. 检查今日交易记录中的手续费数据:")
    today = datetime.now().date().isoformat()
    cursor.execute("""
        SELECT ts, symbol, side, qty, price, pnl, fee, 
               datetime(ts, 'unixepoch') as trade_time
        FROM trades 
        WHERE date(datetime(ts, 'unixepoch')) = ?
        ORDER BY ts DESC
    """, (today,))
    
    today_trades = cursor.fetchall()
    print(f"今日交易记录数量: {len(today_trades)}")
    
    total_fees_from_trades = 0
    for trade in today_trades:
        fee = trade['fee'] if trade['fee'] is not None else 0
        total_fees_from_trades += fee
        print(f"  交易时间: {trade['trade_time']}, 方向: {trade['side']}, "
              f"数量: {trade['qty']}, 价格: {trade['price']}, "
              f"盈亏: {trade['pnl']}, 手续费: {fee}")
    
    print(f"今日交易记录中手续费总计: {total_fees_from_trades}")
    
    print("\n2. 检查今日盈利统计记录:")
    cursor.execute("""
        SELECT date, trade_count, profit, profit_rate, loss_count, profit_count, total_fees
        FROM daily_profits 
        WHERE date = ?
    """, (today,))
    
    today_profit = cursor.fetchone()
    if today_profit:
        print(f"  日期: {today_profit['date']}")
        print(f"  交易次数: {today_profit['trade_count']}")
        print(f"  总盈利: {today_profit['profit']}")
        print(f"  利润率: {today_profit['profit_rate']}")
        print(f"  亏损次数: {today_profit['loss_count']}")
        print(f"  盈利次数: {today_profit['profit_count']}")
        print(f"  总手续费: {today_profit['total_fees']}")
    else:
        print("  今日没有盈利统计记录")
    
    print("\n3. 检查所有交易记录的手续费字段:")
    cursor.execute("SELECT COUNT(*) as total, COUNT(fee) as with_fee, SUM(fee) as total_fees FROM trades")
    fee_stats = cursor.fetchone()
    print(f"  总交易记录: {fee_stats['total']}")
    print(f"  有手续费数据的记录: {fee_stats['with_fee']}")
    print(f"  所有手续费总计: {fee_stats['total_fees']}")
    
    print("\n4. 检查最近5条交易记录的详细信息:")
    cursor.execute("""
        SELECT ts, symbol, side, qty, price, pnl, fee, simulate,
               datetime(ts, 'unixepoch') as trade_time
        FROM trades 
        ORDER BY ts DESC 
        LIMIT 5
    """)
    
    recent_trades = cursor.fetchall()
    for i, trade in enumerate(recent_trades, 1):
        print(f"  交易{i}: 时间={trade['trade_time']}, 方向={trade['side']}, "
              f"数量={trade['qty']}, 价格={trade['price']}, 盈亏={trade['pnl']}, "
              f"手续费={trade['fee']}, 模拟={trade['simulate']}")
    
    print("\n5. 检查所有盈利统计记录:")
    cursor.execute("""
        SELECT date, trade_count, profit, total_fees
        FROM daily_profits 
        ORDER BY date DESC 
        LIMIT 10
    """)
    
    profit_records = cursor.fetchall()
    print(f"  最近10天的盈利记录:")
    for record in profit_records:
        print(f"    {record['date']}: 交易{record['trade_count']}次, "
              f"盈利{record['profit']}, 手续费{record['total_fees']}")
    
    print("\n6. 检查NULL值情况:")
    cursor.execute("SELECT COUNT(*) FROM trades WHERE fee IS NULL")
    null_fee_count = cursor.fetchone()[0]
    print(f"  手续费为NULL的交易记录: {null_fee_count}")
    
    cursor.execute("SELECT COUNT(*) FROM daily_profits WHERE total_fees IS NULL")
    null_total_fees_count = cursor.fetchone()[0]
    print(f"  总手续费为NULL的盈利记录: {null_total_fees_count}")
    
    conn.close()
    
except Exception as e:
    print(f"✗ 深度诊断失败: {e}")
    import traceback
    traceback.print_exc()

print("\n=== 深度诊断完成 ===")