print("=== webapp.py 启动开始 ===")

import threading
import time
import psutil
import os
import socket
import asyncio
from flask import Flask, render_template_string, jsonify, request
from flask_socketio import SocketIO, emit
import logging

print("基础模块导入完成")

from config import config
print(f"config导入完成，WEB_PORT={config.WEB_PORT}")

from db import get_conn, init_db, latest_kline_time, get_position, get_daily_profits
print("db模块导入完成")

from engine import Engine
print("engine模块导入完成")

from indicators import bollinger_bands
import pandas as pd
from db import fetch_klines
print("其他模块导入完成")

print("开始初始化数据库...")
init_db()
print("数据库初始化完成")

app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')
logging.getLogger('werkzeug').setLevel(logging.ERROR)

# 工具：UTC+8 时间格式（月-日 时:分）
def fmt_ts_utc8(ts_ms: int) -> str:
    return time.strftime('%m-%d %H:%M', time.gmtime(ts_ms / 1000 + 8 * 3600))

TEMPLATE = """
<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>自动交易监控</title>
  <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css">
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Noto+Sans+SC:wght@300;400;500;600&display=swap" rel="stylesheet">
  <script src="https://cdn.jsdelivr.net/npm/chart.js@3.9.1/dist/chart.min.js"></script>
  <script src="https://cdn.jsdelivr.net/npm/chartjs-adapter-date-fns@2.0.0/dist/chartjs-adapter-date-fns.bundle.min.js"></script>
  <script src="https://cdn.jsdelivr.net/npm/chartjs-chart-financial@0.2.1/dist/chartjs-chart-financial.min.js"></script>
  <script src="https://cdn.socket.io/4.7.2/socket.io.min.js"></script>

  <style>
    :root {
      /* 中国水墨山水色彩 */
      --ink-black: #2c3e50;        /* 墨黑 */
      --ink-gray: #34495e;         /* 墨灰 */
      --mist-gray: #95a5a6;        /* 雾灰 */
      --cloud-white: #ecf0f1;      /* 云白 */
      --mountain-blue: #7fb3d3;    /* 山青 */
      --water-blue: #a8d8ea;       /* 水蓝 */
      --bamboo-green: #52c41a;     /* 竹绿 */
      --sunset-red: #ff7875;       /* 夕红 */
      --paper-bg: #fafbfc;         /* 宣纸背景 */
      --card-bg: rgba(255, 255, 255, 0.85); /* 半透明卡片 */
    }

    * {
      font-family: 'Noto Sans SC', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    }

    body {
      background: #ffffff;
      padding: 16px;
      font-size: 13px;
      color: var(--ink-black);
      min-height: 100vh;
    }

    .container {
      max-width: 1400px;
    }

    h3 {
      color: var(--ink-black);
      font-weight: 500;
      font-size: 1.4rem;
      letter-spacing: 0.5px;
    }

    .card {
      background: var(--card-bg);
      border: 1px solid rgba(151, 165, 166, 0.2);
      border-radius: 8px;
      box-shadow: 0 2px 8px rgba(44, 62, 80, 0.08);
      backdrop-filter: blur(10px);
      transition: all 0.3s ease;
    }

    .card:hover {
      box-shadow: 0 4px 16px rgba(44, 62, 80, 0.12);
      transform: translateY(-1px);
    }

    .card-header {
      background: linear-gradient(90deg, var(--mountain-blue), var(--water-blue));
      color: white;
      border-bottom: none;
      font-weight: 500;
      font-size: 13px;
      padding: 10px 16px;
      border-radius: 8px 8px 0 0 !important;
    }

    .card-body {
      padding: 5px 5px;
      font-size: 12px;
      line-height: 1.6;
    }

    .card-body > div {
      margin-bottom: 6px;
      color: var(--ink-gray);
    }

    .card-body > div:last-child {
      margin-bottom: 0;
    }

    .row {
      --bs-gutter-x: 12px;
      --bs-gutter-y: 12px;
    }

    .metric {
      font-size: 1rem;
      font-weight: 500;
    }

    .log {
      white-space: pre-wrap;
      max-height: 280px;
      overflow: auto;
      background: #ffffff;
      border: 1px solid rgba(151, 165, 166, 0.15);
      border-radius: 6px;
      padding: 5px;
      font-family: 'Courier New', monospace;
      font-size: 11px;
      color: var(--ink-gray);
      line-height: 1.4;
    }

    /* 交易记录容器，与日志高度一致 */
    #trades {
      max-height: 280px;
      overflow: auto;
      background: #ffffff;
      border: 1px solid rgba(151, 165, 166, 0.15);
      border-radius: 6px;
      padding: 5px;
      margin: 0;
    }

    .table-sm {
      font-size: 11px;
    }

    .table-sm td, .table-sm th {
      padding: 6px 8px;
      border-color: rgba(151, 165, 166, 0.15);
      color: var(--ink-gray);
    }

    .table-sm th {
      background: var(--cloud-white);
      font-weight: 500;
      color: var(--ink-black);
    }

    .list-group-item {
      background: transparent;
      border: none;
      border-bottom: 1px solid rgba(151, 165, 166, 0.1);
      padding: 8px 0;
      font-size: 11px;
      color: var(--ink-gray);
      line-height: 1.5;
    }

    .list-group-item:last-child {
      border-bottom: none;
    }

    /* 交易记录颜色样式 */
    .trade-close {
      color: var(--bamboo-green) !important;
      font-weight: 500;
    }

    /* 盈亏显示样式 */
    .trade-profit {
      color: var(--bamboo-green) !important;
      font-weight: 600;
    }

    .trade-loss {
      color: var(--sunset-red) !important;
      font-weight: 600;
    }

    .trade-neutral {
      color: var(--mist-gray) !important;
      font-weight: 500;
    }

    /* 手续费显示样式 */
    .trade-fee {
      color: #1890ff !important;  /* 蓝色 */
      font-weight: 500;
    }

    /* 持仓方向颜色 */
    .position-long {
      color: var(--bamboo-green) !important;
      font-weight: 500;
    }

    .position-short {
      color: var(--sunset-red) !important;
      font-weight: 500;
    }

    /* BOLL轨道颜色 */
    .boll-upper {
      color: var(--bamboo-green) !important;
      font-weight: 500;
    }

    .boll-lower {
      color: var(--sunset-red) !important;
      font-weight: 500;
    }

    /* 实时币价颜色 */
    .price-above-upper {
      color: var(--bamboo-green) !important;
      font-weight: 600;
    }

    .price-below-lower {
      color: var(--sunset-red) !important;
      font-weight: 600;
    }

    /* 日志颜色样式 */
    .log-stop-loss {
      color: var(--sunset-red) !important;
    }

    .log-take-profit {
      color: var(--bamboo-green) !important;
    }

    /* 状态颜色样式 */
    .log-holding-long {
      color: var(--bamboo-green) !important;
      font-weight: 500;
    }

    .log-holding-short {
      color: var(--sunset-red) !important;
      font-weight: 500;
    }

    .log-waiting {
      color: var(--ink-black) !important;
      font-weight: bold;
    }

    /* 突破信息颜色样式 */
    .log-breakout {
      color: #1890ff !important;
      font-weight: 500;
    }

    .text-success {
      color: var(--bamboo-green) !important;
      font-weight: 500;
    }

    .text-danger {
      color: var(--sunset-red) !important;
      font-weight: 500;
    }

    .text-muted {
      color: var(--mist-gray) !important;
    }

    /* 系统信息在标题行内单行展示 */
    #sysline {
      font-size: clamp(9px, 1.6vw, 12px);
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
      color: var(--mist-gray);
      font-weight: 300;
    }

    /* 系统监控警告颜色 */
    .sys-warning {
      color: var(--sunset-red) !important;
      font-weight: 600;
    }

    /* 配置和持仓卡片布局优化 */
    .config-item, .position-item {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 6px;
    }

    .config-item:last-child, .position-item:last-child {
      margin-bottom: 0;
    }

    .config-key, .position-key {
      text-align: right;
      font-weight: 500;
      color: var(--ink-gray);
      flex: 0 0 auto;
      margin-right: 12px;
    }

    .config-value, .position-value {
      text-align: left;
      flex: 1;
      color: var(--ink-black);
    }

    /* 响应式优化 */
    @media (max-width: 768px) {
      body {
        padding: 12px;
        font-size: 12px;
      }
      
      h3 {
        font-size: 1.2rem;
      }
      
      .card-body {
        padding: 12px;
        font-size: 11px;
      }
      
      .log {
        max-height: 200px;
        font-size: 10px;
      }
    }

    /* 滚动条美化 - 自动隐藏 */
    ::-webkit-scrollbar {
      width: 6px;
      height: 6px;
    }

    ::-webkit-scrollbar-track {
      background: transparent;
      border-radius: 3px;
    }

    ::-webkit-scrollbar-thumb {
      background: transparent;
      border-radius: 3px;
      transition: background 0.3s ease;
    }

    /* 容器悬停时显示滚动条 */
    .log:hover::-webkit-scrollbar-thumb,
    #trades:hover::-webkit-scrollbar-thumb {
      background: rgba(151, 165, 166, 0.3);
    }

    .log:hover::-webkit-scrollbar-thumb:hover,
    #trades:hover::-webkit-scrollbar-thumb:hover {
      background: rgba(151, 165, 166, 0.5);
    }

    .log:hover::-webkit-scrollbar-track,
    #trades:hover::-webkit-scrollbar-track {
      background: rgba(151, 165, 166, 0.1);
    }

    /* 数值高亮 */
    #balance {
      color: var(--bamboo-green);
      font-weight: 500;
    }

    /* 卡片内容间距优化 */
    .my-3 {
      margin-top: 12px !important;
      margin-bottom: 12px !important;
    }

    .mt-2 {
      margin-top: 8px !important;
    }

    /* K线图样式 */
    #klineChart {
      background: #ffffff;
      border-radius: 6px;
      border: 1px solid rgba(151, 165, 166, 0.15);
      padding: 8px;
    }

    #klineCanvas {
      border-radius: 4px;
    }

    /* K线图选择器样式 */
    #klineLimit {
      background: var(--cloud-white);
      border: 1px solid rgba(151, 165, 166, 0.3);
      color: var(--ink-gray);
      font-size: 11px;
      padding: 4px 8px;
      border-radius: 4px;
      min-width: 100px;
    }

    #klineLimit:focus {
      border-color: var(--mountain-blue);
      box-shadow: 0 0 0 2px rgba(127, 179, 211, 0.2);
      outline: none;
    }

    /* 实时数据显示区域样式 */
    .real-time-data {
      background: transparent;
      border: 1px solid rgba(151, 165, 166, 0.2);
      border-radius: 6px;
      padding: 6px 28px;
      margin-bottom: 0;
      font-size: 11px;
      display: flex;
      align-items: center;
      gap: 12px;
      line-height: 1.4;
    }

    .rt-label {
      font-weight: 600;
      color: var(--ink-black);
      min-width: 80px;
      flex-shrink: 0;
    }

    .rt-item {
      font-weight: 500;
      color: var(--ink-gray);
      margin-right: 12px;
    }

    .rt-value {
      font-weight: 600;
      color: var(--ink-black);
      margin-left: 2px;
    }

    .rt-separator {
      color: var(--mist-gray);
      font-weight: 300;
      margin: 0 16px;
      font-size: 14px;
    }

    /* 响应式调整 */
    @media (max-width: 768px) {
      .real-time-data {
        font-size: 10px;
        padding: 6px 10px;
      }
      
      .real-time-line {
        gap: 8px;
      }
      
      .rt-label {
        min-width: 70px;
        font-size: 10px;
      }
      
      .rt-item {
        margin-right: 8px;
        font-size: 10px;
      }
      
      .rt-separator {
        margin: 0 8px;
        font-size: 12px;
      }
    }

    /* K线图响应式设计 */
    @media (max-width: 768px) {
      #klineChart {
        height: 300px !important;
        padding: 6px;
      }
      
      #klineLimit {
        font-size: 10px;
        padding: 3px 6px;
        min-width: 80px;
      }
      
      .card-header .float-end {
        margin-top: -2px;
      }

      .data-content {
        flex-direction: column;
        gap: 4px;
      }
      
      .data-item {
        min-width: 100%;
        text-align: left;
      }
    }

    @media (max-width: 576px) {
      #klineChart {
        height: 250px !important;
        padding: 4px;
      }
    }
  </style>
</head>
<body>
  <div class="container">
    <div class="d-flex flex-wrap justify-content-between align-items-center my-3 gap-2">
      <div class="d-flex align-items-baseline gap-2">
        <h3 class="mb-0">兑复币安合约自动交易系统</h3>
        <span style="font-size: 10px; color: var(--mist-gray);">兑复相生 财富自来 Powered by 无为</span>
      </div>
      <div id="sysline" class="text-muted"></div>
    </div>
    <!-- K线图和BOLL指标显示区域 -->
    <div class="row g-3 mt-2">
      <div class="col-12">
        <div class="card">
          <div class="card-header">
            K线图 & BOLL指标
            <div class="float-end">
              <select id="klineLimit" class="form-select form-select-sm" style="width: auto; display: inline-block;">
                <option value="50">50根K线</option>
                <option value="100" selected>100根K线</option>
                <option value="200">200根K线</option>
                <option value="300">300根K线</option>
              </select>
            </div>
          </div>
          <div class="card-body">
            <!-- 实时K线和BOLL数据显示区域 -->
            <div id="realTimeData" class="real-time-data">
              <span class="rt-item">实时币价: <span id="rtRealTimePrice" class="rt-value" style="color: blue; font-weight: bold;">--</span></span>
              <span class="rt-separator">|</span>
              <span class="rt-label">实时K线数据</span>
              <span class="rt-item">开: <span id="rtOpen" class="rt-value">--</span></span>
              <span class="rt-item">高: <span id="rtHigh" class="rt-value">--</span></span>
              <span class="rt-item">低: <span id="rtLow" class="rt-value">--</span></span>
              <span class="rt-item">收: <span id="rtClose" class="rt-value">--</span></span>
              <span class="rt-separator">|</span>
              <span class="rt-label">BOLL指标</span>
              <span class="rt-item">UP: <span id="rtBollUpper" class="rt-value boll-upper">--</span></span>
              <span class="rt-item">MB: <span id="rtBollMiddle" class="rt-value">--</span></span>
              <span class="rt-item">DN: <span id="rtBollLower" class="rt-value boll-lower">--</span></span>
            </div>
            <div id="klineChart" style="height: 200px; position: relative;">
              <canvas id="klineCanvas"></canvas>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- 其他卡片区域 -->
    <div class="row g-3">
      <div class="col-md-6">
        <div class="card">
          <div class="card-header">配置</div>
          <div class="card-body">
            <div class="config-item">
              <span class="config-key">交易币对:</span>
              <span class="config-value">{{ cfg.SYMBOL }}</span>
            </div>
            <div class="config-item">
              <span class="config-key">K 线周期:</span>
              <span class="config-value">{{ cfg.INTERVAL }}</span>
            </div>
            <div class="config-item">
              <span class="config-key">BOLL:</span>
              <span class="config-value">P={{ cfg.BOLL_PERIOD }} STD={{ cfg.BOLL_STD }}</span>
            </div>
            <div class="config-item">
              <span class="config-key">保证金余额:</span>
              <span class="config-value"><span id="balance">加载中...</span> USDT</span>
            </div>
            <div class="config-item">
              <span class="config-key">默认买入仓位:</span>
              <span class="config-value">{{ cfg.TRADE_PERCENT * 100 }}% </span>
            </div>
            <div class="config-item">
              <span class="config-key">杠杆:</span>
              <span class="config-value">{{ cfg.LEVERAGE }}X</span>
            </div>

            <div class="config-item">
              <span class="config-key">手续费率:</span>
              <span class="config-value">{{ (cfg.FEE_RATE * 100) | round(3) }}%</span>
            </div>
          </div>
        </div>
      </div>
      <div class="col-md-6">
        <div class="card">
          <div class="card-header">持仓</div>
          <div class="card-body" id="pos">加载中...</div>
        </div>
      </div>
      <div class="col-md-6">
        <div class="card">
          <div class="card-header">实时币价 | {{ cfg.INTERVAL }}收盘BOLL</div>
          <div class="card-body" id="price_boll">加载中...</div>
        </div>
      </div>
      <div class="col-md-6">
        <div class="card">
          <div class="card-header">盈利</div>
          <div class="card-body">
            <table class="table table-sm">
              <thead>
                <tr><th>日期</th><th>交易总次数</th><th>亏损次数</th><th>盈利次数</th><th>手续费</th><th>总盈利</th><th>利润率</th></tr>
              </thead>
              <tbody id="profits"></tbody>
            </table>
          </div>
        </div>
      </div>
      <div class="col-md-6">
        <div class="card">
          <div class="card-header">交易记录</div>
          <div class="card-body">
            <ul id="trades" class="list-group list-group-flush"></ul>
          </div>
        </div>
      </div>
      <div class="col-md-6">
        <div class="card">
          <div class="card-header">系统日志</div>
          <div class="card-body"><div id="logs" class="log">加载中...</div></div>
        </div>
      </div>
    </div>

<<<<<<< HEAD
    <!-- K线图和BOLL指标显示区域 -->
    <div class="row g-3 mt-2">
      <div class="col-12">
        <div class="card">
          <div class="card-header">
            K线图 & BOLL指标
            <div class="float-end">
              <select id="klineLimit" class="form-select form-select-sm" style="width: auto; display: inline-block;">
                <option value="50">50根K线</option>
                <option value="100" selected>100根K线</option>
                <option value="200">200根K线</option>
                <option value="300">300根K线</option>
              </select>
            </div>
          </div>
          <div class="card-body">
            <!-- 实时K线和BOLL数据显示区域 -->
            <div id="realTimeData" class="real-time-data">
              <span class="rt-item">实时币价: <span id="rtRealTimePrice" class="rt-value" style="color: blue; font-weight: bold;">--</span></span>
              <span class="rt-separator">|</span>
              <span class="rt-label">实时K线数据</span>
              <span class="rt-item">开: <span id="rtOpen" class="rt-value">--</span></span>
              <span class="rt-item">高: <span id="rtHigh" class="rt-value">--</span></span>
              <span class="rt-item">低: <span id="rtLow" class="rt-value">--</span></span>
              <span class="rt-item">收: <span id="rtClose" class="rt-value">--</span></span>
              <span class="rt-separator">|</span>
              <span class="rt-label">BOLL指标</span>
              <span class="rt-item">UP: <span id="rtBollUpper" class="rt-value boll-upper">--</span></span>
              <span class="rt-item">MB: <span id="rtBollMiddle" class="rt-value">--</span></span>
              <span class="rt-item">DN: <span id="rtBollLower" class="rt-value boll-lower">--</span></span>
            </div>
          </div>
            <div id="klineChart" style="height: 200px; position: relative;">
              <canvas id="klineCanvas"></canvas>
            </div>
          </div>
        </div>
      </div>
    </div>

=======
>>>>>>> 7723a39d6b744b5c2458478aedd88d9ee1748bad

  </div>
<script>
// 改进的fetchJSON函数，增加错误处理和重试机制
async function fetchJSON(url, retries = 3) {
  for (let i = 0; i < retries; i++) {
    try {
      const response = await fetch(url, { 
        timeout: 5000,
        headers: {
          'Cache-Control': 'no-cache'
        }
      });
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      }
      return await response.json();
    } catch (error) {
      console.warn(`API调用失败 (${url}), 尝试 ${i + 1}/${retries}:`, error.message);
      if (i === retries - 1) {
        throw error;
      }
      // 等待一段时间后重试
      await new Promise(resolve => setTimeout(resolve, 1000 * (i + 1)));
    }
  }
}

function fmt2(v){ return Number(v).toFixed(2); }

let current_price = 0;
let current_price_open = 0;
let current_boll = {boll_up: 0, boll_mid: 0, boll_dn: 0};

function updatePriceAndBoll() {
  const pbDiv = document.getElementById('price_boll');
  if (current_price && current_price > 0) {
    // 判断币价与轨道的关系
    let priceClass = '';
    if (current_price > current_boll.boll_up) {
      priceClass = 'price-above-upper';
    } else if (current_price < current_boll.boll_dn) {
      priceClass = 'price-below-lower';
    }
    
    // 计算当天涨跌幅
    let changePercent = 0;
    let changeClass = '';
    let changeText = '';
    if (current_price_open && current_price_open > 0) {
      changePercent = ((current_price - current_price_open) / current_price_open) * 100;
      if (changePercent > 0) {
        changeClass = 'text-success';
        changeText = `+${changePercent.toFixed(4)}%`;
      } else if (changePercent < 0) {
        changeClass = 'text-danger';
        changeText = `${changePercent.toFixed(4)}%`;
      } else {
        changeClass = 'text-muted';
        changeText = '0.0000%';
      }
    } else {
      changeText = '无数据';
      changeClass = 'text-muted';
    }
    
    // 获取当前时间
    const now = new Date();
    const timeStr = now.toLocaleTimeString('zh-CN', { hour12: false });
    
    pbDiv.innerHTML = `
      <div>实时币价: <span class="${priceClass}">${fmt2(current_price)}</span></div>
      <div>当天开盘价: <span class="price-open">${fmt2(current_price_open)}</span> 当天涨跌幅: <span class="${changeClass}">${changeText}</span></div>
      <div>BOLL 上轨: <span class="boll-upper">${fmt2(current_boll.boll_up)}</span></div>
      <div>BOLL 中轨: ${fmt2(current_boll.boll_mid)}</div>
      <div>BOLL 下轨: <span class="boll-lower">${fmt2(current_boll.boll_dn)}</span></div>
      <div>BOLL 同步时间: ${timeStr}</div>
    `;
    
    // 同时更新实时数据区域的币价显示
    const realTimePriceElement = document.getElementById('rtRealTimePrice');
    if (realTimePriceElement) {
      realTimePriceElement.textContent = Number(current_price).toFixed(4);
    }
  } else {
    pbDiv.innerText = '加载中...';
  }
}

// 定期获取价格和BOLL数据
async function fetchPriceAndBoll() {
  try {
    const data = await fetchJSON('/api/price_and_boll');
    if (data && data.price && data.price > 0) {
      current_price = data.price;
      current_price_open = data.price_open || 0;
      current_boll = {
        boll_up: data.boll_up || 0,
        boll_mid: data.boll_mid || 0,
        boll_dn: data.boll_dn || 0
      };
      updatePriceAndBoll();
    } else {
      console.warn('价格数据无效:', data);
    }
  } catch (e) {
    console.error('获取价格数据失败:', e);
    // 保持当前显示，不更新为"加载中..."
  }
}

async function refresh(){
  // 系统信息 - 标题行一行展示
  try {
    const sys = await fetchJSON('/api/system');
    if (sys) {
      // 判断是否需要警告颜色
      const cpuClass = sys.cpu > 80 ? 'sys-warning' : '';
      const memClass = sys.mem > 85 ? 'sys-warning' : '';
      const diskClass = sys.disk > 90 ? 'sys-warning' : '';
      
      const sysLine = `CPU <span class="${cpuClass}">${sys.cpu}%</span> | C${sys.cpu_cores} | MEM<span class="${memClass}">${sys.mem}%</span> (${sys.mem_total_mb}M/${sys.mem_available_mb}M) | Disk<span class="${diskClass}">${sys.disk}%</span> (${sys.disk_total_gb}G/${sys.disk_free_gb}G)`;
      const sysEl = document.getElementById('sysline');
      if (sysEl) sysEl.innerHTML = sysLine;
    }
  } catch (e) {
    console.error('获取系统信息失败:', e);
  }

  // 获取实时余额
  try {
    const balanceData = await fetchJSON('/api/balance');
    if (balanceData && typeof balanceData.balance !== 'undefined') {
      const balanceEl = document.getElementById('balance');
      if (balanceEl) balanceEl.innerText = fmt2(balanceData.balance);
    }
  } catch (e) {
    console.error('获取余额失败:', e);
    const balanceEl = document.getElementById('balance');
    if (balanceEl && balanceEl.innerText === '加载中...') {
      balanceEl.innerText = '获取失败';
    }
  }

  // positions (multi-symbol)
  try {
    const posData = await fetchJSON('/api/positions');
    const posDiv = document.getElementById('pos');
    if (!posData || !posData.items || posData.items.length === 0) { 
      posDiv.innerText = '无持仓'; 
    } else {
      let parts = [];
      for (const p of posData.items){
         const sideClass = p.side.toLowerCase() === 'long' ? 'position-long' : 'position-short';
         // 强平价格颜色：short=绿色，long=红色
         const liquidationClass = p.side.toLowerCase() === 'short' ? 'text-success' : 'text-danger';
         parts.push(
           `<div class="mb-2">
             <div class="position-item">
               <span class="position-key">方向:</span>
               <span class="position-value"><span class="${sideClass}">${p.side}</span></span>
             </div>
             
             <div class="position-item">
               <span class="position-key">持仓金额:</span>
               <span class="position-value">${fmt2(p.qty_usdt)} USDT</span>
             </div>
             <div class="position-item">
               <span class="position-key">数量:</span>
               <span class="position-value">${(Math.abs(p.qty_usdt) / p.entry_price).toFixed(4)}</span>
             </div>
             <div class="position-item">
               <span class="position-key">开仓价格:</span>
               <span class="position-value">${fmt2(p.entry_price)}</span>
             </div>
             <div class="position-item">
               <span class="position-key">保证金:</span>
               <span class="position-value">${fmt2(p.open_amount)} USDT</span>
             </div>
             <div class="position-item">
               <span class="position-key">未实现盈亏:</span>
               <span class="position-value ${p.unrealized_pnl >= 0 ? 'text-success' : 'text-danger'}">${fmt2(p.unrealized_pnl)} USDT</span>
             </div>
             <div class="position-item">
               <span class="position-key">强平价格:</span>
               <span class="position-value ${liquidationClass}">${fmt2(p.liquidation_price)}</span>
             </div>
           </div>`
         );
      }
      posDiv.innerHTML = parts.join('<hr class="my-2">');
    }
  } catch (e) {
    console.error('获取持仓失败:', e);
    const posDiv = document.getElementById('pos');
    if (posDiv && posDiv.innerText === '加载中...') {
      posDiv.innerText = '获取失败';
    }
  }

  // 交易记录
  try {
    const trades = await fetchJSON('/api/trades');
    if (trades && Array.isArray(trades)) {
      const ul = document.getElementById('trades'); 
      ul.innerHTML='';
      trades.forEach(t=>{ 
        const li = document.createElement('li'); 
        li.className='list-group-item';
        if (t.text && t.text.includes('平仓')) { li.classList.add('trade-close'); }
        li.innerHTML = t.text || ''; 
        ul.appendChild(li); 
      });
    }
  } catch (e) {
    console.error('获取交易记录失败:', e);
  }

  // 系统日志
  try {
    const logs = await fetch('/api/logs');
    if (logs.ok) {
      let logText = await logs.text();
      
      // 为止损和止盈日志添加颜色标识
      logText = logText.replace(/(.*止损.*)/g, '<span class="log-stop-loss">$1</span>');
      logText = logText.replace(/(.*止盈.*)/g, '<span class="log-take-profit">$1</span>');
      
      // 为状态添加颜色标识
      logText = logText.replace(/(.*holding_long.*)/g, '<span class="log-holding-long">$1</span>');
      logText = logText.replace(/(.*holding_short.*)/g, '<span class="log-holding-short">$1</span>');
      logText = logText.replace(/(.*waiting.*)/g, '<span class="log-waiting">$1</span>');
      
      // 为突破信息添加颜色标识
      logText = logText.replace(/(.*收盘价突破.*)/g, '<span class="log-breakout">$1</span>');
      logText = logText.replace(/(.*收盘价跌破.*)/g, '<span class="log-breakout">$1</span>');
      
      document.getElementById('logs').innerHTML = logText;
    }
  } catch (e) {
    console.error('获取日志失败:', e);
  }

  // 盈利统计 - 使用新的汇总API
  try {
    const profits = await fetchJSON('/api/profits_summary');
    if (profits && Array.isArray(profits)) {
      const profitsBody = document.getElementById('profits');
      profitsBody.innerHTML = '';
      
      // 只显示前3行数据（汇总、当天、昨天）
      const displayData = profits.slice(0, 3);
      
      displayData.forEach((p, index) => {
        const tr = document.createElement('tr');
        
        // 汇总行使用特殊样式
        if (index === 0) {
          tr.style.backgroundColor = 'var(--cloud-white)';
          tr.style.fontWeight = '600';
        }
        
        const dateTd = document.createElement('td'); 
        dateTd.textContent = p.date || ''; 
        tr.appendChild(dateTd);
        
        const countTd = document.createElement('td'); 
        countTd.textContent = p.trade_count || 0; 
        tr.appendChild(countTd);
        
        const lossCountTd = document.createElement('td'); 
        lossCountTd.textContent = p.loss_count || 0; 
        lossCountTd.className = 'text-danger'; 
        tr.appendChild(lossCountTd);
        
        const profitCountTd = document.createElement('td'); 
        profitCountTd.textContent = p.profit_count || 0;
        profitCountTd.className = 'text-success'; 
        tr.appendChild(profitCountTd);
        
        const feesTd = document.createElement('td'); 
        feesTd.textContent = fmt2(p.total_fees || 0);
        feesTd.className = 'text-danger'; 
        tr.appendChild(feesTd);
        
        const profitTd = document.createElement('td'); 
        profitTd.textContent = fmt2(p.profit || 0);
        profitTd.className = (p.profit || 0) >= 0 ? 'text-success' : 'text-danger'; 
        tr.appendChild(profitTd);
        
        const rateTd = document.createElement('td'); 
        rateTd.textContent = fmt2(p.profit_rate || 0) + '%'; 
        tr.appendChild(rateTd);
        
        profitsBody.appendChild(tr);
      });
    }
  } catch (e) {
    console.error('获取盈利统计失败:', e);
  }
  
  // 更新价格和BOLL数据
  await fetchPriceAndBoll();
  
  // 更新K线图
  await updateKlineChart();
}

// K线图相关变量和函数
let klineChart = null;
let klineData = [];

// 初始化K线图
function initKlineChart() {
  const ctx = document.getElementById('klineCanvas').getContext('2d');
  
  klineChart = new Chart(ctx, {
    type: 'candlestick',
    data: {
      datasets: [
        {
          label: 'K线',
          data: [],
          borderColor: 'var(--ink-black)',
          backgroundColor: 'var(--ink-black)',
          borderWidth: 1,
          color: {
            up: 'var(--bamboo-green)',
            down: 'var(--sunset-red)',
            unchanged: 'var(--mist-gray)'
          },
          borderColor: {
            up: 'var(--bamboo-green)',
            down: 'var(--sunset-red)',
            unchanged: 'var(--mist-gray)'
          }
        },
        {
          label: 'BOLL上轨',
          type: 'line',
          data: [],
          borderColor: '#1890ff',
          backgroundColor: 'transparent',
          borderWidth: 1,
          pointRadius: 0,
          fill: false
        },
        {
          label: 'BOLL中轨',
          type: 'line',
          data: [],
          borderColor: '#1890ff',
          backgroundColor: 'transparent',
          borderWidth: 1,
          pointRadius: 0,
          fill: false
        },
        {
          label: 'BOLL下轨',
          type: 'line',
          data: [],
          borderColor: '#1890ff',
          backgroundColor: 'transparent',
          borderWidth: 1,
          pointRadius: 0,
          fill: false
        }
      ]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: {
        intersect: false,
        mode: 'index'
      },
      plugins: {
        legend: {
          display: false
        },
        tooltip: {
          enabled: true,
          mode: 'index',
          intersect: false,
          backgroundColor: 'rgba(255, 255, 255, 0.95)',
          titleColor: '#2c3e50',
          bodyColor: '#34495e',
          borderColor: '#95a5a6',
          borderWidth: 1,
          cornerRadius: 6,
          displayColors: true,
          callbacks: {
            title: function(context) {
              if (context && context.length > 0) {
                return context[0].label || 'N/A';
              }
              return 'N/A';
            },
            label: function(context) {
              const dataset = context.dataset;
              const dataPoint = context.raw;
              
              // K线数据显示
              if (dataset && dataset.label === 'K线') {
                if (dataPoint && typeof dataPoint === 'object') {
                  const o = dataPoint.o;
                  const h = dataPoint.h;
                  const l = dataPoint.l;
                  const c = dataPoint.c;
                  
                  if (o !== undefined && h !== undefined && l !== undefined && c !== undefined) {
                    return `K线: 开盘 ${Number(o).toFixed(2)} 最高 ${Number(h).toFixed(2)} 最低 ${Number(l).toFixed(2)} 收盘 ${Number(c).toFixed(2)}`;
                  }
                }
                return 'K线: [数据加载中]';
              }
              
              // BOLL线数据显示
              if (dataset && dataset.label && dataPoint && dataPoint.y !== undefined) {
                return `${dataset.label}: ${Number(dataPoint.y).toFixed(2)}`;
              }
              
              return `${dataset ? dataset.label : 'Unknown'}: 无数据`;
            }
          }
        }
      },
      scales: {
        x: {
          type: 'time',
          time: {
            unit: 'hour',
            displayFormats: {
              hour: 'MM-dd HH:mm'
            }
          },
          display: true,
          grid: {
            color: 'rgba(151, 165, 166, 0.1)'
          },
          ticks: {
            font: {
              size: 10
            },
            color: 'var(--ink-gray)',
            maxTicksLimit: 10
          }
        },
        y: {
          display: true,
          position: 'right',
          grid: {
            color: 'rgba(151, 165, 166, 0.1)'
          },
          ticks: {
            font: {
              size: 10
            },
            color: 'var(--ink-gray)',
            callback: function(value) {
              return Number(value).toFixed(4);
            }
          }
        }
      },
      elements: {
        point: {
          hoverBackgroundColor: 'var(--mountain-blue)'
        }
      }
    }
  });
}

// 获取K线数据并更新图表
async function updateKlineChart() {
  try {
    const limit = document.getElementById('klineLimit').value || 50;
    const data = await fetchJSON(`/api/kline_data?limit=${limit}`);
    
    if (data && data.klines && data.boll && Array.isArray(data.klines) && Array.isArray(data.boll)) {
      klineData = data.klines;
      const bollData = data.boll;
      
      // 准备蜡烛图数据
      const candlestickData = klineData.map(k => ({
        x: k.time,
        o: k.open,
        h: k.high,
        l: k.low,
        c: k.close
      }));
      
      // 准备BOLL数据 - 使用时间戳作为x轴
      const bollUpper = bollData.map(b => ({ x: b.time, y: b.upper }));
      const bollMiddle = bollData.map(b => ({ x: b.time, y: b.middle }));
      const bollLower = bollData.map(b => ({ x: b.time, y: b.lower }));
      
      // 更新图表数据
      if (klineChart) {
        klineChart.data.datasets[0].data = candlestickData;
        klineChart.data.datasets[1].data = bollUpper;
        klineChart.data.datasets[2].data = bollMiddle;
        klineChart.data.datasets[3].data = bollLower;
        klineChart.update('none'); // 无动画更新
      }

      // 更新实时数据显示
      updateRealTimeData(klineData, bollData);
    } else {
      console.warn('K线数据或BOLL数据无效:', data);
    }
  } catch (e) {
    console.error('获取K线数据失败:', e);
  }
}

// 更新实时数据显示
function updateRealTimeData(klineData, bollData) {
  if (!klineData || !bollData || klineData.length === 0 || bollData.length === 0) {
    return;
  }

  // 获取最新的K线数据（最后一根K线）
  const latestKline = klineData[klineData.length - 1];
  const latestBoll = bollData[bollData.length - 1];

  // 更新实时币价（使用全局变量current_price，如果没有则使用最新K线收盘价）
  const realTimePriceElement = document.getElementById('rtRealTimePrice');
  if (realTimePriceElement) {
    const displayPrice = (current_price && current_price > 0) ? current_price : (latestKline ? latestKline.close : 0);
    if (displayPrice > 0) {
      realTimePriceElement.textContent = Number(displayPrice).toFixed(4);
    } else {
      realTimePriceElement.textContent = '--';
    }
  }

  if (latestKline) {
    // 更新K线数据
    document.getElementById('rtOpen').textContent = Number(latestKline.open).toFixed(4);
    document.getElementById('rtHigh').textContent = Number(latestKline.high).toFixed(4);
    document.getElementById('rtLow').textContent = Number(latestKline.low).toFixed(4);
    document.getElementById('rtClose').textContent = Number(latestKline.close).toFixed(4);
  }

  if (latestBoll) {
    // 更新BOLL数据
    document.getElementById('rtBollUpper').textContent = Number(latestBoll.upper).toFixed(4);
    document.getElementById('rtBollMiddle').textContent = Number(latestBoll.middle).toFixed(4);
    document.getElementById('rtBollLower').textContent = Number(latestBoll.lower).toFixed(4);
  }
}

// K线数量选择器事件监听
document.addEventListener('DOMContentLoaded', function() {
  // 初始化K线图
  initKlineChart();
  
  // 监听K线数量选择器变化
  const klineLimitSelect = document.getElementById('klineLimit');
  if (klineLimitSelect) {
    klineLimitSelect.addEventListener('change', function() {
      updateKlineChart();
    });
  }
});

// 初始化Socket.IO连接
const socket = io();

// 监听实时价格更新
socket.on('price_update', function(data) {
  if (data && data.price) {
    // 更新全局价格变量
    current_price = data.price;
    
    // 立即更新实时价格显示
    const realTimePriceElement = document.getElementById('rtRealTimePrice');
    if (realTimePriceElement) {
      realTimePriceElement.textContent = Number(data.price).toFixed(4);
    }
    
    // 更新价格和BOLL显示
    updatePriceAndBoll();
  }
});

// 连接状态监听
socket.on('connect', function() {
  console.log('Socket.IO连接已建立');
});

socket.on('disconnect', function() {
  console.log('Socket.IO连接已断开');
});

// 减少轮询频率，主要用于其他数据更新（非价格数据）
setInterval(refresh, 10000); // 改为10秒更新一次其他数据
refresh();
</script>
</body>
</html>
"""


