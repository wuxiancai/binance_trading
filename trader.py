import asyncio
import time
from typing import Optional, Dict, Any

from config import config
from db import add_trade, set_position, get_position, close_position, log

try:
    from binance.client import Client as UMFutures  # type: ignore
except ImportError:
    try:
        from binance.um_futures import UMFutures  # type: ignore
    except ImportError:  # pragma: no cover
        UMFutures = None


class Trader:
    def __init__(self):
        self.client = None
        self.dual_side_position = False  # 是否支持双向持仓
        if UMFutures is not None and config.API_KEY:
            if config.USE_TESTNET:
                # 对于测试网，需要使用不同的初始化方式
                self.client = UMFutures(api_key=config.API_KEY, api_secret=config.API_SECRET, testnet=True)
            else:
                # 对于主网，使用默认初始化
                self.client = UMFutures(api_key=config.API_KEY, api_secret=config.API_SECRET)
            
            # 尝试开启双向持仓模式
            self._setup_dual_side_position()

    def _setup_dual_side_position(self):
        """设置双向持仓模式"""
        if self.client is None:
            return
        
        try:
            # 尝试开启双向持仓模式
            self.client.futures_change_position_mode(dualSidePosition="true")
            self.dual_side_position = True
            log("INFO", "双向持仓模式已开启")
        except Exception as e:
            error_msg = str(e)
            # 如果错误信息包含"No need to change position side"，说明已经是双向持仓模式
            if "No need to change position side" in error_msg or "-4059" in error_msg:
                self.dual_side_position = True
                log("INFO", "账户已是双向持仓模式")
            else:
                self.dual_side_position = False
                log("WARNING", f"无法开启双向持仓模式: {e}，将使用单向持仓模式")

    async def place_order(self, side: str, qty: float, price: Optional[float] = None):
        ts = int(time.time() * 1000)
        symbol = config.SYMBOL

        if self.client is None:
            log("ERROR", "Binance client not initialized")
            return {"error": "Binance client not initialized"}

        # 处理数量精度，BTCUSDT通常是3位小数
        qty = round(qty, 3)
        
        # 确保数量大于最小值
        if qty < 0.001:
            log("WARNING", f"Order quantity {qty} is too small, minimum is 0.001")
            return {"error": "Quantity too small"}

        # 真实交易
        try:
            params: Dict[str, Any] = {
                "symbol": symbol,
                "side": side,
                "type": "MARKET",
                "quantity": qty,
            }
            
            # 只有在双向持仓模式下才添加positionSide参数
            if self.dual_side_position:
                position_side = "LONG" if side == "BUY" else "SHORT"
                params["positionSide"] = position_side
            res = self.client.futures_create_order(**params)
            avg_price = float(res.get("avgPrice", 0)) if isinstance(res, dict) else 0.0
            
            # 如果avgPrice为0，尝试获取当前市场价格
            if avg_price == 0.0 and price is not None:
                avg_price = price
                log("WARNING", f"Order avgPrice is 0, using provided price: {price}")
            elif avg_price == 0.0:
                # 如果没有提供价格，尝试获取当前市场价格
                try:
                    ticker = self.client.futures_symbol_ticker(symbol=symbol)
                    avg_price = float(ticker.get("price", 0))
                    log("WARNING", f"Order avgPrice is 0, using current market price: {avg_price}")
                except Exception as e:
                    log("ERROR", f"Failed to get market price: {e}")
                    avg_price = 0.0
            
            # 计算手续费：交易金额 * 手续费率
            trade_amount = qty * avg_price
            fee = trade_amount * config.FEE_RATE
            add_trade(ts, symbol, side, qty, avg_price, simulate=False, fee=fee)
            if side == "BUY":
                set_position(symbol, "long", qty, avg_price, ts)
            else:
                set_position(symbol, "short", qty, avg_price, ts)
            log("INFO", f"REAL ORDER {side} {qty} @ {avg_price}")
            return res
        except Exception as e:  # pragma: no cover
            log("ERROR", f"order failed: {e}")
            return {"error": str(e)}

    async def close_all(self, current_price: Optional[float] = None) -> float:
        pos = get_position(config.SYMBOL)
        if not pos:
            return 0.0
        side = pos["side"]
        qty = pos["qty"]
        ts = int(time.time() * 1000)
        symbol = config.SYMBOL
        close_side = "SELL" if side == "long" else "BUY"

        if self.client is None:
            log("ERROR", "Binance client not initialized")
            return 0.0

        # 处理数量精度，BTCUSDT通常是3位小数
        qty = round(qty, 3)
        
        # 确保数量大于最小值
        if qty < 0.001:
            log("WARNING", f"Close quantity {qty} is too small, minimum is 0.001")
            return 0.0

        # 真实平仓
        try:
            params = {
                "symbol": symbol,
                "side": close_side,
                "type": "MARKET",
                "quantity": qty,
            }
            
            # 只有在双向持仓模式下才添加positionSide参数，不使用reduceOnly
            if self.dual_side_position:
                position_side = "LONG" if side == "long" else "SHORT"
                params["positionSide"] = position_side
            else:
                # 单向持仓模式下使用reduceOnly
                params["reduceOnly"] = True
            res = self.client.futures_create_order(**params)
            exit_price = float(res.get("avgPrice", 0))
            
            # 如果avgPrice为0，尝试获取当前市场价格
            if exit_price == 0.0 and current_price is not None:
                exit_price = current_price
                log("WARNING", f"Close avgPrice is 0, using provided current_price: {current_price}")
            elif exit_price == 0.0:
                # 如果没有提供当前价格，尝试获取市场价格
                try:
                    ticker = self.client.futures_symbol_ticker(symbol=symbol)
                    exit_price = float(ticker.get("price", 0))
                    log("WARNING", f"Close avgPrice is 0, using current market price: {exit_price}")
                except Exception as e:
                    log("ERROR", f"Failed to get market price for close: {e}")
                    exit_price = 0.0
            
            pnl = (exit_price - pos["entry_price"]) * qty if side == "long" else (pos["entry_price"] - exit_price) * qty
            # 计算手续费：交易金额 * 手续费率
            trade_amount = qty * exit_price
            fee = trade_amount * config.FEE_RATE
            add_trade(ts, symbol, f"CLOSE_{side.upper()}", qty, exit_price, pnl, simulate=False, fee=fee)
            close_position(symbol)
            log("INFO", f"REAL CLOSE {side} {qty} @ {exit_price}")
            return exit_price
        except Exception as e:  # pragma: no cover
            log("ERROR", f"close failed: {e}")
            return 0.0

    def get_balance(self) -> float:
        if self.client is None:
            log("ERROR", "Binance client not initialized")
            return 0.0
        try:
            # 使用futures_account()方法获取账户信息，包含可用余额
            account_info = self.client.futures_account()
            if account_info is None:
                log("ERROR", "Failed to get account info: futures_account() returned None")
                return 0.0
            
            # 获取各种余额信息
            available_balance = float(account_info.get('availableBalance', 0))
            wallet_balance = float(account_info.get('totalWalletBalance', 0))
            unrealized_pnl = float(account_info.get('totalUnrealizedProfit', 0))
            
            # 详细记录余额信息
            #log("INFO", f"余额详情 - 钱包总余额: {wallet_balance:.2f}, 可用余额: {available_balance:.2f}, 未实现盈亏: {unrealized_pnl:.2f}")
            
            if available_balance <= 0:
                log("WARNING", f"Available balance is {available_balance}, using wallet balance as fallback")
                return wallet_balance
            
            # 使用可用余额进行交易
            #log("INFO", f"使用可用余额进行交易: {available_balance:.2f} USDT")
            return available_balance
        except Exception as e:
            log("ERROR", f"Failed to get balance: {str(e)}")
            return 0.0

    def get_positions(self):
        """获取实际持仓信息"""
        if self.client is None:
            log("ERROR", "Binance client not initialized")
            return []
        
        try:
            positions = self.client.futures_position_information()
            if positions is None:
                log("ERROR", "Failed to get positions: get_position_risk() returned None")
                return []
            
            # 只返回有持仓的交易对
            active_positions = []
            for pos in positions:
                position_amt = float(pos.get('positionAmt', 0))
                if position_amt != 0:
                    active_positions.append(pos)
            return active_positions
        except Exception as e:
            log("ERROR", f"Failed to get positions: {str(e)}")
            return []