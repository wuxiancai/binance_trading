import os

class Config:
    # 基本设置
    SYMBOL: str = os.getenv("SYMBOL", "BTCUSDT")
    INTERVAL: str = os.getenv("INTERVAL", "15m")  # K线时间周期
    BOLL_PERIOD: int = int(os.getenv("BOLL_PERIOD", 26))
    BOLL_STD: float = float(os.getenv("BOLL_STD", 2.5))
    INITIAL_KLINES: int = int(os.getenv("INITIAL_KLINES", 50))

    # 交易相关
    DEFAULT_MARGIN: float = 1000.0  # 模拟默认保证金余额 USDT
    TRADE_PERCENT: float = 0.7  # 交易金额占保证金的百分比
    LEVERAGE: int = int(os.getenv("LEVERAGE", 10))  # 杠杆倍数
    FEE_RATE: float = float(os.getenv("FEE_RATE", 0.0005))  # 手续费率，默认0.05% = 0.0005
    USE_TESTNET: bool = os.getenv("USE_TESTNET", "false").lower() == "true"
    SIMULATE: bool = os.getenv("SIMULATE", "false").lower() == "true"  # 模拟交易

    # API 密钥
    API_KEY: str = os.getenv("BINANCE_API_KEY", "yHEbiLZVNTpX81Vc6UYPJpIsPFa6P461R1OVHHq7JcLs60B4GPcVSEq7Chw8OCGG")
    API_SECRET: str = os.getenv("BINANCE_API_SECRET", "gwbbkf4uCPTJbMH6M3QZFJ4qtkqqzasg28vVZb20nkWwe7kDCZsSRSMjidHCb3Th")

    # 数据库与日志
    DB_PATH: str = os.getenv("DB_PATH", "data/trading.db")
    LOG_DIR: str = os.getenv("LOG_DIR", "logs")

    # 自动重启
    AUTO_RESTART: bool = os.getenv("AUTO_RESTART", "true").lower() == "true"

    # Web 服务
    WEB_HOST: str = os.getenv("WEB_HOST", "0.0.0.0")
    WEB_PORT: int = int(os.getenv("WEB_PORT", 5000))


config = Config()