@app.route("/")
def index():
    return render_template_string(TEMPLATE, cfg=config)


@app.get("/api/system")
def api_system():
    vm = psutil.virtual_memory()
    du = psutil.disk_usage("/")
    return jsonify({
        "cpu": psutil.cpu_percent(interval=None),
        "cpu_cores": psutil.cpu_count(logical=True),
        "mem": vm.percent,
        "mem_total_mb": int(vm.total / (1024 * 1024)),
        "mem_available_mb": int(vm.available / (1024 * 1024)),
        "disk": du.percent,
        "disk_total_gb": round(du.total / (1024 * 1024 * 1024), 1),
        "disk_free_gb": round(du.free / (1024 * 1024 * 1024), 1),
    })


# 兼容旧接口（单一文本）
@app.get("/api/position")
def api_position_compat():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT symbol, side, qty, entry_price, ts FROM positions LIMIT 1")
    row = cur.fetchone()
    conn.close()
    if not row:
        return jsonify({"text": "无持仓"})
    side = row["side"].lower()
    side_text = "long" if side == "long" else ("short" if side == "short" else side)
    open_time = fmt_ts_utc8(row['ts'])
    text = f"{row['symbol']} {side_text} | 开仓时间: {open_time} | 金额: {row['qty']:.2f} | 价格: {row['entry_price']:.2f}"
    return jsonify({"text": text})


