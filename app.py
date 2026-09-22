import streamlit as st
import pyupbit
import pandas as pd
import numpy as np
import time

# ----------------------------------------
# 1. 보조 지표 계산 함수 (ATR, VWAP 등)
# ----------------------------------------
def add_indicators(df):
    # 단순 이동평균
    df['ma5'] = df['close'].rolling(5).mean()
    df['ma20'] = df['close'].rolling(20).mean()
    df['ma60'] = df['close'].rolling(60).mean()
    
    # 지수 이동평균 (MACD용)
    ema12 = df['close'].ewm(span=12, adjust=False).mean()
    ema26 = df['close'].ewm(span=26, adjust=False).mean()
    df['macd'] = ema12 - ema26
    df['macd_signal'] = df['macd'].ewm(span=9, adjust=False).mean()
    
    # RSI
    delta = df['close'].diff()
    up = delta.clip(lower=0)
    down = -1 * delta.clip(upper=0)
    df['rsi'] = 100 - (100 / (1 + (up.ewm(com=13, adjust=False).mean() / (down.ewm(com=13, adjust=False).mean() + 1e-9))))
    
    # ATR (Average True Range) - 캔들 하나당 평균 변동폭 (시간 예측용)
    high_low = df['high'] - df['low']
    high_close = np.abs(df['high'] - df['close'].shift())
    low_close = np.abs(df['low'] - df['close'].shift())
    ranges = pd.concat([high_low, high_close, low_close], axis=1)
    true_range = np.max(ranges, axis=1)
    df['atr'] = true_range.rolling(14).mean()
    
    # VWAP (거래량 가중 평균가)
    cum_vol_price = (df['close'] * df['volume']).rolling(window=100).sum()
    cum_vol = df['volume'].rolling(window=100).sum()
    df['vwap'] = cum_vol_price / (cum_vol + 1e-9)
    
    return df

# ----------------------------------------
# 2. V8 MTF (다중 타임프레임) 정밀 분석 엔진
# ----------------------------------------
def mtf_precision_scan(coin):
    """4H, 1H, 15M, 5M 캔들을 모두 분석하여 완벽한 교집합일 때만 타점 반환"""
    
    try:
        # 4개의 타임프레임 데이터 동시 수집
        df_4h = pyupbit.get_ohlcv(coin, interval="minute240", count=100)
        df_1h = pyupbit.get_ohlcv(coin, interval="minute60", count=100)
        df_15m = pyupbit.get_ohlcv(coin, interval="minute15", count=100)
        df_5m = pyupbit.get_ohlcv(coin, interval="minute5", count=200)
        
        if any(df is None for df in [df_4h, df_1h, df_15m, df_5m]):
            return None
            
        df_4h = add_indicators(df_4h)
        df_1h = add_indicators(df_1h)
        df_15m = add_indicators(df_15m)
        df_5m = add_indicators(df_5m)
        
        last_4h = df_4h.iloc[-1]
        last_1h = df_1h.iloc[-1]
        last_15m = df_15m.iloc[-1]
        last_5m = df_5m.iloc[-1]
        
        # [조건 1] 4시간봉: 거시 추세가 반드시 상승장일 것 (20 이평선 위)
        cond_4h = last_4h['close'] > last_4h['ma20']
        
        # [조건 2] 1시간봉: 세력 평단가(VWAP) 위에 존재하며 MACD가 골든크로스 상태일 것
        cond_1h = (last_1h['close'] > last_1h['vwap']) and (last_1h['macd'] > last_1h['macd_signal'])
        
        # [조건 3] 15분봉: 단기 눌림목 후 반등 모멘텀 (RSI 50~65 사이로 탄력받는 중)
        cond_15m = (50 < last_15m['rsi'] < 65) and (last_15m['close'] > last_15m['ma20'])
        
        # [조건 4] 5분봉: 즉각적인 거래량 동반 돌파 타점
        cond_5m = (last_5m['close'] > last_5m['ma5']) and (last_5m['volume'] > df_5m['volume'].rolling(20).mean().iloc[-1] * 1.2)
        
        # 모든 타임프레임의 조건이 완벽히 일치할 때만 True
        is_perfect_entry = cond_4h and cond_1h and cond_15m and cond_5m
        
        if is_perfect_entry:
            curr_price = last_5m['close']
            tp_pct = 0.025 # 목표 익절 2.5%
            sl_pct = 0.012 # 칼손절 1.2%
            
            tp_price = curr_price * (1 + tp_pct)
            sl_price = curr_price * (1 - sl_pct)
            
            # --- [핵심] 도달 예상 시간(ETA) 수학적 추론 ---
            # 1시간봉의 ATR(시간당 평균 변동 가격)을 활용하여 목표가까지 몇 시간이 걸릴지 계산
            hourly_volatility = last_1h['atr']
            target_distance = tp_price - curr_price
            
            if hourly_volatility > 0:
                estimated_hours = target_distance / hourly_volatility
                # 보수적인 예측을 위해 1.5배의 버퍼 타임 적용
                min_time = max(1, int(estimated_hours))
                max_time = max(2, int(estimated_hours * 1.5))
                eta_str = f"약 {min_time}시간 ~ {max_time}시간 내외"
            else:
                eta_str = "변동성 부족 (예측 불가)"
                
            return {
                "현재가": curr_price,
                "익절가": tp_price,
                "손절가": sl_price,
                "예상시간": eta_str,
                "근거": "4H 추세 + 1H VWAP + 15M 모멘텀 + 5M 돌파 완벽 일치"
            }
            
        return None
        
    except Exception as e:
        return None

