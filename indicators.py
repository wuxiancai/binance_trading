import numpy as np
import pandas as pd
import requests
from config import config


def get_boll_params(interval: str = None):
    """
    根据时间周期获取推荐的BOLL参数
    
    Args:
        interval: 时间周期，如'1m', '5m', '15m', '1h', '4h', '1d'
                 如果为None，使用配置文件中的默认周期
    
    Returns:
        dict: 包含period和std的字典
    """
    if interval is None:
        interval = config.INTERVAL
    
    # 从配置中获取推荐参数，如果没有则使用默认值
    return config.BOLL_PARAMS.get(interval, {"period": config.BOLL_PERIOD, "std": config.BOLL_STD})


def bollinger_bands(df: pd.DataFrame, period: int = 20, stds: float = 2.0, ddof: int = None):
    """
    计算布林带指标
    
    Args:
        df: 包含价格数据的DataFrame，必须有'close'列
        period: 移动平均周期，默认20
        stds: 标准差倍数，默认2.0
        ddof: 标准差计算的自由度调整，None=使用配置默认值，0=总体标准差，1=样本标准差
    
    Returns:
        tuple: (中轨, 上轨, 下轨)
    """
    # 如果ddof为None，使用配置文件中的默认值
    if ddof is None:
        ddof = config.BOLL_DDOF
    
    # 计算移动平均线（中轨）
    mid = df['close'].rolling(window=period).mean()
    
    # 计算标准差
    std = df['close'].rolling(window=period).std(ddof=ddof)
    
    # 计算上轨和下轨
    up = mid + (std * stds)
    dn = mid - (std * stds)
    
    return mid, up, dn


def calculate_boll_binance_compatible(symbol, interval, period=None, std_mult=None):
    """
    计算与币安兼容的BOLL值
    关键：不使用当前未完成的K线，避免实时价格波动导致的误差
    
    Args:
        symbol: 交易对符号
        interval: K线间隔
        period: BOLL周期，None时使用推荐参数
        std_mult: 标准差倍数，None时使用推荐参数
    
    Returns:
        dict: 包含up, mid, dn, last_complete_close等信息
    """
    # 获取推荐的BOLL参数
    boll_params = get_boll_params(interval)
    if period is None:
        period = boll_params["period"]
    if std_mult is None:
        std_mult = boll_params["std"]
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
    
    # 计算BOLL，使用总体标准差（ddof=0）以匹配币安官网标准
    mid, up, dn = bollinger_bands(df_complete, period, std_mult, ddof=0)
    
    return {
        'up': up.iloc[-1],
        'mid': mid.iloc[-1],
        'dn': dn.iloc[-1],
        'last_complete_close': df_complete['close'].iloc[-1],
        'current_close': df['close'].iloc[-1],
        'data_points': len(df_complete)
    }


def calculate_boll_dynamic(symbol, interval, period=None, std_mult=None):
    """
    动态BOLL计算策略
    根据价格波动幅度选择最佳计算方法
    
    Args:
        symbol: 交易对符号
        interval: K线间隔
        period: BOLL周期，None时使用推荐参数
        std_mult: 标准差倍数，None时使用推荐参数
    
    Returns:
        dict: 包含up, mid, dn, method, price_change等信息
    """
    # 获取推荐的BOLL参数
    boll_params = get_boll_params(interval)
    if period is None:
        period = boll_params["period"]
    if std_mult is None:
        std_mult = boll_params["std"]
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
    
    # 简化实时价格处理逻辑，更接近币安官网标准
    # 使用完整的历史K线数据 + 当前价格替换最后一根K线的收盘价
    df_calc = df.copy()
    df_calc.loc[df_calc.index[-1], 'close'] = current_price
    method = "实时价格替换"
    
    # 确保有足够的数据
    if len(df_calc) < period:
        raise ValueError(f"数据不足，需要至少{period}根K线，当前只有{len(df_calc)}根")
    
    # 计算BOLL，使用总体标准差（ddof=0）以匹配币安官网标准
    mid, up, dn = bollinger_bands(df_calc, period, std_mult, ddof=0)
    
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