# 多交易币对持仓列表
@app.get("/api/positions")
def api_positions():
    items = []
    
    # 优先从实际API获取持仓信息
    if hasattr(app, 'engine_instance') and app.engine_instance and app.engine_instance.trader:
        try:
            api_positions = app.engine_instance.trader.get_positions()
            for pos in api_positions:
                symbol = pos.get('symbol', '')
                position_amt = float(pos.get('positionAmt', 0))
                entry_price = float(pos.get('entryPrice', 0))
                unrealized_pnl = float(pos.get('unRealizedProfit', 0))
                liquidation_price = float(pos.get('liquidationPrice', 0))
                
                # 确定持仓方向
                side = 'long' if position_amt > 0 else 'short'
                # 数量显示为USDT计价（持仓数量 * 入场价格）
                qty_usdt = position_amt * entry_price
                
                # 计算保证金（数量 * 价格 / 杠杆）
                open_amount = (abs(position_amt) * entry_price) / config.LEVERAGE if config.LEVERAGE > 0 else abs(position_amt) * entry_price
                
                items.append({
                    'symbol': symbol,
                    'side': side,
                    'qty_usdt': qty_usdt,
                    'entry_price': entry_price,
                    'open_amount': open_amount,
                    'unrealized_pnl': unrealized_pnl,
                    'liquidation_price': liquidation_price,
                })
        except Exception as e:
            print(f"获取API持仓失败: {e}")
    
    # 如果没有API持仓或获取失败，从数据库获取
    if not items:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("SELECT symbol, side, qty, entry_price, ts FROM positions ORDER BY symbol ASC")
        rows = [dict(r) for r in cur.fetchall()]
        
        # 预取各symbol最新价格
        latest = {}
        for r in rows:
            cur.execute("SELECT close FROM klines WHERE symbol=? AND interval=? ORDER BY open_time DESC LIMIT 1", (r['symbol'], config.INTERVAL))
            k = cur.fetchone()
            latest[r['symbol']] = float(k['close']) if k else r['entry_price']
        
        # 计算
        for r in rows:
            side_raw = (r['side'] or '').lower()
            side = 'long' if side_raw == 'long' else ('short' if side_raw == 'short' else side_raw)
            last_price = latest.get(r['symbol'], r['entry_price'])
            qty = float(r['qty'])
            entry = float(r['entry_price'])
            
            # 未实现盈亏
            if side == 'long':
                unrealized = (last_price - entry) * qty
            elif side == 'short':
                unrealized = (entry - last_price) * qty
            else:
                unrealized = 0.0
            
            # 已实现盈亏（基于trades.pnl汇总，若未维护则为0）
            cur.execute("SELECT COALESCE(SUM(pnl),0) AS s FROM trades WHERE symbol=?", (r['symbol'],))
            realized = float(cur.fetchone()['s'])
            
            items.append({
                'symbol': r['symbol'],
                'side': side,
                'qty': qty,
                'entry_price': entry,
                'open_amount': qty * entry,
                'open_time': fmt_ts_utc8(r['ts']),
                'unrealized_pnl': unrealized,
                'realized_pnl': realized,
            })
        conn.close()
    
    return jsonify({'items': items})


