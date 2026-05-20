from fastapi import FastAPI, HTTPException, Request
import pandas as pd
import akshare as ak
import efinance as ef

app = FastAPI(title="统一金融数据 API - 华为云版")

# ==========================================
# 0. 系统级路由 (用于保活与健康检查)
# ==========================================
@app.get("/ping")
@app.post("/invoke") # 兼容华为云内部定时触发器的 POST 请求
async def keep_alive():
    return {"status": "alive", "message": "Container is warm."}

# ==========================================
# 1. EFinance 接口 - 主攻【实时/高频微观】
# ==========================================
@app.get("/api/realtime/quote/{code}")
def get_efinance_quote(code: str):
    try:
        # 获取股票实时行情 (支持 A股、美股、港股，例如 "600519")
        df = ef.stock.get_quote_history(code)
        if df.empty:
            raise HTTPException(status_code=404, detail="未获取到数据")
        
        # 转换数据格式，处理 NaN 空值
        data = df.fillna("").to_dict(orient="records")
        return {"code": 0, "source": "efinance", "data": data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ==========================================
# 2. AkShare 接口 - 主攻【历史/宏观】
# ==========================================
@app.get("/api/akshare/history/{code}")
def get_akshare_history(code: str, start_date: str = "20230101", end_date: str = "20231231"):
    try:
        # 获取 A 股前复权历史 K 线
        df = ak.stock_zh_a_hist(symbol=code, period="daily", start_date=start_date, end_date=end_date, adjust="qfq")
        if df.empty:
            raise HTTPException(status_code=404, detail="未获取到数据")
        
        # 处理日期格式并转换为 JSON 安全格式
        if '日期' in df.columns:
            df['日期'] = df['日期'].astype(str)
            
        data = df.fillna("").to_dict(orient="records")
        return {"code": 0, "source": "akshare", "data": data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ==========================================
# 3. 巨潮资讯 (CNInfo) - 借由 AkShare 调用
# ==========================================
@app.get("/api/cninfo/announcement/{code}")
def get_cninfo_announcement(code: str):
    try:
        # 调取巨潮资讯的个股公告摘要（示例接口）
        # 注意：此处以深交所/巨潮数据为例，根据实际需求可替换 akshare 中的其他巨潮接口
        df = ak.stock_info_szse_cninfo(symbol="最新公告") 
        
        # 为了演示，此处过滤出请求的代码（实际使用中建议研究 AkShare 文档获取最匹配接口）
        if not df.empty and '代码' in df.columns:
            df = df[df['代码'] == code]
            
        data = df.fillna("").to_dict(orient="records")
        return {"code": 0, "source": "cninfo", "data": data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
