from fastapi import FastAPI, HTTPException
import pandas as pd
import akshare as ak
import efinance as ef
from pytdx.hq import TdxHq_API
import json

app = FastAPI(title="金融数据网关 - 自动防封锁版")

@app.get("/ping")
def keep_alive():
    return {"status": "alive"}

# ==========================================
# 辅助函数 1：用通达信获取数据 (底层 TCP，抗封锁)
# ==========================================
def fetch_from_tdx(code: str, count: int):
    api = TdxHq_API(heartbeat=True)
    # 通达信常用行情服务器 IP (深圳节点之一，对海外连通率高)
    ip, port = '119.147.212.81', 7709 
    
    with api.connect(ip, port):
        # 市场代码判断: 上海(6开头)为1，深圳(0或3开头)为0
        market = 1 if code.startswith('6') else 0
        # 获取日线数据: category 9 为日线
        data = api.get_security_bars(9, market, code, 0, count)
        if not data:
            raise Exception("通达信未返回数据")
        
        df = api.to_df(data)
        # 统一格式：截取前10位日期，保留核心列
        df['date'] = df['datetime'].str.slice(0, 10)
        df.rename(columns={'vol': 'volume'}, inplace=True)
        return df[['date', 'open', 'close', 'high', 'low', 'volume']]

# ==========================================
# 辅助函数 2：用 efinance 获取数据
# ==========================================
def fetch_from_efinance(code: str):
    df = ef.stock.get_quote_history(code)
    if df.empty:
        raise Exception("EFinance未返回数据")
    # 统一字段名
    df.rename(columns={
        '日期': 'date', '开盘': 'open', '收盘': 'close', 
        '最高': 'high', '最低': 'low', '成交量': 'volume'
    }, inplace=True)
    return df[['date', 'open', 'close', 'high', 'low', 'volume']]

# ==========================================
# 辅助函数 3：用 akshare 获取数据
# ==========================================
def fetch_from_akshare(code: str):
    # 只取近期数据防止 OOM
    df = ak.stock_zh_a_hist(symbol=code, period="daily", start_date="20230101", adjust="qfq")
    if df.empty:
        raise Exception("AkShare未返回数据")
    # 统一字段名
    df.rename(columns={
        '日期': 'date', '开盘': 'open', '收盘': 'close', 
        '最高': 'high', '最低': 'low', '成交量': 'volume'
    }, inplace=True)
    return df[['date', 'open', 'close', 'high', 'low', 'volume']]


# ==========================================
# 核心路由：全自动智能切换获取 K 线数据
# ==========================================
@app.get("/api/smart_history/{code}")
def get_smart_history(code: str, count: int = 100):
    """
    智能获取数据：按照 PyTDX -> EFinance -> AkShare 的顺序尝试，
    哪个成功就返回哪个，彻底解决单个数据源被封锁的问题。
    """
    errors = []
    
    # 第一优先级：通达信 (TCP长连接，极少被封海外IP)
    try:
        df = fetch_from_tdx(code, count)
        data = df.fillna("").to_dict(orient="records")
        return {"code": 0, "source": "pytdx", "data": data}
    except Exception as e:
        errors.append(f"PyTDX 失败: {str(e)}")

    # 第二优先级：EFinance
    try:
        df = fetch_from_efinance(code)
        # efinance 返回全量数据，按 count 截取最后几行
        df = df.tail(count) 
        data = df.fillna("").to_dict(orient="records")
        return {"code": 0, "source": "efinance", "data": data}
    except Exception as e:
        errors.append(f"EFinance 失败: {str(e)}")

    # 第三优先级：AkShare
    try:
        df = fetch_from_akshare(code)
        df = df.tail(count)
        data = df.fillna("").to_dict(orient="records")
        return {"code": 0, "source": "akshare", "data": data}
    except Exception as e:
        errors.append(f"AkShare 失败: {str(e)}")
        
    # 如果三个全挂了，抛出 500 详细报错
    raise HTTPException(status_code=500, detail="所有数据源均不可用。日志: " + " | ".join(errors))
