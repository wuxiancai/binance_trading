import asyncio
import json
import time
from typing import Deque, Dict, Any, List, Tuple
from collections import deque

import pandas as pd
import websockets

from config import config
from db import init_db, latest_kline_time, insert_kline, fetch_klines, log, get_position, get_daily_profit, update_daily_profit, close_position
from indicators import bollinger_bands, calculate_boll_binance_compatible, calculate_boll_dynamic
from trader import Trader
from datetime import datetime

KLINE_WS_URL = "wss://fstream.binance.com/ws"  # futures stream

try:
    from binance.client import Client as UMFutures  # type: ignore
except ImportError:
    try:
        from binance.um_futures import UMFutures  # type: ignore
    except ImportError:  # pragma: no cover
        UMFutures = None  # type: ignore


class Engine:
    def __init__(self, socketio=None):
        init_db()
        self.trader = Trader()
        self.initial_balance = self.trader.get_balance()
        
        # 同步数据库持仓记录与 API 实际持仓
        pos = self._sync_position_with_api()
        
        self.initial_capital = self.initial_balance
        self.socketio = socketio  # 添加socketio支持
        
        # 新的状态机枚举
        # 等待开仓状态
        self.STATE_WAITING = "waiting"  # 等待开仓
        
        # 开空相关状态
        self.STATE_BREAKOUT_UP_WAIT_FALL = "breakout_up_wait_fall"  # 突破UP，等待跌破UP
        self.STATE_HOLDING_SHORT = "holding_short"  # 持仓SHORT
        self.STATE_SHORT_STOP_LOSS_WAIT_FALL = "short_stop_loss_wait_fall"  # 已止损SHORT，等待跌破UP
        self.STATE_SHORT_BELOW_MID_WAIT = "short_below_mid_wait"  # 跌破中轨，等待突破中轨或跌破DN
        self.STATE_SHORT_WAIT_PROFIT = "short_wait_profit"  # 等待止盈SHORT（收盘价跌破DN后等待实时价格>DN）
        self.STATE_SHORT_PROFIT_TAKEN = "short_profit_taken"  # 已止盈SHORT，等待开仓
        
        # 开多相关状态  
        self.STATE_BREAKDOWN_DN_WAIT_BOUNCE = "breakdown_dn_wait_bounce"  # 跌破DN，等待反弹到DN
        self.STATE_HOLDING_LONG = "holding_long"  # 持仓LONG
        self.STATE_LONG_STOP_LOSS_WAIT_BOUNCE = "long_stop_loss_wait_bounce"  # 已止损LONG，等待收盘价>DN
        self.STATE_LONG_ABOVE_MID_WAIT = "long_above_mid_wait"  # 突破中轨，等待突破UP或跌破中轨
        self.STATE_LONG_WAIT_PROFIT = "long_wait_profit"  # 等待止盈LONG（收盘价突破UP后等待实时价格<UP）
        self.STATE_LONG_PROFIT_TAKEN = "long_profit_taken"  # 已止盈LONG，等待开仓
        
        # 初始化状态
        self.state = self.STATE_WAITING
        
        self.prices: Deque[float] = deque(maxlen=1000)
        self.last_price: float = 0.0
        # 评估频率节流（用于未收盘K线内的即时评估）
        self._last_eval_ts: float = 0.0
        # self.socketio 已在构造函数中设置，不要在这里重置
        self.last_trade_time = 0  # 上次交易时间戳
        self.trade_cooldown = 60000  # 交易冷却时间60秒(毫秒)
        self.last_action_price = 0  # 上次动作价格
        self.price_threshold = 0.001  # 价格变化阈值(0.1%)
        
        # 用于跟踪状态变化，避免重复日志
        self._last_logged_state = None

        # 根据现有持仓恢复状态
        if pos and pos.get("side") == "long":
            self.state = self.STATE_HOLDING_LONG
            log("INFO", f"恢复状态为 {self.state}（检测到多仓持仓）")
        elif pos and pos.get("side") == "short":
            self.state = self.STATE_HOLDING_SHORT
            log("INFO", f"恢复状态为 {self.state}（检测到空仓持仓）")
    
    def _sync_position_with_api(self):
        """
        同步数据库持仓记录与 API 实际持仓
        返回同步后的持仓信息
        """
        # 获取数据库中的持仓记录
        db_position = get_position(config.SYMBOL)
        
        # 获取 API 中的实际持仓
        api_positions = self.trader.get_positions()
        api_position = None
        for pos in api_positions:
            if pos.get('symbol') == config.SYMBOL and float(pos.get('positionAmt', 0)) != 0:
                api_position = pos
                break
        
        log("INFO", f"数据库持仓记录: {db_position}")
        log("INFO", f"API 实际持仓: {api_position}")
        
        # 如果数据库有持仓记录但 API 没有持仓，清除数据库记录
        if db_position and not api_position:
            log("WARNING", f"数据库中有持仓记录但 API 无持仓，清除数据库记录: {db_position}")
            close_position(config.SYMBOL)
            return None
        
        # 如果 API 有持仓但数据库没有记录，这种情况暂时不处理（需要手动介入）
        if api_position and not db_position:
            log("WARNING", f"API 有持仓但数据库无记录，请手动检查: {api_position}")
            # 这种情况比较复杂，因为我们不知道开仓价格和时间，暂时不自动处理
            return None
        
        # 如果两边都有持仓，检查是否一致
        if db_position and api_position:
            db_side = db_position.get('side')
            api_side = 'long' if float(api_position.get('positionAmt', 0)) > 0 else 'short'
            
            if db_side != api_side:
                log("WARNING", f"数据库持仓方向({db_side})与 API 持仓方向({api_side})不一致，以 API 为准")
                close_position(config.SYMBOL)
                return None
            else:
                log("INFO", f"数据库持仓记录与 API 持仓一致: {db_side}")
                return db_position
        
        # 如果两边都没有持仓
        log("INFO", "数据库和 API 都无持仓记录")
        return None
    
    def get_daily_initial_balance(self, date: str) -> float:
        """获取指定日期的初始余额，如果不存在则记录当前余额作为初始余额"""
        daily = get_daily_profit(date)
        if daily and daily.get('initial_balance', 0) > 0:
            return daily['initial_balance']
        else:
            # 如果没有记录初始余额，使用当前余额作为初始余额
            current_balance = self.trader.get_balance()
            return current_balance

    async def bootstrap(self):
        """
        初始化系统，确保数据库表结构存在并获取初始K线数据
        """
        try:
            # 确保数据库表结构存在
            init_db()
            print("数据库表结构初始化完成")
            
            if UMFutures is None:
                print("UMFutures 未导入，无法获取历史 K 线。")
                return
        
            client = UMFutures()  # 公共端点无需密钥
        
            def get_interval_ms(itv: str) -> int:
                num = int(itv[:-1])
                unit = itv[-1]
                if unit == 'm':
                    return num * 60000
                elif unit == 'h':
                    return num * 3600000
                elif unit == 'd':
                    return num * 86400000
                else:
                    raise ValueError(f"Unsupported interval: {itv}")
        
            interval_ms = get_interval_ms(config.INTERVAL)
            last_time = latest_kline_time(config.SYMBOL, config.INTERVAL) or 0
            current_time = int(time.time() * 1000)
        
            if last_time >= current_time - interval_ms:
                print("K 线数据已是最新，无需补齐。")
                return
        
            # 如果数据库为空，先获取初始 K 线
            all_inserts: List[Tuple] = []
            if last_time == 0:
                data = await asyncio.to_thread(
                    client.futures_klines, symbol=config.SYMBOL, interval=config.INTERVAL, limit=config.INITIAL_KLINES
                )
                print(f"从 API 获取到 {len(data)} 条初始 K 线数据。")
                for k in data:
                    ot = int(k[0])
                    o, h, l, c, v, ct = float(k[1]), float(k[2]), float(k[3]), float(k[4]), float(k[5]), int(k[6])
                    all_inserts.append((config.SYMBOL, config.INTERVAL, ot, o, h, l, c, v, ct))
                if data:
                    last_time = max(int(d[0]) for d in data)
        
            # 补齐缺失 K 线
            start_time = last_time + 1
            while start_time < current_time - interval_ms:  # 只补齐到上一个已收盘 K 线
                data = await asyncio.to_thread(
                    client.futures_klines, symbol=config.SYMBOL, interval=config.INTERVAL, startTime=start_time, limit=500
                )
                if not data:
                    break
                print(f"从 API 获取到 {len(data)} 条补齐 K 线数据（从 {start_time} 开始）。")
                for k in data:
                    ot = int(k[0])
                    if ot <= last_time:
                        continue
                    o, h, l, c, v, ct = float(k[1]), float(k[2]), float(k[3]), float(k[4]), float(k[5]), int(k[6])
                    all_inserts.append((config.SYMBOL, config.INTERVAL, ot, o, h, l, c, v, ct))
                    last_time = ot
                start_time = last_time + 1
                if len(data) < 500:
                    break
        
            if all_inserts:
                insert_kline(all_inserts)
                log("INFO", f"bootstrap 插入/补齐 {len(all_inserts)} 条 K 线: {config.SYMBOL} {config.INTERVAL}")
                print(f"插入/补齐 {len(all_inserts)} 条 K 线。")
            else:
                log("INFO", "bootstrap 无需插入K线（已最新）")
                print("无需插入 K 线。")
        except Exception as e:  # pragma: no cover
            log("ERROR", f"bootstrap失败: {e}")
            print(f"bootstrap 失败: {e}")

    async def run_ws(self):
        # 不需要重复调用bootstrap，因为在run_web中已经调用过了
        # await self.bootstrap()
        stream = f"{config.SYMBOL.lower()}@kline_{config.INTERVAL}"
        url = f"{KLINE_WS_URL}/{stream}"
        print(f"正在连接WebSocket: {url}")
        while True:
            try:
                async with websockets.connect(url, ping_interval=15, ping_timeout=15, max_queue=1000) as ws:
                    print("WebSocket连接成功，开始接收数据...")
                    await self._consume(ws)
            except Exception as e:  # pragma: no cover
                log("ERROR", f"ws error: {e}")
                print(f"WebSocket连接错误: {e}")
                await asyncio.sleep(3)
                continue

    async def _consume(self, ws):
        async for msg in ws:
            data = json.loads(msg)
            k = data.get("k", {})
            is_closed = k.get("x", False)
            price = float(k.get("c", 0))
            open_time = int(k.get("t", 0))
            close = float(k.get("c", 0))
            high = float(k.get("h", 0))
            low = float(k.get("l", 0))
            open_ = float(k.get("o", 0))
            volume = float(k.get("v", 0))

            self.last_price = price
            self.prices.append(price)
            if self.socketio:
                self.socketio.emit('price_update', {'price': price})
                print(f"WebSocket价格更新: {price}, 已通过SocketIO推送")

            # 在未收盘期间也进行节流评估，以便尽早产生“突破/跌破”信号
            now = time.time()
            if now - self._last_eval_ts >= 1.0:  # 每秒最多一次
                self._last_eval_ts = now
                await self.evaluate()

            if is_closed:
                insert_kline([
                    (
                        config.SYMBOL,
                        config.INTERVAL,
                        open_time,
                        open_,
                        high,
                        low,
                        close,
                        volume,
                        open_time + 1,
                    )
                ])
                await self.evaluate()

    async def evaluate(self):
        try:
            # 使用动态BOLL计算策略
            boll_result = calculate_boll_dynamic(
                config.SYMBOL, 
                config.INTERVAL, 
                config.BOLL_PERIOD, 
                config.BOLL_STD
            )
            last_up = float(boll_result['up'])
            last_mid = float(boll_result['mid'])
            last_dn = float(boll_result['dn'])
            
            # 记录使用的计算方法
            if hasattr(self, '_last_boll_method') and self._last_boll_method != boll_result['method']:
                log("INFO", f"BOLL计算方法切换: {boll_result['method']} (价格变化: {boll_result['price_change_pct']:.3f}%)")
            self._last_boll_method = boll_result['method']
            
            # 获取K线数据用于价格比较
            rows = fetch_klines(config.SYMBOL, limit=max(60, config.BOLL_PERIOD + 5))
            if len(rows) < config.BOLL_PERIOD:
                return
            df = pd.DataFrame(rows)
        except Exception as e:
            log("ERROR", f"动态BOLL计算失败，回退到币安兼容方法: {e}")
            try:
                # 回退到币安兼容方法
                boll_result = calculate_boll_binance_compatible(
                    config.SYMBOL, 
                    config.INTERVAL, 
                    config.BOLL_PERIOD, 
                    config.BOLL_STD
                )
                last_up = float(boll_result['up'])
                last_mid = float(boll_result['mid'])
                last_dn = float(boll_result['dn'])
                
                rows = fetch_klines(config.SYMBOL, limit=max(60, config.BOLL_PERIOD + 5))
                if len(rows) < config.BOLL_PERIOD:
                    return
                df = pd.DataFrame(rows)
            except Exception as e2:
                log("ERROR", f"币安兼容BOLL计算也失败，回退到原始方法: {e2}")
                # 最后回退到原始方法
                rows = fetch_klines(config.SYMBOL, limit=max(60, config.BOLL_PERIOD + 5))
                if len(rows) < config.BOLL_PERIOD:
                    return
                df = pd.DataFrame(rows)
                # 计算基于闭合 K 线的 BOLL，以匹配 Binance 显示
                mid, up, dn = bollinger_bands(df, config.BOLL_PERIOD, config.BOLL_STD, ddof=0)
                last_mid = float(mid.iloc[-1])
                last_up = float(up.iloc[-1])
                last_dn = float(dn.iloc[-1])
        
        # 使用K线收盘价而不是实时价格进行比较
        close_price = float(df["close"].iloc[-1])
        current_price = float(self.last_price) if self.last_price != 0 else close_price
        
        if self.socketio:
            boll_data = {
                'boll_up': last_up, 
                'boll_mid': last_mid, 
                'boll_dn': last_dn,
                'close_price': close_price,
                'current_price': current_price,
                'state': self.state
            }
            self.socketio.emit('boll_update', boll_data)

        # 只在状态发生变化时打印日志，避免重复输出
        state_changed = self._last_logged_state != self.state
        
        if state_changed:
            log("INFO", f"状态变化: {self.state}, 收盘价: {close_price:.2f}, UP: {last_up:.2f}, MID: {last_mid:.2f}, DN: {last_dn:.2f}")
            self._last_logged_state = self.state

        # 新的BOLL交易策略状态机
        await self._handle_state_transitions(close_price, current_price, last_up, last_mid, last_dn)

    async def _handle_state_transitions(self, close_price: float, current_price: float, up: float, mid: float, dn: float):
        """处理状态转换的核心逻辑"""
        
        # ==================== 开空逻辑 ====================
        
        # 等待开仓状态：收盘价突破UP -> 突破UP等待跌破
        if self.state == self.STATE_WAITING and close_price > up:
            self.state = self.STATE_BREAKOUT_UP_WAIT_FALL
            log("INFO", f"收盘价突破UP({up:.2f}) -> 标记状态：突破UP，等待跌破UP")
            return
            
        # 突破UP等待跌破：收盘价跌破UP -> 开空仓
        if self.state == self.STATE_BREAKOUT_UP_WAIT_FALL and close_price <= up:
            # 新增条件：如果收盘价小于中轨，则不开仓，继续等待
            if close_price < mid:
                log("INFO", f"收盘价跌破UP({up:.2f})但小于中轨({mid:.2f}) -> 不开仓，继续等待")
                return
            if await self._place_short_order(current_price):
                self.state = self.STATE_HOLDING_SHORT
                log("INFO", f"收盘价跌破UP({up:.2f})且大于等于中轨({mid:.2f}) -> 开空仓，标记状态：持仓SHORT")
            return
            
        # 已止损SHORT等待跌破：收盘价跌破UP -> 再次开空
        if self.state == self.STATE_SHORT_STOP_LOSS_WAIT_FALL and close_price <= up:
            # 新增条件：如果收盘价小于中轨，则不开仓，继续等待
            if close_price < mid:
                log("INFO", f"收盘价跌破UP({up:.2f})但小于中轨({mid:.2f}) -> 不开仓，继续等待")
                return
            if await self._place_short_order(current_price):
                self.state = self.STATE_HOLDING_SHORT
                log("INFO", f"收盘价跌破UP({up:.2f})且大于等于中轨({mid:.2f}) -> 再次开空，标记状态：持仓SHORT")
            return
            
        # 持仓SHORT的处理
        if self.state == self.STATE_HOLDING_SHORT:
            # A. 止损情况：收盘价再次站上UP -> 立即平仓止损
            if close_price > up:
                if await self.close_and_update_profit(current_price):
                    self.state = self.STATE_SHORT_STOP_LOSS_WAIT_FALL
                    log("INFO", f"空仓止损：收盘价站上UP({up:.2f}) -> 平仓，标记状态：已止损SHORT，等待跌破UP")
                return
                
            # B. 止盈情况：收盘价跌破中轨
            if close_price < mid:
                self.state = self.STATE_SHORT_BELOW_MID_WAIT
                log("INFO", f"收盘价跌破中轨({mid:.2f}) -> 标记状态：跌破中轨，等待突破中轨或跌破DN")
                return
                
        # 跌破中轨等待状态的处理
        if self.state == self.STATE_SHORT_BELOW_MID_WAIT:
            # 收盘价突破中轨 -> 止盈
            if close_price > mid:
                if await self.close_and_update_profit(current_price):
                    self.state = self.STATE_SHORT_PROFIT_TAKEN
                    log("INFO", f"收盘价突破中轨({mid:.2f}) -> 止盈SHORT，标记状态：已止盈SHORT，等待开仓")
                return
                
            # 收盘价跌破DN -> 标记为等待止盈状态
            if close_price < dn:
                self.state = self.STATE_SHORT_WAIT_PROFIT
                log("INFO", f"收盘价跌破DN({dn:.2f}) -> 标记状态：等待止盈SHORT（等待实时价格>DN）")
                return
                

                
        # ==================== 开多逻辑 ====================
        
        # 等待开仓状态：收盘价跌破DN -> 跌破DN等待反弹
        if self.state == self.STATE_WAITING and close_price < dn:
            self.state = self.STATE_BREAKDOWN_DN_WAIT_BOUNCE
            log("INFO", f"收盘价跌破DN({dn:.2f}) -> 标记状态：跌破DN，等待反弹到DN")
            return
            
        # 跌破DN等待反弹：收盘价反弹至DN -> 开多仓
        if self.state == self.STATE_BREAKDOWN_DN_WAIT_BOUNCE and close_price > dn:
            # 新增条件：如果收盘价大于中轨，则不开仓，继续等待
            if close_price > mid:
                log("INFO", f"收盘价反弹至DN({dn:.2f})但大于中轨({mid:.2f}) -> 不开仓，继续等待")
                return
            if await self._place_long_order(current_price):
                self.state = self.STATE_HOLDING_LONG
                log("INFO", f"收盘价反弹至DN({dn:.2f})且小于等于中轨({mid:.2f}) -> 开多仓，标记状态：持仓LONG")
            return
            
        # 已止损LONG等待反弹：收盘价反弹至DN -> 再次开多
        if self.state == self.STATE_LONG_STOP_LOSS_WAIT_BOUNCE and close_price > dn:
            # 新增条件：如果收盘价大于中轨，则不开仓，继续等待
            if close_price > mid:
                log("INFO", f"收盘价反弹至DN({dn:.2f})但大于中轨({mid:.2f}) -> 不开仓，继续等待")
                return
            if await self._place_long_order(current_price):
                self.state = self.STATE_HOLDING_LONG
                log("INFO", f"收盘价反弹至DN({dn:.2f})且小于等于中轨({mid:.2f}) -> 再次开多，标记状态：持仓LONG")
            return
            
        # 持仓LONG的处理
        if self.state == self.STATE_HOLDING_LONG:
            # A. 止损情况：收盘价跌破DN -> 立即平仓止损
            if close_price < dn:
                if await self.close_and_update_profit(current_price):
                    self.state = self.STATE_LONG_STOP_LOSS_WAIT_BOUNCE
                    log("INFO", f"多仓止损：收盘价跌破DN({dn:.2f}) -> 平仓，标记状态：已止损LONG，等待收盘价>DN")
                return
                
            # B. 止盈情况：收盘价突破中轨
            if close_price > mid:
                self.state = self.STATE_LONG_ABOVE_MID_WAIT
                log("INFO", f"收盘价突破中轨({mid:.2f}) -> 标记状态：突破中轨，等待突破UP或跌破中轨")
                return
                
        # 突破中轨等待状态的处理
        if self.state == self.STATE_LONG_ABOVE_MID_WAIT:
            # 收盘价突破UP -> 标记为等待止盈状态
            if close_price > up:
                self.state = self.STATE_LONG_WAIT_PROFIT
                log("INFO", f"收盘价突破UP({up:.2f}) -> 标记状态：等待止盈LONG（等待实时价格<UP）")
                return
                
            # 收盘价跌破中轨 -> 止盈LONG
            if close_price < mid:
                if await self.close_and_update_profit(current_price):
                    self.state = self.STATE_LONG_PROFIT_TAKEN
                    log("INFO", f"收盘价跌破中轨({mid:.2f}) -> 止盈LONG，标记状态：已止盈，等待开仓")
                return
                
        # ==================== 等待止盈状态处理 ====================
        
        # 等待止盈SHORT状态：实时价格大于DN时立即止盈
        if self.state == self.STATE_SHORT_WAIT_PROFIT:
            if current_price > dn:
                if await self.close_and_update_profit(current_price):
                    self.state = self.STATE_WAITING
                    log("INFO", f"实时价格({current_price:.2f})大于DN({dn:.2f}) -> 立即止盈SHORT，标记状态：等待开仓")
                return
                
        # 等待止盈LONG状态：实时价格小于UP时立即止盈
        if self.state == self.STATE_LONG_WAIT_PROFIT:
            if current_price < up:
                if await self.close_and_update_profit(current_price):
                    self.state = self.STATE_WAITING
                    log("INFO", f"实时价格({current_price:.2f})小于UP({up:.2f}) -> 立即止盈LONG，标记状态：等待开仓")
                return
                
        # ==================== 已止盈状态处理 ====================
        
        # 已止盈SHORT状态 -> 重新开始等待开仓
        if self.state == self.STATE_SHORT_PROFIT_TAKEN:
            self.state = self.STATE_WAITING
            log("INFO", "已止盈SHORT -> 重新等待开仓机会")
            return
            
        # 已止盈LONG状态 -> 重新开始等待开仓  
        if self.state == self.STATE_LONG_PROFIT_TAKEN:
            self.state = self.STATE_WAITING
            log("INFO", "已止盈LONG -> 重新等待开仓机会")
            return

    async def _place_short_order(self, current_price: float) -> bool:
        """下空单"""
        current_time = int(time.time() * 1000)
        if current_time - self.last_trade_time < self.trade_cooldown:
            log("INFO", f"交易冷却中，距离上次交易{(current_time - self.last_trade_time)/1000:.1f}秒")
            return False
            
        balance = self.trader.get_balance()
        if balance <= 0 or current_price <= 0 or config.LEVERAGE <= 0:
            log("WARNING", "Insufficient balance, invalid price, or invalid leverage for short order")
            return False
            
        margin = balance * config.TRADE_PERCENT
        qty = margin * config.LEVERAGE / current_price
        
        # 详细记录开仓计算过程
        log("INFO", f"开空仓计算 - 余额: {balance:.2f}, 交易比例: {config.TRADE_PERCENT}, 杠杆: {config.LEVERAGE}X")
        log("INFO", f"开空仓计算 - 分配保证金: {margin:.2f}, 价格: {current_price:.2f}, 数量: {qty:.6f}")
        
        success = await self.trader.place_order("SELL", qty, current_price)
        if success:
            self.last_trade_time = current_time
            log("INFO", f"开空仓成功: {qty:.6f} @ {current_price:.2f}")
        return success

    async def _place_long_order(self, current_price: float) -> bool:
        """下多单"""
        current_time = int(time.time() * 1000)
        if current_time - self.last_trade_time < self.trade_cooldown:
            log("INFO", f"交易冷却中，距离上次交易{(current_time - self.last_trade_time)/1000:.1f}秒")
            return False
            
        balance = self.trader.get_balance()
        if balance <= 0 or current_price <= 0 or config.LEVERAGE <= 0:
            log("WARNING", "Insufficient balance, invalid price, or invalid leverage for long order")
            return False
            
        margin = balance * config.TRADE_PERCENT
        qty = margin * config.LEVERAGE / current_price
        
        # 详细记录开仓计算过程
        log("INFO", f"开多仓计算 - 余额: {balance:.2f}, 交易比例: {config.TRADE_PERCENT}, 杠杆: {config.LEVERAGE}X")
        log("INFO", f"开多仓计算 - 分配保证金: {margin:.2f}, 价格: {current_price:.2f}, 数量: {qty:.6f}")
        
        success = await self.trader.place_order("BUY", qty, current_price)
        if success:
            self.last_trade_time = current_time
            log("INFO", f"开多仓成功: {qty:.6f} @ {current_price:.2f}")
        return success



    async def close_and_update_profit(self, price: float):
        pos = get_position(config.SYMBOL)
        if not pos:
            return True  # 没有持仓，认为是成功的
        side = pos['side']
        entry_price = pos['entry_price']
        qty = pos['qty']
        exit_price = await self.trader.close_all(price)
        if exit_price <= 0:
            log("ERROR", f"平仓失败，exit_price={exit_price}")
            return False  # 平仓失败
        this_profit = (exit_price - entry_price) * qty if side == 'long' else (entry_price - exit_price) * qty
        date = datetime.now().date().isoformat()
        daily = get_daily_profit(date)
        if daily is None:
            daily = {'trade_count': 0, 'profit': 0.0, 'profit_rate': 0.0, 'loss_count': 0, 'profit_count': 0}
        
        # 更新交易次数和总盈利
        daily['trade_count'] += 1
        daily['profit'] += this_profit
        
        # 计算当日手续费总和
        from db import get_conn
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("SELECT SUM(fee) FROM trades WHERE date(datetime(ts/1000, 'unixepoch')) = ?", (date,))
        total_fees_result = cur.fetchone()
        total_fees = total_fees_result[0] if total_fees_result and total_fees_result[0] else 0.0
        conn.close()
        
        # 计算净利润（扣除手续费后的利润）
        net_profit = daily['profit'] - total_fees
        
        # 统计盈利和亏损次数（基于单笔交易盈亏）
        if this_profit > 0:
            daily['profit_count'] = daily.get('profit_count', 0) + 1
        elif this_profit < 0:
            daily['loss_count'] = daily.get('loss_count', 0) + 1
        
        # 获取当日初始余额
        daily_initial_balance = self.get_daily_initial_balance(date)
        
        # 如果是当日第一笔交易，记录初始余额
        if daily['trade_count'] == 1:
            daily_initial_balance = self.trader.get_balance() - this_profit
        
        # 计算利润率：(当前余额 - 当日初始余额) / 当日初始余额
        current_balance = self.trader.get_balance()
        if daily_initial_balance > 0:
            daily['profit_rate'] = ((current_balance - daily_initial_balance) / daily_initial_balance) * 100
        else:
            daily['profit_rate'] = 0.0
        
        update_daily_profit(date, daily['trade_count'], net_profit, daily['profit_rate'], 
                          daily.get('loss_count', 0), daily.get('profit_count', 0), total_fees, daily_initial_balance)
        
        log("INFO", f"平仓成功，使用收盘价策略无需冷却期")
        
        return True  # 平仓成功


async def main():
    eng = Engine()
    await eng.run_ws()


if __name__ == "__main__":
    asyncio.run(main())