@app.route('/api/profits')
def api_profits():
    profits = get_daily_profits()
    return jsonify(profits)

@app.route('/api/profits_summary')
def api_profits_summary():
    """获取累计汇总数据和最近3天的盈利数据"""
    from datetime import datetime, timedelta
    
    conn = get_conn()
    cur = conn.cursor()
    
    # 直接从trades表计算累计汇总数据（计算所有平仓交易：CLOSE_LONG和CLOSE_SHORT）
    cur.execute("""
        SELECT 
            COUNT(*) as total_trade_count,
            SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) as total_profit_count,
            SUM(CASE WHEN pnl < 0 THEN 1 ELSE 0 END) as total_loss_count,
            COALESCE(SUM(pnl), 0) as total_profit
        FROM trades 
        WHERE side IN ('CLOSE_LONG', 'CLOSE_SHORT')
    """)
    summary_row = cur.fetchone()
    
    # 计算所有交易的总手续费（包括开仓和平仓）
    cur.execute("""
        SELECT COALESCE(SUM(fee), 0) as all_fees
        FROM trades
    """)
    all_fees_row = cur.fetchone()
    
    # 获取初始余额（从第一条记录或使用默认值）
    cur.execute("SELECT initial_balance FROM daily_profits WHERE initial_balance > 0 ORDER BY date ASC LIMIT 1")
    initial_balance_row = cur.fetchone()
    initial_balance = initial_balance_row['initial_balance'] if initial_balance_row else 40.0
    
    # 计算总净利润（总盈亏 - 所有手续费），与每日数据计算逻辑保持一致
    total_net_profit = (summary_row['total_profit'] or 0.0) - (all_fees_row['all_fees'] or 0.0)
    
    # 计算总利润率（使用净利润）
    total_profit_rate = (total_net_profit / initial_balance * 100) if initial_balance > 0 else 0.0
    
    # 获取当天日期
    today = datetime.now().strftime('%Y-%m-%d')
    
    # 计算交易天数：从第一次交易到当前日期的天数
    cur.execute("SELECT MIN(ts) as first_trade_ts FROM trades")
    first_trade_row = cur.fetchone()
    
    if first_trade_row and first_trade_row['first_trade_ts']:
        # 将时间戳转换为日期
        first_trade_date = datetime.fromtimestamp(first_trade_row['first_trade_ts'] / 1000).date()
        current_date = datetime.now().date()
        # 计算天数差
        trading_days = (current_date - first_trade_date).days + 1  # +1 包含第一天
        summary_title = f'{trading_days} 天交易汇总'
    else:
        # 如果没有交易记录，显示默认格式
        summary_title = f'汇总({today})'
    
    # 构建汇总数据
    summary_data = {
        'date': summary_title,
        'trade_count': summary_row['total_trade_count'] or 0,
        'profit_count': summary_row['total_profit_count'] or 0,
        'loss_count': summary_row['total_loss_count'] or 0,
        'total_fees': all_fees_row['all_fees'] or 0.0,
        'profit': total_net_profit,
        'profit_rate': total_profit_rate,
        'initial_balance': initial_balance
    }
    
    # 获取实际有交易记录的日期（最多显示最近2天）
    cur.execute("""
        SELECT DISTINCT DATE(datetime(ts/1000 + 8*3600, 'unixepoch')) as trade_date
        FROM trades 
        ORDER BY trade_date DESC
        LIMIT 2
    """)
    
    trade_dates = [row['trade_date'] for row in cur.fetchall()]
    
    recent_profits = []
    for date_str in trade_dates:
        # 统计该日期的平仓交易数据（交易次数只计算平仓：CLOSE_LONG和CLOSE_SHORT）
        cur.execute("""
            SELECT 
                COUNT(*) as close_count,
                SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) as profit_count,
                SUM(CASE WHEN pnl < 0 THEN 1 ELSE 0 END) as loss_count,
                COALESCE(SUM(fee), 0) as close_fees,
                COALESCE(SUM(pnl), 0) as profit
            FROM trades 
            WHERE side IN ('CLOSE_LONG', 'CLOSE_SHORT') AND DATE(datetime(ts/1000 + 8*3600, 'unixepoch')) = ?
        """, (date_str,))
        
        close_row = cur.fetchone()
        
        # 统计该日期的所有交易手续费（包括开仓和平仓）
        cur.execute("""
            SELECT COALESCE(SUM(fee), 0) as total_fees
            FROM trades 
            WHERE DATE(datetime(ts/1000 + 8*3600, 'unixepoch')) = ?
        """, (date_str,))
        
        all_fees_row = cur.fetchone()
        
        # 交易次数、盈利次数、亏损次数只计算平仓交易
        trade_count = close_row['close_count'] or 0
        profit_count = close_row['profit_count'] or 0
        loss_count = close_row['loss_count'] or 0
        
        # 手续费包括所有交易（开仓+平仓）
        total_fees = all_fees_row['total_fees'] or 0.0
        
        # 盈亏只来自平仓交易
        profit = close_row['profit'] or 0.0
        
        # 获取该日期的初始余额和利润率（从daily_profits表）
        cur.execute("""
            SELECT initial_balance, profit_rate 
            FROM daily_profits 
            WHERE date = ?
        """, (date_str,))
        
        daily_row = cur.fetchone()
        initial_balance = daily_row['initial_balance'] if daily_row else 40.0
        
        # 计算净利润（总盈亏 - 手续费）
        net_profit = profit - total_fees
        
        # 计算利润率（使用净利润）
        profit_rate = (net_profit / initial_balance * 100) if initial_balance > 0 else 0.0
        
        recent_profits.append({
            'date': date_str,
            'trade_count': trade_count,
            'profit_count': profit_count,
            'loss_count': loss_count,
            'total_fees': total_fees,
            'profit': net_profit,
            'profit_rate': profit_rate,
            'initial_balance': initial_balance
        })
    
    conn.close()
    
    # 返回汇总数据和最近数据
    result = [summary_data] + recent_profits
    return jsonify(result)

