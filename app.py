import streamlit as st
import pyupbit
import pandas as pd
import numpy as np
import time
from datetime import datetime

# ----------------------------------------
# 1. 지표 연산 및 Z-Score 퀀트 엔진
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
            return None
            
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
st.set_page_config(page_title="V13 자동매매 퀀트 머신", layout="wide")

if 'highest_prices' not in st.session_state:
    st.session_state['highest_prices'] = {} # 보유 종목의 고점 추적용 (트레일링 스탑)

TARGET_COINS = [
    "KRW-BTC", "KRW-SOL", "KRW-XRP", "KRW-DOGE", "KRW-SHIB", 
    "KRW-SEI", "KRW-SUI", "KRW-STX", "KRW-LINK", "KRW-AVAX"
]
MAX_INVEST_PER_COIN = 500000 # 1회 최대 진입 비중 (50만 원)

st.markdown("""
    <style>
    .stApp { background-color: #0b0f19; color: #f0f2f6; }
    .sidebar .sidebar-content { background-color: #161b22; }
    </style>
    """, unsafe_allow_html=True)

st.title("🤖 V13 업비트 실전 자동매매 시스템")
st.markdown("API 키를 입력하면 **실제 계좌의 원화(KRW)로 시장가 매수/매도를 자동 집행**합니다.")

# 사이드바: API 키 입력 및 계좌 연동
st.sidebar.header("🔑 업비트 API 연동")
access_key = st.sidebar.text_input("Access Key", type="password")
secret_key = st.sidebar.text_input("Secret Key", type="password")

upbit = None
krw_balance = 0

if access_key and secret_key:
    upbit = pyupbit.Upbit(access_key, secret_key)
    try:
        krw_balance = upbit.get_balance("KRW")
        st.sidebar.success(f"연동 성공! 보유 원화: {int(krw_balance):,} 원")
    except Exception as e:
        st.sidebar.error("API 키가 올바르지 않거나 권한이 없습니다.")
        upbit = None

# 자동매매 가동 스위치
auto_mode = st.toggle("🚀 실전 자동매매 가동 (주의: 실제 돈이 거래됩니다)", value=False)

if auto_mode:
    if upbit is None:
        st.error("⚠️ 사이드바에 올바른 API 키를 먼저 입력해야 자동매매가 작동합니다.")
        st.stop()
        
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    st.info(f"🔄 [{now_str}] 자동매매 엔진 가동 중... (포지션 관리 및 타점 스캔)")
    
    logs = []
    
    # ----------------------------------------
    # [핵심] 자동매매 로직 실행
    # ----------------------------------------
    for coin in TARGET_COINS:
        time.sleep(0.3) # API 제한 방지
        
        # 1. 내 계좌에 해당 코인이 있는지(포지션 유무) 확인
        coin_ticker = coin.replace("KRW-", "")
        coin_balance = upbit.get_balance(coin_ticker)
        curr_price = pyupbit.get_current_price(coin)
        
        # 보유 금액이 5,000원 이상이면 '보유 중'으로 간주 -> 매도 관리(익절/손절) 돌입
        if coin_balance * curr_price > 5000:
            avg_buy_price = upbit.get_avg_buy_price(coin_ticker)
            
            # 보유 종목의 고점(Highest Price) 갱신
            if coin not in st.session_state['highest_prices']:
                st.session_state['highest_prices'][coin] = curr_price
            else:
                st.session_state['highest_prices'][coin] = max(st.session_state['highest_prices'][coin], curr_price)
                
            highest_p = st.session_state['highest_prices'][coin]
            profit_rate = (curr_price - avg_buy_price) / avg_buy_price * 100
            
            # [매도 조건 A] 트레일링 스탑: 고점 대비 1.5% 하락 시 시장가 전량 매도 (수익 보존)
            if curr_price <= highest_p * 0.985 and highest_p > avg_buy_price * 1.02:
                upbit.sell_market_order(coin, coin_balance)
                logs.append(f"🟢 [트레일링 스탑 익절] {coin} 매도 완료 (수익률: {profit_rate:+.2f}%)")
                del st.session_state['highest_prices'][coin] # 고점 데이터 초기화
                
            # [매도 조건 B] 칼손절: 매수 평단가 대비 -2% 도달 시 즉시 시장가 매도 (계좌 보호)
            elif curr_price <= avg_buy_price * 0.98:
                upbit.sell_market_order(coin, coin_balance)
                logs.append(f"🔴 [손절 라인 이탈] {coin} 매도 완료 (수익률: {profit_rate:+.2f}%)")
                if coin in st.session_state['highest_prices']:
                    del st.session_state['highest_prices'][coin]
                    
            else:
                logs.append(f"👁️ [보유 중] {coin} | 평단가: {int(avg_buy_price):,} | 현재가: {int(curr_price):,} ({profit_rate:+.2f}%)")
                
        # 2. 보유하고 있지 않다면 -> 매수 타점 스캔
        else:
            is_buy_signal = z_score_breakout_scan(coin)
            
            if is_buy_signal:
                krw_bal = upbit.get_balance("KRW")
                # 살 돈이 최소 5,000원 이상 남아있는지 확인
                if krw_bal > 5000:
                    # 최대 투입 한도(50만원)와 현재 잔고 중 작은 금액으로 매수
                    invest_amount = min(MAX_INVEST_PER_COIN, krw_bal * 0.99) # 수수료 여유분 1% 제외
                    upbit.buy_market_order(coin, invest_amount)
                    st.session_state['highest_prices'][coin] = curr_price # 고점 기록 시작
                    logs.append(f"🚀 [강력 매수 체결] {coin} | {int(invest_amount):,} 원 진입 완료!")
                else:
                    logs.append(f"⚠️ [매수 실패] {coin} 타점 발생했으나 잔고 부족")

    # ----------------------------------------
    # 실행 로그 출력 및 무한 루프 갱신
    # ----------------------------------------
    if logs:
        for log in logs:
            st.write(log)
            
    with st.spinner("다음 사이클을 기다리는 중... (3분 간격 감시)"):
        # 포지션 관리의 민첩성을 높이기 위해 5분 대기 대신 3분 대기로 단축
        time.sleep(180) 
        st.rerun()

else:
    st.warning("스위치를 켜면 실제 원화 계좌와 연동되어 매수/매도가 자동 진행됩니다.")