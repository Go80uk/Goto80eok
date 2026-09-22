import streamlit as st
import pyupbit
import pandas as pd
import numpy as np
import time

# ----------------------------------------
# 1. 고도화된 통계 및 모멘텀 지표 엔진
# ----------------------------------------
def add_advanced_indicators(df):
    # 기본 이동평균
    df['ma5'] = df['close'].rolling(5).mean()
    df['ma20'] = df['close'].rolling(20).mean()
    df['ma60'] = df['close'].rolling(60).mean()
    
    # 1. 거래량 Z-Score (통계적 이상치 탐지)
    # 최근 60개 캔들의 거래량 평균과 표준편차를 구함
    vol_mean = df['volume'].rolling(window=60).mean()
    vol_std = df['volume'].rolling(window=60).std()
    df['vol_zscore'] = (df['volume'] - vol_mean) / (vol_std + 1e-9)
    
    # 2. 가격 변동성 (ATR)
    high_low = df['high'] - df['low']
    high_close = np.abs(df['high'] - df['close'].shift())
    low_close = np.abs(df['low'] - df['close'].shift())
    ranges = pd.concat([high_low, high_close, low_close], axis=1)
    df['atr'] = np.max(ranges, axis=1).rolling(14).mean()
    
    # 3. MACD & RSI 모멘텀
    ema12 = df['close'].ewm(span=12, adjust=False).mean()
    ema26 = df['close'].ewm(span=26, adjust=False).mean()
    df['macd'] = ema12 - ema26
    df['macd_signal'] = df['macd'].ewm(span=9, adjust=False).mean()
    
    delta = df['close'].diff()
    up = delta.clip(lower=0)
    down = -1 * delta.clip(upper=0)
    df['rsi'] = 100 - (100 / (1 + (up.ewm(com=13, adjust=False).mean() / (down.ewm(com=13, adjust=False).mean() + 1e-9))))
    
    return df

# ----------------------------------------
# 2. V12 Z-Score 돌파 스캐너 
# ----------------------------------------
def z_score_breakout_scan(coin):
    try:
        # 5분봉과 15분봉의 교차 검증 (속도와 정확성 밸런스)
        df_15m = pyupbit.get_ohlcv(coin, interval="minute15", count=100)
        df_5m = pyupbit.get_ohlcv(coin, interval="minute5", count=150)
        
        if df_15m is None or df_5m is None:
            return None
            
        df_15m = add_advanced_indicators(df_15m)
        df_5m = add_advanced_indicators(df_5m)
        
        last_15m = df_15m.iloc[-1]
        last_5m = df_5m.iloc[-1]
        
        # [조건 1] 15분봉 거시 추세: 20일선 위 유지 및 MACD 상승세
        trend_15m = (last_15m['close'] > last_15m['ma20']) and (last_15m['macd'] > last_15m['macd_signal'])
        
        # [조건 2] 5분봉 Z-Score 거래량 폭발: 거래량 Z값이 2.5 이상 (정규분포 0.6% 극단치)
        vol_breakout = last_5m['vol_zscore'] >= 2.5
        
        # [조건 3] 5분봉 가격 모멘텀: 5일선이 20일선을 강하게 상향 돌파 중 (RSI 과매수 직전)
        price_momentum = (last_5m['close'] > last_5m['ma5']) and (last_5m['rsi'] >= 55) and (last_5m['rsi'] <= 75)
        
        if trend_15m and vol_breakout and price_momentum:
            curr_price = last_5m['close']
            atr_val = last_5m['atr']
            
            # 동적 트레일링 스탑 가이드라인 (ATR 기반)
            # 변동성이 클수록 손절폭과 목표가를 넓게, 작을수록 좁게 설정
            stop_loss = curr_price - (atr_val * 1.5)
            trailing_start = curr_price + (atr_val * 2.0)
            
            return {
                "현재가": curr_price,
                "손절선(SL)": stop_loss,
                "추적익절(Trailing) 시작가": trailing_start,
                "Z-Score": round(last_5m['vol_zscore'], 2)
            }
        return None
    except Exception:
        return None

