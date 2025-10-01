import asyncio
import time
import requests
from typing import Optional, Dict, Any
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

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
        """初始化交易器"""
        if UMFutures is None:
            log("ERROR", "Binance library not found. Please install python-binance")
            self.client = None
            return
        
        try:
            # 初始化Binance客户端，使用基本配置
            self.client = UMFutures(
                api_key=config.API_KEY, 
                api_secret=config.API_SECRET,
                requests_params={
                    'timeout': 30  # 请求超时时间
                }
            )
            
            # 尝试备用API端点（如果主端点连接失败）
            self._try_alternative_endpoints()
            
            self._setup_dual_side_position()
            log("INFO", "Binance futures client initialized successfully with optimized network settings")
        except Exception as e:
            log("ERROR", f"Failed to initialize Binance client: {str(e)}")
            self.client = None
        
        # 添加持仓状态缓存，用于避免重复日志
        self._last_positions_hash = None
        self._last_log_time = 0
        self._log_interval = 60  # 最少60秒才记录一次详细日志

    def _try_alternative_endpoints(self):
        """尝试备用API端点"""
        try:
            # 测试连接到主API端点
            response = requests.get("https://fapi.binance.com/fapi/v1/ping", timeout=10)
            if response.status_code == 200:
                log("INFO", "主API端点连接正常")
                return
        except Exception as e:
            log("WARNING", f"主API端点连接失败: {e}")
        
        # 如果主端点失败，尝试备用端点
        alternative_endpoints = [
            "https://fapi1.binance.com",
            "https://fapi2.binance.com", 
            "https://fapi3.binance.com"
        ]
        
        for endpoint in alternative_endpoints:
            try:
                response = requests.get(f"{endpoint}/fapi/v1/ping", timeout=10)
                if response.status_code == 200:
                    log("INFO", f"备用API端点 {endpoint} 连接成功")
                    # 更新客户端的base_url（如果支持的话）
                    if hasattr(self.client, 'API_URL'):
                        self.client.API_URL = endpoint
                    return
            except Exception as e:
                log("WARNING", f"备用API端点 {endpoint} 连接失败: {e}")
                continue
        
        log("ERROR", "所有API端点连接失败，网络可能存在问题")

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
        """获取账户余额，带重试机制"""
        if self.client is None:
            log("ERROR", "Binance client not initialized")
            return 0.0
        
        max_retries = 3
        retry_delay = 2  # 秒
        
        for attempt in range(max_retries):
            try:
                if attempt > 0:
                    log("INFO", f"重试获取余额信息 (第 {attempt + 1} 次尝试)...")
                
                # 使用futures_account()方法获取账户信息，包含可用余额
                account_info = self.client.futures_account()
                if account_info is None:
                    log("ERROR", "Failed to get account info: futures_account() returned None")
                    if attempt < max_retries - 1:
                        time.sleep(retry_delay)
                        continue
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
                
            except requests.exceptions.Timeout as e:
                log("ERROR", f"获取余额网络超时 (尝试 {attempt + 1}/{max_retries}): {str(e)}")
                if attempt < max_retries - 1:
                    time.sleep(retry_delay * (attempt + 1))
                    continue
            except requests.exceptions.ConnectionError as e:
                log("ERROR", f"获取余额网络连接错误 (尝试 {attempt + 1}/{max_retries}): {str(e)}")
                if attempt < max_retries - 1:
                    time.sleep(retry_delay * (attempt + 1))
                    continue
            except requests.exceptions.SSLError as e:
                log("ERROR", f"获取余额SSL连接错误 (尝试 {attempt + 1}/{max_retries}): {str(e)}")
                if attempt < max_retries - 1:
                    time.sleep(retry_delay * (attempt + 1))
                    continue
            except Exception as e:
                error_msg = str(e)
                if "HTTPSConnectionPool" in error_msg or "timeout" in error_msg.lower():
                    log("ERROR", f"获取余额网络连接问题 (尝试 {attempt + 1}/{max_retries}): {error_msg}")
                    if attempt < max_retries - 1:
                        time.sleep(retry_delay * (attempt + 1))
                        continue
                else:
                    log("ERROR", f"获取余额失败: {error_msg}")
                    break
        
        log("ERROR", f"获取余额失败，已重试 {max_retries} 次")
        return 0.0

    def get_positions(self):
        """获取实际持仓信息，带重试机制"""
        if self.client is None:
            log("ERROR", "Binance client not initialized")
            return []
        
        max_retries = 3
        retry_delay = 2  # 秒
        
        for attempt in range(max_retries):
            try:
                current_time = time.time()
                should_log_details = (current_time - self._last_log_time) > self._log_interval
                
                if should_log_details and attempt == 0:
                    log("INFO", "开始调用 Binance API 获取持仓信息...")
                elif attempt > 0:
                    log("INFO", f"重试获取持仓信息 (第 {attempt + 1} 次尝试)...")
                
                # 尝试方法1：获取所有持仓信息
                positions = self.client.futures_position_information()
                if positions is None:
                    log("ERROR", "futures_position_information() returned None")
                    if attempt < max_retries - 1:
                        time.sleep(retry_delay)
                        continue
                    return []
                
                if should_log_details:
                    log("INFO", f"futures_position_information() 返回了 {len(positions)} 个交易对的持仓信息")
                
                # 如果返回空列表，尝试方法2：指定交易对
                if len(positions) == 0:
                    if should_log_details:
                        log("INFO", f"尝试获取 {config.SYMBOL} 的特定持仓信息...")
                    try:
                        btc_positions = self.client.futures_position_information(symbol=config.SYMBOL)
                        if should_log_details:
                            log("INFO", f"futures_position_information(symbol={config.SYMBOL}) 返回了 {len(btc_positions) if btc_positions else 0} 个持仓")
                        if btc_positions:
                            positions = btc_positions
                    except Exception as e:
                        log("ERROR", f"获取特定交易对持仓失败: {e}")
                        if attempt < max_retries - 1:
                            time.sleep(retry_delay)
                            continue
                
                # 只返回有持仓的交易对
                active_positions = []
                for i, pos in enumerate(positions):
                    position_amt = float(pos.get('positionAmt', 0))
                    symbol = pos.get('symbol', 'Unknown')
                    
                    # 记录所有交易对的持仓情况（用于调试）
                    if should_log_details and i < 10:  # 记录前10个，用于调试
                        log("DEBUG", f"交易对 {symbol}: positionAmt={position_amt}")
                    
                    if position_amt != 0:
                        # 有持仓的情况总是记录，因为这是重要信息
                        log("INFO", f"发现有持仓的交易对: {symbol}, 持仓数量: {position_amt}")
                        active_positions.append(pos)
                
                # 计算当前持仓状态的哈希值，用于检测变化
                positions_hash = hash(str([(pos.get('symbol'), float(pos.get('positionAmt', 0))) for pos in active_positions]))
                
                # 如果持仓状态发生变化或者距离上次详细日志超过间隔时间，记录详细信息
                if positions_hash != self._last_positions_hash or should_log_details:
                    log("INFO", f"共找到 {len(active_positions)} 个有持仓的交易对")
                    self._last_positions_hash = positions_hash
                    self._last_log_time = current_time
                
                return active_positions
                
            except requests.exceptions.Timeout as e:
                log("ERROR", f"网络超时 (尝试 {attempt + 1}/{max_retries}): {str(e)}")
                if attempt < max_retries - 1:
                    time.sleep(retry_delay * (attempt + 1))  # 递增延迟
                    continue
            except requests.exceptions.ConnectionError as e:
                log("ERROR", f"网络连接错误 (尝试 {attempt + 1}/{max_retries}): {str(e)}")
                if attempt < max_retries - 1:
                    time.sleep(retry_delay * (attempt + 1))
                    continue
            except requests.exceptions.SSLError as e:
                log("ERROR", f"SSL连接错误 (尝试 {attempt + 1}/{max_retries}): {str(e)}")
                if attempt < max_retries - 1:
                    time.sleep(retry_delay * (attempt + 1))
                    continue
            except Exception as e:
                error_msg = str(e)
                if "HTTPSConnectionPool" in error_msg or "timeout" in error_msg.lower():
                    log("ERROR", f"网络连接问题 (尝试 {attempt + 1}/{max_retries}): {error_msg}")
                    if attempt < max_retries - 1:
                        time.sleep(retry_delay * (attempt + 1))
                        continue
                else:
                    log("ERROR", f"获取持仓失败: {error_msg}")
                    break
        
        log("ERROR", f"获取持仓信息失败，已重试 {max_retries} 次")
        return []