import sqlite3

conn = sqlite3.connect('data/trading.db')
cur = conn.cursor()

# 获取所有有交易记录的日期
cur.execute("SELECT DISTINCT date(datetime(ts/1000, 'unixepoch')) as trade_date FROM trades ORDER BY trade_date DESC")
trade_dates = [row[0] for row in cur.fetchall()]
print(f"Found {len(trade_dates)} dates with trades: {trade_dates}")

for date in trade_dates:
    # 计算该日期的手续费总和
    cur.execute("SELECT SUM(fee) FROM trades WHERE date(datetime(ts/1000, 'unixepoch')) = ?", (date,))
    total_fees_result = cur.fetchone()
    total_fees = total_fees_result[0] if total_fees_result and total_fees_result[0] else 0.0
    
    # 更新daily_profits记录
    cur.execute("UPDATE daily_profits SET total_fees = ? WHERE date = ?", (total_fees, date))
    print(f"Updated {date}: total_fees = {total_fees:.6f}")

conn.commit()
conn.close()
print("Historical fees update completed!")