import streamlit as st
import pyupbit
import pandas as pd
import numpy as np
import time
import requests
from datetime import datetime

# ----------------------------------------
# 1. 텔레그램 전송 함수
# ----------------------------------------
def send_telegram(token, chat_id, message):
    """토큰과 Chat ID가 입력되어 있을 때만 텔레그램 발송"""
    if not token or not chat_id:
        return
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "Markdown"
    }
    try:
        requests.post(url, data=payload, timeout=5)
    except Exception as e:
        st.toast(f"텔레그램 발송 실패: {e}")

# ----------------------------------------
# 2. 지표 연산 및 Z-Score 퀀트 엔진
# ----------------------------------------
def add_advanced_indicators(df):
    df['ma5'] = df['close'].rolling(5).mean()
    df['ma20'] = df['close'].rolling(20).mean()
    
    vol_mean = df['volume'].rolling(window=60).mean()
    vol_std = df['volume'].rolling(window=60).std()
    df['vol_zscore'] = (df['volume'] - vol_mean) / (vol_std + 1e-9)
    
    high_low = df['high'] - df['low']
    high_close = np.abs(df['high'] - df['close'].shift())
    low_close = np.abs(df['low'] - df['close'].shift())
    ranges = pd.concat([high_low, high_close, low_close], axis=1)
    df['atr'] = np.max(ranges, axis=1).rolling(14).mean()
    
    ema12 = df['close'].ewm(span=12, adjust=False).mean()
    ema26 = df['close'].ewm(span=26, adjust=False).mean()
    df['macd'] = ema12 - ema26
    df['macd_signal'] = df['macd'].ewm(span=9, adjust=False).mean()
    
    delta = df['close'].diff()
    up = delta.clip(lower=0)
    down = -1 * delta.clip(upper=0)
    df['rsi'] = 100 - (100 / (1 + (up.ewm(com=13, adjust=False).mean() / (down.ewm(com=13, adjust=False).mean() + 1e-9))))
    return df

def z_score_breakout_scan(coin):
    try:
        df_15m = pyupbit.get_ohlcv(coin, interval="minute15", count=100)
        df_5m = pyupbit.get_ohlcv(coin, interval="minute5", count=150)
        
        if df_15m is None or df_5m is None:
            return False
            
        df_15m = add_advanced_indicators(df_15m)
        df_5m = add_advanced_indicators(df_5m)
        
        last_15m = df_15m.iloc[-1]
        last_5m = df_5m.iloc[-1]
        
        trend_15m = (last_15m['close'] > last_15m['ma20']) and (last_15m['macd'] > last_15m['macd_signal'])
        vol_breakout = last_5m['vol_zscore'] >= 2.5
        price_momentum = (last_5m['close'] > last_5m['ma5']) and (last_5m['rsi'] >= 55) and (last_5m['rsi'] <= 75)
        
        if trend_15m and vol_breakout and price_momentum:
            return True
        return False
    except Exception:
        return False

# ----------------------------------------
# Streamlit UI & 자동매매 상태 관리
# ----------------------------------------
st.set_page_config(page_title="V13.1 자동매매 & 텔레그램 보고", layout="wide")

if 'highest_prices' not in st.session_state:
    st.session_state['highest_prices'] = {}

TARGET_COINS = [
    "KRW-BTC", "KRW-SOL", "KRW-XRP", "KRW-DOGE", "KRW-SHIB", 
    "KRW-SEI", "KRW-SUI", "KRW-STX", "KRW-LINK", "KRW-AVAX"
]
MAX_INVEST_PER_COIN = 500000 

st.markdown("""
    <style>
    .stApp { background-color: #0b0f19; color: #f0f2f6; }
    .sidebar .sidebar-content { background-color: #161b22; }
    </style>
    """, unsafe_allow_html=True)

st.title("🤖 V13.1 실전 자동매매 & 알림 시스템")

# 사이드바: 1. 업비트 API
st.sidebar.header("🔑 1. 업비트 API 연동")
access_key = st.sidebar.text_input("Access Key", type="password")
secret_key = st.sidebar.text_input("Secret Key", type="password")