@app.route('/api/engine_status')
def api_engine_status():
    """获取 Engine 实例的实时状态"""
    try:
        if hasattr(app, 'engine_instance') and app.engine_instance:
            eng = app.engine_instance
            return jsonify({
                'connected': True,
                'last_price': eng.last_price,
                'state': eng.state,
                'prices_count': len(eng.prices),
                'recent_prices': list(eng.prices)[-5:] if eng.prices else []
            })
        else:
            return jsonify({
                'connected': False,
                'last_price': 0,
                'state': 'unknown',
                'prices_count': 0,
                'recent_prices': []
            })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/price_and_boll')
def api_price_and_boll():
    try:
        # 获取当天开盘价（当天00:00的开盘价）
        today_open_price = 0
        try:
            from datetime import datetime, timezone, timedelta
            # 获取当天00:00的时间戳（UTC+8）
            now = datetime.now(timezone(timedelta(hours=8)))
            today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            today_start_ts = int(today_start.timestamp() * 1000)
            
            # 查询当天00:00附近的K线数据
            conn = get_conn()
            cursor = conn.cursor()
            cursor.execute("""
                SELECT open FROM klines 
                WHERE symbol = ? AND open_time >= ? 
                ORDER BY open_time ASC LIMIT 1
            """, (config.SYMBOL, today_start_ts))
            result = cursor.fetchone()
            if result:
                today_open_price = float(result[0])
            conn.close()
        except Exception as e:
            print(f"获取当天开盘价失败: {e}")
        
        # 优先使用 Engine 实例的实时数据
        if hasattr(app, 'engine_instance') and app.engine_instance:
            eng = app.engine_instance
            
            # 使用实时价格
            current_price = eng.last_price if eng.last_price > 0 else 0
            
            # 获取最新的 K 线数据并加入实时价格计算 BOLL
            rows = fetch_klines(config.SYMBOL, limit=config.BOLL_PERIOD)
            if len(rows) >= config.BOLL_PERIOD and current_price > 0:
                # 创建包含实时价格的数据框
                df = pd.DataFrame(rows)
                
                # 如果有实时价格，用实时价格替换最后一条记录的收盘价
                if len(df) > 0:
                    df.loc[df.index[-1], 'close'] = current_price
                    df.loc[df.index[-1], 'high'] = max(df.iloc[-1]['high'], current_price)
                    df.loc[df.index[-1], 'low'] = min(df.iloc[-1]['low'], current_price)
                
                # 计算实时 BOLL 指标
                mid, up, dn = bollinger_bands(df, config.BOLL_PERIOD, config.BOLL_STD, ddof=1)
                
                return jsonify({
                    'price': current_price,
                    'price_open': today_open_price,
                    'boll_up': float(up.iloc[-1]),
                    'boll_mid': float(mid.iloc[-1]),
                    'boll_dn': float(dn.iloc[-1])
                })
        
        # 回退到数据库数据
        rows = fetch_klines(config.SYMBOL, limit=config.BOLL_PERIOD + 1)
        if len(rows) < config.BOLL_PERIOD:
            return jsonify({
                'price': 0,
                'price_open': today_open_price,
                'boll_up': 0,
                'boll_mid': 0,
                'boll_dn': 0
            })
        
        # 计算 BOLL 指标
        df = pd.DataFrame(rows)
        mid, up, dn = bollinger_bands(df, config.BOLL_PERIOD, config.BOLL_STD, ddof=1)
        price = float(df['close'].iloc[-1])
        
        return jsonify({
            'price': price,
            'price_open': today_open_price,
            'boll_up': float(up.iloc[-1]),
            'boll_mid': float(mid.iloc[-1]),
            'boll_dn': float(dn.iloc[-1])
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/current_boll')
def api_current_boll():
    """获取当前BOLL值，用于自动微调程序"""
    try:
        # 优先使用 Engine 实例的实时数据
        if hasattr(app, 'engine_instance') and app.engine_instance:
            eng = app.engine_instance
            current_price = eng.last_price if eng.last_price > 0 else 0
            
            # 获取最新的 K 线数据并加入实时价格计算 BOLL
            rows = fetch_klines(config.SYMBOL, limit=config.BOLL_PERIOD)
            if len(rows) >= config.BOLL_PERIOD and current_price > 0:
                df = pd.DataFrame(rows)
                
                # 如果有实时价格，用实时价格替换最后一条记录的收盘价
                if len(df) > 0:
                    df.loc[df.index[-1], 'close'] = current_price
                    df.loc[df.index[-1], 'high'] = max(df.iloc[-1]['high'], current_price)
                    df.loc[df.index[-1], 'low'] = min(df.iloc[-1]['low'], current_price)
                
                # 计算实时 BOLL 指标
                mid, up, dn = bollinger_bands(df, config.BOLL_PERIOD, config.BOLL_STD, ddof=1)
                
                return jsonify({
                    'upper': float(up.iloc[-1]),
                    'middle': float(mid.iloc[-1]),
                    'lower': float(dn.iloc[-1]),
                    'timestamp': int(time.time() * 1000),
                    'period': config.BOLL_PERIOD,
                    'std': config.BOLL_STD
                })
        
        # 回退到数据库数据
        rows = fetch_klines(config.SYMBOL, limit=config.BOLL_PERIOD + 1)
        if len(rows) < config.BOLL_PERIOD:
            return jsonify({'error': 'K线数据不足'}), 400
        
        df = pd.DataFrame(rows)
        mid, up, dn = bollinger_bands(df, config.BOLL_PERIOD, config.BOLL_STD, ddof=1)
        
        return jsonify({
            'upper': float(up.iloc[-1]),
            'middle': float(mid.iloc[-1]),
            'lower': float(dn.iloc[-1]),
            'timestamp': int(time.time() * 1000),
            'period': config.BOLL_PERIOD,
            'std': config.BOLL_STD
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/update_boll_params', methods=['POST'])
def api_update_boll_params():
    """更新BOLL参数，用于自动微调程序"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'message': '请求数据为空'}), 400
        
        period = data.get('period')
        std = data.get('std')
        
        # 验证参数
        if period is None or std is None:
            return jsonify({'success': False, 'message': '缺少必要参数'}), 400
        
        try:
            period = int(period)
            std = float(std)
        except (ValueError, TypeError):
            return jsonify({'success': False, 'message': '参数类型错误'}), 400
        
        # 验证参数范围
        if not (10 <= period <= 50):
            return jsonify({'success': False, 'message': 'period必须在10-50之间'}), 400
        
        if not (0.5 <= std <= 5.0):
            return jsonify({'success': False, 'message': 'std必须在0.5-5.0之间'}), 400
        
        # 更新配置
        config.BOLL_PERIOD = period
        config.BOLL_STD = std
        
        # 如果有engine实例，也更新其配置
        if hasattr(app, 'engine_instance') and app.engine_instance:
            app.engine_instance.boll_period = period
            app.engine_instance.boll_std = std
        
        return jsonify({
            'success': True,
            'message': f'BOLL参数已更新: period={period}, std={std}',
            'period': period,
            'std': std
        })
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@app.get("/api/trades")
def api_trades():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT ts, side, qty, price, pnl, simulate, fee FROM trades ORDER BY ts DESC LIMIT 50")
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()

    def fmt(r):
        ts_str = fmt_ts_utc8(int(r['ts']))
        side = r['side']
        if side in ("BUY", "SELL"):
            action = "开仓"
            direction = "long" if side == "BUY" else "short"
        elif isinstance(side, str) and side.startswith("CLOSE"):
            action = "平仓"
            direction = side.split("_", 1)[-1].lower() if "_" in side else "-"
        else:
            action = side
            direction = "-"
        qty = float(r['qty'])
        price = float(r['price'])
        
        # 根据操作类型显示不同的金额信息
        if action == "开仓":
            # 开仓显示分配的交易保证金（按照engine.py中的逻辑）
            # 在engine.py中: margin = balance * TRADE_PERCENT, qty = margin * LEVERAGE / price
            # 所以: margin = qty * price / LEVERAGE (这就是分配给交易的保证金)
            margin = (qty * price) / config.LEVERAGE
            text = f"{ts_str} {action} 分配保证金: {margin:.2f} 方向: {direction} 价格: {price:.2f} 数量: {qty:.4f}"
            
            # 显示开仓手续费（如果有的话）
            if r.get('fee') is not None and r['fee'] > 0:
                fee = float(r['fee'])
                fee_text = f" <span class='trade-fee'>手续费: {fee:.2f}</span>"
                text += fee_text
                
        elif action == "平仓":
            # 平仓显示平仓收益和盈亏
            if r.get('pnl') is not None:
                pnl = float(r['pnl'])
                
                # 使用数据库中存储的实际手续费
                fee = float(r.get('fee', 0))
                
                # 计算保证金
                original_margin = (qty * price) / config.LEVERAGE
                
                # 平仓收益 = 保证金 + 盈亏 - 手续费
                close_amount = original_margin + pnl - fee
                
                text = f"{ts_str} {action} 收益: {close_amount:.2f} 方向: {direction} 价格: {price:.2f} 数量: {qty:.4f}"
                
                # 添加盈亏信息（原始盈亏，未减去手续费）
                if pnl > 0:
                    pnl_text = f" <span class='trade-profit'>盈利: {pnl:.2f}</span>"
                elif pnl < 0:
                    pnl_text = f" <span class='trade-loss'>亏损: {abs(pnl):.2f}</span>"
                else:
                    pnl_text = f" <span class='trade-neutral'>盈亏: 0.00</span>"
                
                # 添加手续费信息
                fee_text = f" <span class='trade-fee'>手续费: {fee:.2f}</span>"
                
                text += pnl_text + fee_text
            else:
                # 没有盈亏信息时，显示名义价值
                amount = qty * price
                text = f"{ts_str} {action} 名义价值: {amount:.2f} 方向: {direction} 价格: {price:.2f} 数量: {qty:.4f}"
                
                # 显示手续费（如果有的话）
                if r.get('fee') is not None and r['fee'] > 0:
                    fee = float(r['fee'])
                    fee_text = f" <span class='trade-fee'>手续费: {fee:.2f}</span>"
                    text += fee_text
        else:
            # 其他操作显示名义价值
            amount = qty * price
            text = f"{ts_str} {action} 金额: {amount:.2f} 方向: {direction} 价格: {price:.2f} 数量: {qty:.4f}"
            
            # 显示手续费（如果有的话）
            if r.get('fee') is not None and r['fee'] > 0:
                fee = float(r['fee'])
                fee_text = f" <span class='trade-fee'>手续费: {fee:.2f}</span>"
                text += fee_text
        
        return {"text": text}

    items = list(map(fmt, rows))
    return jsonify(items)


@app.get("/api/logs")
def api_logs():
    conn = get_conn()
    cur = conn.cursor()
    # 排除DEBUG级别的日志，只显示INFO、WARNING、ERROR级别的日志
    cur.execute("SELECT ts, level, message FROM logs WHERE level != 'DEBUG' ORDER BY ts DESC LIMIT 200")
    rows = cur.fetchall()
    conn.close()
    return "\n".join(
        [f"{fmt_ts_utc8(row['ts'])} [{row['level']}] {row['message']}" for row in rows]
    )



@app.get("/api/balance")
def api_balance():
    """获取当前余额（模拟模式下返回模拟余额）"""
    try:
        # 获取 Engine 实例中的 trader 余额
        if hasattr(app, 'engine_instance') and app.engine_instance:
            balance = app.engine_instance.trader.get_balance()
        else:
            # 如果没有 engine 实例，返回默认值
            balance = 0.0
        return jsonify({"balance": balance})
    except Exception as e:
        return jsonify({"balance": 0.0, "error": str(e)})


@app.get("/api/kline_data")
def api_kline_data():
    """获取 K 线数据和 BOLL 指标用于图表显示"""
    try:
        # 获取参数，默认返回最近100条K线数据
        limit = int(request.args.get('limit', 100))
        limit = min(limit, 500)  # 限制最大数量
        
        # 获取K线数据
        rows = fetch_klines(config.SYMBOL, limit=limit + config.BOLL_PERIOD)
        if len(rows) < config.BOLL_PERIOD:
            return jsonify({
                'klines': [],
                'boll': [],
                'error': 'K线数据不足'
            })
        
        # 转换为DataFrame计算BOLL指标
        df = pd.DataFrame(rows)
        mid, up, dn = bollinger_bands(df, config.BOLL_PERIOD, config.BOLL_STD, ddof=1)
        
        # 只返回最近limit条数据
        df_display = df.tail(limit).copy()
        mid_display = mid.tail(limit)
        up_display = up.tail(limit)
        dn_display = dn.tail(limit)
        
        # 格式化K线数据
        klines = []
        for i, (idx, row) in enumerate(df_display.iterrows()):
            klines.append({
                'time': int(row['open_time']),
                'open': float(row['open']),
                'high': float(row['high']),
                'low': float(row['low']),
                'close': float(row['close']),
                'volume': float(row['volume'])
            })
        
        # 格式化BOLL数据
        boll_data = []
        for i, (idx, row) in enumerate(df_display.iterrows()):
            boll_data.append({
                'time': int(row['open_time']),
                'upper': float(up_display.iloc[i]),
                'middle': float(mid_display.iloc[i]),
                'lower': float(dn_display.iloc[i])
            })
        
        return jsonify({
            'klines': klines,
            'boll': boll_data,
            'symbol': config.SYMBOL,
            'interval': config.INTERVAL
        })
        
    except Exception as e:
        return jsonify({
            'klines': [],
            'boll': [],
            'error': str(e)
        }), 500


@app.get("/api/realtime_boll")
def api_realtime_boll():
    """获取实时BOLL数据用于同步系统"""
    try:
        # 获取最新的K线数据用于计算BOLL
        rows = fetch_klines(config.SYMBOL, limit=config.BOLL_PERIOD + 1)
        if len(rows) < config.BOLL_PERIOD:
            return jsonify({
                'success': False,
                'error': 'K线数据不足',
                'boll': None
            })
        
        # 转换为DataFrame计算BOLL指标
        df = pd.DataFrame(rows)
        mid, up, dn = bollinger_bands(df, config.BOLL_PERIOD, config.BOLL_STD, ddof=1)
        
        # 获取最新的BOLL值
        latest_boll = {
            'timestamp': int(df.iloc[-1]['open_time']),
            'upper': float(up.iloc[-1]),
            'middle': float(mid.iloc[-1]),
            'lower': float(dn.iloc[-1]),
            'period': config.BOLL_PERIOD,
            'std': config.BOLL_STD,
            'symbol': config.SYMBOL,
            'interval': config.INTERVAL
        }
        
        return jsonify({
            'success': True,
            'boll': latest_boll,
            'error': None
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e),
            'boll': None
        }), 500


@app.post("/api/boll_sync_status")
def api_boll_sync_status():
    """接收BOLL同步状态更新"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': '无效的请求数据'})
        
        # 这里可以记录同步状态到数据库或日志
        # 暂时只返回成功状态
        return jsonify({
            'success': True,
            'message': '同步状态已更新'
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


def _ensure_port_free(port: int):
    """如果端口被占用，立即杀掉占用进程，并等待端口释放。"""
    try:
        victims = set()
        for c in psutil.net_connections(kind='inet'):
            try:
                if c.laddr and getattr(c.laddr, 'port', None) == port and c.pid and c.pid != os.getpid():
                    victims.add(c.pid)
            except Exception:
                continue
        for pid in victims:
            try:
                p = psutil.Process(pid)
                p.terminate()
                try:
                    p.wait(2)
                except psutil.TimeoutExpired:
                    p.kill()
            except Exception:
                continue
        # 等待端口释放
        def _in_use(p: int) -> bool:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(0.2)
                return s.connect_ex(('127.0.0.1', p)) == 0
        for _ in range(15):
            if not _in_use(port):
                break
            time.sleep(0.2)
    except Exception:
        # 忽略清理过程中的权限或平台差异错误
        pass


def run_web():
    print("启动检查开始...")

    eng = Engine(socketio=socketio)  # 传入socketio对象
    asyncio.run(eng.bootstrap())
    
    # 将 engine 实例存储到 app 对象中，供 API 接口使用
    app.engine_instance = eng

    print("启动 WebSocket API 订阅实时币价...")
    def run_engine_ws():
        asyncio.run(eng.run_ws())
    thread = threading.Thread(target=run_engine_ws, daemon=True)
    thread.start()
    print("WebSocket 订阅已启动。")

    # 检查数据库 K 线数据（更新后）
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) AS c FROM klines WHERE symbol=? AND interval=?", (config.SYMBOL, config.INTERVAL))
    kline_count = cur.fetchone()['c']
    latest_time = latest_kline_time(config.SYMBOL, config.INTERVAL) or 0
    print(f"数据库中有 {kline_count} 条 {config.SYMBOL} {config.INTERVAL} 的 K 线数据，最新 open_time: {fmt_ts_utc8(latest_time)}。")

    # 检查持仓
    pos = get_position(config.SYMBOL)
    if pos:
        print(f"检测到持仓: {pos['side']} 数量 {pos['qty']} 入场价 {pos['entry_price']}。")
    else:
        print("无当前持仓。")

    # 端口检查
    print("检查端口可用性...")
    _ensure_port_free(5000)
    print(f"端口 5000 已可用。")

    print("启动检查完成。")
    # 使用socketio.run启动应用，支持WebSocket，添加allow_unsafe_werkzeug=True以支持生产环境部署
    socketio.run(app, host=config.WEB_HOST, port=config.WEB_PORT, debug=False, allow_unsafe_werkzeug=True)


if __name__ == "__main__":
    run_web()