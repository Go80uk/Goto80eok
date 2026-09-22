import streamlit as st
import pyupbit
import pandas as pd
import numpy as np
import time

# ----------------------------------------
# 1. 보조 지표 계산 
# ----------------------------------------
def add_indicators(df):
    df['ma5'] = df['close'].rolling(5).mean()
    df['ma20'] = df['close'].rolling(20).mean()
    
    ema12 = df['close'].ewm(span=12, adjust=False).mean()
    ema26 = df['close'].ewm(span=26, adjust=False).mean()
    df['macd'] = ema12 - ema26
    df['macd_signal'] = df['macd'].ewm(span=9, adjust=False).mean()
    
    delta = df['close'].diff()
    up = delta.clip(lower=0)
    down = -1 * delta.clip(upper=0)
    df['rsi'] = 100 - (100 / (1 + (up.ewm(com=13, adjust=False).mean() / (down.ewm(com=13, adjust=False).mean() + 1e-9))))
    
    high_low = df['high'] - df['low']
    high_close = np.abs(df['high'] - df['close'].shift())
    low_close = np.abs(df['low'] - df['close'].shift())
    ranges = pd.concat([high_low, high_close, low_close], axis=1)
    df['atr'] = np.max(ranges, axis=1).rolling(14).mean()
    
    cum_vol_price = (df['close'] * df['volume']).rolling(window=100).sum()
    cum_vol = df['volume'].rolling(window=100).sum()
    df['vwap'] = cum_vol_price / (cum_vol + 1e-9)
    return df

# ----------------------------------------
# 2. V11 공격형 데이트레이딩 분석 엔진
# ----------------------------------------
def action_mode_scan(coin):
    try:
        # 4시간봉 제외, 1시간/15분/5분봉만 사용하여 타점 빈도 증가
        df_1h = pyupbit.get_ohlcv(coin, interval="minute60", count=100)
        df_15m = pyupbit.get_ohlcv(coin, interval="minute15", count=100)
        df_5m = pyupbit.get_ohlcv(coin, interval="minute5", count=100)
        
        if any(df is None for df in [df_1h, df_15m, df_5m]):
            return None
            
        df_1h = add_indicators(df_1h)
        df_15m = add_indicators(df_15m)
        df_5m = add_indicators(df_5m)
        
        last_1h = df_1h.iloc[-1]
        last_15m = df_15m.iloc[-1]
        last_5m = df_5m.iloc[-1]
        
        # [완화된 조건 1] 1시간봉: 가격이 20일선 위에만 있으면 단기 추세 인정
        cond_1h = last_1h['close'] > last_1h['ma20']
        
        # [완화된 조건 2] 15분봉: RSI 모멘텀 확장 (45 ~ 70 범위 허용)
        cond_15m = (45 < last_15m['rsi'] < 70) and (last_15m['macd'] > last_15m['macd_signal'])
        
        # [완화된 조건 3] 5분봉: 거래량 조건 완화 (평균 거래량만 넘겨도 진입)
        avg_vol = df_5m['volume'].rolling(20).mean().iloc[-1]
        cond_5m = (last_5m['close'] > last_5m['ma5']) and (last_5m['volume'] > avg_vol)
        
        if cond_1h and cond_15m and cond_5m:
            curr_price = last_5m['close']
            tp_pct = 0.015 # 회전율을 높이기 위해 +1.5% 단타 익절
            sl_pct = 0.008 # 빠른 손절 -0.8%
            
            tp_price = curr_price * (1 + tp_pct)
            sl_price = curr_price * (1 - sl_pct)
            
            hourly_volatility = last_1h['atr']
            if hourly_volatility > 0:
                estimated_hours = (tp_price - curr_price) / hourly_volatility
                eta_str = f"약 {max(1, int(estimated_hours))}시간 내외"
            else:
                eta_str = "빠른 단타 권장"
                
            return {"현재가": curr_price, "익절가": tp_price, "손절가": sl_price, "예상시간": eta_str}
        return None
    except Exception:
        return None

# ----------------------------------------
# 3. 브라우저 알림음 재생 함수
# ----------------------------------------
def play_alarm_sound():
    audio_url = "https://actions.google.com/sounds/v1/alarms/beep_short.ogg"
    audio_html = f"""
        <audio autoplay="true" style="display:none;">
            <source src="{audio_url}" type="audio/ogg">
        </audio>
    """
    st.markdown(audio_html, unsafe_allow_html=True)

# ----------------------------------------
# Streamlit UI
# ----------------------------------------
st.set_page_config(page_title="액션 모드 스캐너", layout="wide")

TARGET_COINS = [
    "KRW-BTC", "KRW-ETH", "KRW-XRP", "KRW-DOGE", "KRW-SOL", 
    "KRW-SHIB", "KRW-SEI", "KRW-SUI", "KRW-AVAX", "KRW-LINK", 
    "KRW-STX", "KRW-POL", "KRW-ALGO", "KRW-SAND", "KRW-TRX"
]

st.markdown("""
    <style>
    .stApp { background-color: #121212; color: #ffffff; }
    </style>
    """, unsafe_allow_html=True)

st.title("⚡ 실시간 공격형 웹 스캐너 (Action Mode)")
st.markdown("거시 경제 조건을 제외하고 당일 단기 반등에 집중하여 타점 발생 빈도를 크게 높인 스캘핑/데이트레이딩 모드입니다.")

auto_mode = st.toggle("🤖 24시간 단타 스캔 켜기", value=False)

if auto_mode:
    st.info("🔄 타점 감시 중... (5분마다 자동 새로고침 됨)")
    
    results = []
    progress_bar = st.progress(0)
    
    for idx, coin in enumerate(TARGET_COINS):
        time.sleep(0.3) 
        scan_result = action_mode_scan(coin)
        
        if scan_result:
            results.append({
                "코인명": coin.replace("KRW-", ""),
                "현재가": f"{scan_result['현재가']:,.4f} 원",
                "🎯 단타 익절가": f"{scan_result['익절가']:,.4f} 원",
                "🛡️ 즉시 손절가": f"{scan_result['손절가']:,.4f} 원",
                "⏳ 예상시간": scan_result['예상시간']
            })
        progress_bar.progress((idx + 1) / len(TARGET_COINS))
        
    progress_bar.empty() 
    
    if results:
        res_df = pd.DataFrame(results)
        st.success(f"🔥 {time.strftime('%H:%M:%S')} 기준 - {len(results)}개 타점 포착!")
        st.dataframe(res_df, use_container_width=True, hide_index=True)
        
        play_alarm_sound()
        for idx, row in res_df.iterrows():
            st.toast(f"🚨 {row['코인명']} 단타 진입 타점 포착!", icon="⚡")
            
    else:
        st.write(f"🕒 마지막 스캔 시간: {time.strftime('%H:%M:%S')} - 발견된 타점 없음")

    with st.spinner("다음 5분봉 갱신 대기 중..."):
        time.sleep(300) 
        st.rerun() 
else:
    st.warning("스위치를 켜면 단기 파동 감시가 시작됩니다.")