# 사이드바: 2. 텔레그램 연동 (선택사항)
st.sidebar.header("📱 2. 텔레그램 매매 보고 (선택)")
tele_token = st.sidebar.text_input("Bot Token (봇파더 발급)", type="password")
tele_chat_id = st.sidebar.text_input("Chat ID (내 고유번호)", type="password")

upbit = None
krw_balance = 0

if access_key and secret_key:
    upbit = pyupbit.Upbit(access_key, secret_key)
    try:
        krw_balance = upbit.get_balance("KRW")
        st.sidebar.success(f"업비트 연동 성공! 잔고: {int(krw_balance):,} 원")
    except Exception:
        st.sidebar.error("API 키 오류 또는 권한 없음")
        upbit = None

auto_mode = st.toggle("🚀 실전 자동매매 가동", value=False)

if auto_mode:
    if upbit is None:
        st.error("⚠️ 사이드바에 올바른 API 키를 먼저 입력하세요.")
        st.stop()
        
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    st.info(f"🔄 [{now_str}] 계좌 감시 및 매매 엔진 가동 중...")
    
    logs = []
    
    for coin in TARGET_COINS:
        time.sleep(0.3)
        
        coin_ticker = coin.replace("KRW-", "")
        coin_balance = upbit.get_balance(coin_ticker)
        curr_price = pyupbit.get_current_price(coin)
        
        # 보유 중인 경우 (평가금액 5,000원 이상)
        if coin_balance * curr_price > 5000:
            avg_buy_price = upbit.get_avg_buy_price(coin_ticker)
            
            if coin not in st.session_state['highest_prices']:
                st.session_state['highest_prices'][coin] = curr_price
            else:
                st.session_state['highest_prices'][coin] = max(st.session_state['highest_prices'][coin], curr_price)
                
            highest_p = st.session_state['highest_prices'][coin]
            profit_rate = (curr_price - avg_buy_price) / avg_buy_price * 100
            
            # [조건 A] 트레일링 스탑 익절
            if curr_price <= highest_p * 0.985 and highest_p > avg_buy_price * 1.02:
                upbit.sell_market_order(coin, coin_balance)
                msg = f"🟢 **[익절 체결]** {coin}\n* 매도단가: {int(curr_price):,}원\n* 수익률: **{profit_rate:+.2f}%**"
                logs.append(msg.replace("\n* ", " | "))
                send_telegram(tele_token, tele_chat_id, msg)
                del st.session_state['highest_prices'][coin]
                
            # [조건 B] 칼손절
            elif curr_price <= avg_buy_price * 0.98:
                upbit.sell_market_order(coin, coin_balance)
                msg = f"🔴 **[손절 체결]** {coin}\n* 매도단가: {int(curr_price):,}원\n* 수익률: **{profit_rate:+.2f}%**"
                logs.append(msg.replace("\n* ", " | "))
                send_telegram(tele_token, tele_chat_id, msg)
                if coin in st.session_state['highest_prices']:
                    del st.session_state['highest_prices'][coin]
                    
            else:
                logs.append(f"👁️ [보유 유지] {coin} | 평단가: {int(avg_buy_price):,} | 현재가: {int(curr_price):,} ({profit_rate:+.2f}%)")
                
        # 보유 중이 아닌 경우 (신규 매수 탐색)
        else:
            if z_score_breakout_scan(coin):
                krw_bal = upbit.get_balance("KRW")
                if krw_bal > 5000:
                    invest_amount = min(MAX_INVEST_PER_COIN, krw_bal * 0.99)
                    upbit.buy_market_order(coin, invest_amount)
                    st.session_state['highest_prices'][coin] = curr_price
                    
                    msg = f"🚀 **[매수 체결]** {coin}\n* 진입단가: {int(curr_price):,}원\n* 투입금액: {int(invest_amount):,}원"
                    logs.append(msg.replace("\n* ", " | "))
                    send_telegram(tele_token, tele_chat_id, msg)
                else:
                    logs.append(f"⚠️ [매수 실패] {coin} 타점 발생 (잔고 부족)")

    if logs:
        for log in logs:
            st.write(log)
            
    with st.spinner("3분 후 다음 매매 스캔을 진행합니다..."):
        time.sleep(180) 
        st.rerun()
else:
    st.warning("스위치를 켜면 실제 원화 계좌 연동 및 자동매매가 시작됩니다.")