import numpy as np
import pandas as pd
import requests


def bollinger_bands(df: pd.DataFrame, period: int = 20, stds: float = 2.0, ddof: int = 0):
    # df columns: open_time, open, high, low, close, volume
    close = df["close"].astype(float)
    mid = close.rolling(window=period, min_periods=period).mean()
    std = close.rolling(window=period, min_periods=period).std(ddof=ddof)
    up = mid + stds * std
    dn = mid - stds * std
    return mid, up, dn


def calculate_boll_binance_compatible(symbol, interval, period=21, std_mult=2.0):
    """
    计算与币安兼容的BOLL值
    关键：不使用当前未完成的K线，避免实时价格波动导致的误差
    
    Args:
        symbol: 交易对符号
        interval: K线间隔
        period: BOLL周期，默认21
        std_mult: 标准差倍数，默认2.0
    
    Returns:
        dict: 包含up, mid, dn, last_complete_close等信息
    """
    # 获取K线数据，多获取一些确保有足够的数据
    url = "https://api.binance.com/api/v3/klines"
    params = {
        'symbol': symbol,
        'interval': interval,
        'limit': period + 10
    }
    
    response = requests.get(url, params=params)
    data = response.json()
    
    df = pd.DataFrame(data, columns=[
        'timestamp', 'open', 'high', 'low', 'close', 'volume',
        'close_time', 'quote_asset_volume', 'number_of_trades',
        'taker_buy_base_asset_volume', 'taker_buy_quote_asset_volume', 'ignore'
    ])
    
    for col in ['open', 'high', 'low', 'close', 'volume']:
        df[col] = df[col].astype(float)
    
    # 关键修正：排除最后一根K线（当前未完成的K线）
    df_complete = df.iloc[:-1]
    
    # 确保有足够的数据
    if len(df_complete) < period:
        raise ValueError(f"数据不足，需要至少{period}根完整K线，当前只有{len(df_complete)}根")
    
    # 计算BOLL，使用样本标准差（ddof=1）
    mid, up, dn = bollinger_bands(df_complete, period, std_mult, ddof=1)
    
    return {
        'up': up.iloc[-1],
        'mid': mid.iloc[-1],
        'dn': dn.iloc[-1],
        'last_complete_close': df_complete['close'].iloc[-1],
        'current_close': df['close'].iloc[-1],
        'data_points': len(df_complete)
    }


def calculate_boll_dynamic(symbol, interval, period=21, std_mult=2.0):
    """
    动态BOLL计算策略
    根据价格波动幅度选择最佳计算方法
    
    Args:
        symbol: 交易对符号
        interval: K线间隔
        period: BOLL周期，默认21
        std_mult: 标准差倍数，默认2.0
    
    Returns:
        dict: 包含up, mid, dn, method, price_change等信息
    """
    # 获取当前价格
    price_url = f"https://api.binance.com/api/v3/ticker/price?symbol={symbol}"
    price_response = requests.get(price_url)
    current_price = float(price_response.json()['price'])
    
    # 获取K线数据
    url = "https://api.binance.com/api/v3/klines"
    params = {
        'symbol': symbol,
        'interval': interval,
        'limit': period + 10
    }
    
    response = requests.get(url, params=params)
    data = response.json()
    
    df = pd.DataFrame(data, columns=[
        'timestamp', 'open', 'high', 'low', 'close', 'volume',
        'close_time', 'quote_asset_volume', 'number_of_trades',
        'taker_buy_base_asset_volume', 'taker_buy_quote_asset_volume', 'ignore'
    ])
    
    for col in ['open', 'high', 'low', 'close', 'volume']:
        df[col] = df[col].astype(float)
    
    # 计算价格变化幅度
    last_close = df['close'].iloc[-1]
    price_change = abs(current_price - last_close)
    price_change_pct = price_change / last_close * 100
    
    # 根据价格变化幅度选择计算方法
    if price_change_pct > 0.5:  # 价格变化超过0.5%，使用仅完整K线方法
        df_calc = df.iloc[:-1]
        method = "仅完整K线（大波动）"
    elif price_change_pct > 0.1:  # 价格变化0.1%-0.5%，使用平均价格方法
        df_calc = df.copy()
        # 使用高低价和当前价的平均值
        avg_price = (df_calc.loc[df_calc.index[-1], 'high'] + 
                    df_calc.loc[df_calc.index[-1], 'low'] + current_price) / 3
        df_calc.loc[df_calc.index[-1], 'close'] = avg_price
        method = "平均价格（中等波动）"
    else:  # 价格变化小于0.1%，使用实时价格方法
        df_calc = df.copy()
        df_calc.loc[df_calc.index[-1], 'close'] = current_price
        method = "实时价格（小波动）"
    
    # 确保有足够的数据
    if len(df_calc) < period:
        raise ValueError(f"数据不足，需要至少{period}根K线，当前只有{len(df_calc)}根")
    
    # 计算BOLL
    mid, up, dn = bollinger_bands(df_calc, period, std_mult, ddof=1)
    
    return {
        'up': up.iloc[-1],
        'mid': mid.iloc[-1],
        'dn': dn.iloc[-1],
        'current_price': current_price,
        'last_close': last_close,
        'price_change': price_change,
        'price_change_pct': price_change_pct,
        'method': method,
        'data_points': len(df_calc)
    }