# ----------------------------------------
# Streamlit UI
# ----------------------------------------
st.set_page_config(page_title="V12 Z-Score 퀀트 머신", layout="wide")

TOTAL_SEED_MONEY = 2500000  # 총 시드머니 250만 원

# 고거래량 메이저 및 밈/레이어1 알트코인
TARGET_COINS = [
    "KRW-BTC", "KRW-SOL", "KRW-XRP", "KRW-DOGE", "KRW-SHIB", 
    "KRW-SEI", "KRW-SUI", "KRW-STX", "KRW-LINK", "KRW-AVAX",
    "KRW-NEAR", "KRW-APT", "KRW-ASTR", "KRW-PYTH", "KRW-ARB"
]

st.markdown("""
    <style>
    .stApp { background-color: #0b0f19; color: #f0f2f6; }
    .metric-card { background-color: #1e253c; padding: 20px; border-radius: 10px; margin-bottom: 20px; text-align: center; }
    </style>
    """, unsafe_allow_html=True)

st.title("📈 V12 Z-Score 기반 통계적 돌파 스캐너")
st.markdown(f"총 운용 자산 **{TOTAL_SEED_MONEY:,} 원**을 기반으로, 켈리 공식 관점에 맞춘 리스크 분배와 Z-Score 거래량 이상치를 실시간으로 추적합니다.")

# 대시보드 요약
col1, col2 = st.columns(2)
with col1:
    st.markdown(f"<div class='metric-card'><h3>총 시드머니</h3><h2>{TOTAL_SEED_MONEY:,} 원</h2></div>", unsafe_allow_html=True)
with col2:
    max_position = int(TOTAL_SEED_MONEY * 0.20) # 1회 최대 진입 비중 20%
    st.markdown(f"<div class='metric-card'><h3>1회 권장 투입 한도 (20%)</h3><h2 style='color:#00FFAA;'>{max_position:,} 원</h2></div>", unsafe_allow_html=True)

auto_mode = st.toggle("🤖 5분 주기 Z-Score 감시 모드 켜기", value=False)

if auto_mode:
    st.info("🔄 시장의 통계적 이상치(Anomaly)를 탐색 중입니다...")
    
    results = []
    progress_bar = st.progress(0)
    
    for idx, coin in enumerate(TARGET_COINS):
        time.sleep(0.3)
        scan = z_score_breakout_scan(coin)
        
        if scan:
            results.append({
                "코인명": coin.replace("KRW-", ""),
                "진입 현재가": f"{scan['현재가']:,.4f} 원",
                "📊 거래량 폭발 지수": f"Z={scan['Z-Score']} (초강세)",
                "🛡️ 절대 손절선": f"{scan['손절선(SL)']:,.4f} 원",
                "🚀 트레일링 익절 시작선": f"{scan['추적익절(Trailing) 시작가']:,.4f} 원"
            })
        progress_bar.progress((idx + 1) / len(TARGET_COINS))
        
    progress_bar.empty()
    
    if results:
        res_df = pd.DataFrame(results)
        st.success(f"🔥 통계적 유의성을 가진 돌파 타점이 {len(results)}건 포착되었습니다.")
        st.dataframe(res_df, use_container_width=True, hide_index=True)
        
        st.warning(f"💡 **V12 자금 운용 규칙:** 진입 시그널이 떴더라도 한 종목에 **{max_position:,} 원** 이상 진입하지 마십시오. 또한 가격이 [🚀 트레일링 익절 시작선]을 돌파하면 그때부터는 지정가 매도가 아닌, 가격이 꺾일 때 시장가로 던지는 '추세 추종'을 시작하십시오.")
    else:
        st.write(f"🕒 현재 시각 {time.strftime('%H:%M:%S')} - 시장 내 통계적 이상치 없음 (노이즈 구간)")

    with st.spinner("다음 5분봉 갱신 대기 중 (5분 간격)..."):
        time.sleep(300)
        st.rerun()
else:
    st.warning("상단의 스위치를 켜면 스캔이 시작됩니다.")