# ----------------------------------------
# Streamlit UI
# ----------------------------------------
st.set_page_config(page_title="V8 MTF 정밀 시공간 예측기", layout="wide")

# API 호출 횟수가 4배 늘었으므로 안정성을 위해 시총 상위 15개 코인으로 집중 분석
TARGET_COINS = [
    "KRW-BTC", "KRW-ETH", "KRW-SOL", "KRW-XRP", "KRW-DOGE", 
    "KRW-ADA", "KRW-SEI", "KRW-SUI", "KRW-AVAX", "KRW-LINK",
    "KRW-STX", "KRW-POL", "KRW-ALGO", "KRW-SAND", "KRW-SHIB"
]

st.markdown("""
    <style>
    .stApp { background-color: #0b0f19; color: #f0f2f6; }
    .stButton>button { background-color: #1f77b4; color: white; font-weight: bold; width: 100%; border:none; padding:15px; border-radius:10px; }
    .stButton>button:hover { background-color: #155a8a; }
    </style>
    """, unsafe_allow_html=True)

st.title("⏳ V8 다중 프레임 시공간(ETA) 예측 스캐너")
st.markdown("4시간, 1시간, 15분, 5분봉의 4차원 데이터를 동시 분석하여 승률을 극한으로 높이고, 목표가에 도달할 **예상 소요 시간**까지 수학적으로 계산합니다.")

if st.button("🚀 4차원 시공간 정밀 분석 스캔 시작 (시간이 다소 소요됩니다)"):
    progress_bar = st.progress(0)
    status_text = st.empty()
    results = []
    
    for idx, coin in enumerate(TARGET_COINS):
        status_text.text(f"[{idx+1}/{len(TARGET_COINS)}] {coin} 4H/1H/15M/5M 다중 프레임 데이터 수집 및 연산 중...")
        
        # 1코인당 4번의 API 호출이 발생하므로 강력한 딜레이 적용 (IP 밴 방지)
        time.sleep(0.5) 
        
        scan_result = mtf_precision_scan(coin)
        
        if scan_result:
            results.append({
                "코인명": coin.replace("KRW-", ""),
                "진입 현재가": f"{scan_result['현재가']:,.4f} 원",
                "🎯 익절 목표가": f"{scan_result['익절가']:,.4f} 원",
                "🛡️ 손절 방어선": f"{scan_result['손절가']:,.4f} 원",
                "⏳ 익절가 도달 예상 시간": scan_result['예상시간'],
                "진입 검증 로직": scan_result['근거']
            })
            
        progress_bar.progress((idx + 1) / len(TARGET_COINS))
        
    status_text.text("✅ 고강도 MTF 시공간 분석 완료!")
    
    if results:
        res_df = pd.DataFrame(results)
        st.success(f"🔥 **{len(results)}개 종목에서 극한의 교집합 타점이 발견되었습니다!**")
        st.dataframe(res_df, use_container_width=True, hide_index=True)
        st.warning("⚡ **실전 운용 팁:** 매수 후 즉시 🎯익절 목표가와 🛡️손절 방어선에 예약 매도를 걸어두세요. 예상 시간이 지나도 목표가에 도달하지 않고 횡보한다면, 시장의 힘이 빠진 것이므로 본절(매수가) 근처에서 미련 없이 탈출하는 것이 안전합니다.")
    else:
        st.error("📉 **분석 결과:** 현재 15개 메이저 알트코인 중 4개의 타임프레임이 모두 상승을 가리키는 종목이 **단 하나도 없습니다.** (전형적인 하락장 또는 혼조세). 소중한 시드머니를 지키기 위해 지금은 무조건 관망하십시오.")