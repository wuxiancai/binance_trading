#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
保证金不足问题诊断脚本
检查账户余额、交易参数和风险设置
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from config import config
from trader import Trader
import asyncio

async def diagnose_margin_issue():
    """诊断保证金不足问题"""
    print("=== 保证金不足问题诊断 ===")
    
    # 1. 检查配置参数
    print("\n1. 交易配置参数:")
    print(f"  交易对: {config.SYMBOL}")
    print(f"  杠杆倍数: {config.LEVERAGE}X")
    print(f"  交易比例: {config.TRADE_PERCENT * 100}%")
    print(f"  手续费率: {config.FEE_RATE * 100}%")
    print(f"  是否测试网: {config.USE_TESTNET}")
    print(f"  是否模拟交易: {config.SIMULATE}")
    
    # 2. 检查账户余额
    print("\n2. 账户余额检查:")
    trader = Trader()
    
    if trader.client is None:
        print("  错误: Binance客户端未初始化")
        print("  请检查API密钥配置")
        return
    
    try:
        balance = trader.get_balance()
        print(f"  当前USDT余额: {balance:.2f} USDT")
        
        if balance <= 0:
            print("  ❌ 账户余额不足或为0")
            return
        
        # 3. 获取当前价格
        print("\n3. 当前市场价格:")
        try:
            ticker = trader.client.futures_symbol_ticker(symbol=config.SYMBOL)
            current_price = float(ticker.get("price", 0))
            print(f"  {config.SYMBOL} 当前价格: ${current_price:.2f}")
        except Exception as e:
            print(f"  获取价格失败: {e}")
            current_price = 50000  # 使用默认价格进行计算
            print(f"  使用默认价格进行计算: ${current_price:.2f}")
        
        # 4. 计算交易参数
        print("\n4. 交易参数计算:")
        margin = balance * config.TRADE_PERCENT
        qty = margin * config.LEVERAGE / current_price
        required_margin = qty * current_price / config.LEVERAGE
        
        print(f"  可用于交易的保证金: {margin:.2f} USDT ({config.TRADE_PERCENT * 100}%)")
        print(f"  计算的交易数量: {qty:.6f} {config.SYMBOL.replace('USDT', '')}")
        print(f"  实际所需保证金: {required_margin:.2f} USDT")
        print(f"  名义价值: {qty * current_price:.2f} USDT")
        
        # 5. 风险检查
        print("\n5. 风险检查:")
        if qty < 0.001:
            print("  ❌ 交易数量过小 (最小0.001)")
        else:
            print("  ✅ 交易数量符合要求")
        
        if required_margin > balance:
            print("  ❌ 所需保证金超过账户余额")
        else:
            print("  ✅ 保证金充足")
        
        margin_ratio = required_margin / balance * 100
        print(f"  保证金使用率: {margin_ratio:.1f}%")
        
        if margin_ratio > 80:
            print("  ⚠️  保证金使用率过高，存在强平风险")
        elif margin_ratio > 50:
            print("  ⚠️  保证金使用率较高")
        else:
            print("  ✅ 保证金使用率正常")
        
        # 6. 获取账户信息
        print("\n6. 账户详细信息:")
        try:
            account_info = trader.client.futures_account()
            total_wallet_balance = float(account_info.get('totalWalletBalance', 0))
            available_balance = float(account_info.get('availableBalance', 0))
            total_unrealized_profit = float(account_info.get('totalUnrealizedProfit', 0))
            
            print(f"  钱包总余额: {total_wallet_balance:.2f} USDT")
            print(f"  可用余额: {available_balance:.2f} USDT")
            print(f"  未实现盈亏: {total_unrealized_profit:.2f} USDT")
            
            # 检查是否有持仓
            positions = trader.get_positions()
            if positions:
                print(f"  当前持仓数量: {len(positions)}")
                for pos in positions:
                    symbol = pos.get('symbol', '')
                    position_amt = float(pos.get('positionAmt', 0))
                    unrealized_pnl = float(pos.get('unRealizedProfit', 0))
                    print(f"    {symbol}: 数量={position_amt:.6f}, 未实现盈亏={unrealized_pnl:.2f}")
            else:
                print("  当前无持仓")
                
        except Exception as e:
            print(f"  获取账户信息失败: {e}")
        
        # 7. 建议
        print("\n7. 建议:")
        if balance < 100:
            print("  💡 账户余额较少，建议:")
            print("     - 增加账户资金")
            print("     - 降低交易比例 (TRADE_PERCENT)")
            print("     - 降低杠杆倍数 (LEVERAGE)")
        
        if margin_ratio > 50:
            print("  💡 保证金使用率过高，建议:")
            print("     - 降低交易比例 (TRADE_PERCENT)")
            print("     - 降低杠杆倍数 (LEVERAGE)")
        
        print("  💡 其他建议:")
        print("     - 确保账户有足够的风险缓冲")
        print("     - 定期检查持仓和风险状况")
        print("     - 考虑设置止损和止盈")
        
    except Exception as e:
        print(f"  获取余额失败: {e}")
        print("  可能的原因:")
        print("  - API密钥错误或过期")
        print("  - 网络连接问题")
        print("  - API权限不足")

if __name__ == "__main__":
    asyncio.run(diagnose_margin_issue())