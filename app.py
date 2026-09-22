import streamlit as st
import pyupbit
import pandas as pd
import numpy as np
import time

# ----------------------------------------
# 1. 보조 지표 계산 및 V9 MTF 정밀 분석 엔진
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

def mtf_precision_scan(coin):
    try:
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
        
        cond_4h = last_4h['close'] > last_4h['ma20']
        cond_1h = (last_1h['close'] > last_1h['vwap']) and (last_1h['macd'] > last_1h['macd_signal'])
        cond_15m = (50 < last_15m['rsi'] < 65) and (last_15m['close'] > last_15m['ma20'])
        cond_5m = (last_5m['close'] > last_5m['ma5']) and (last_5m['volume'] > df_5m['volume'].rolling(20).mean().iloc[-1] * 1.2)
        
        if cond_4h and cond_1h and cond_15m and cond_5m:
            curr_price = last_5m['close']
            tp_pct = 0.025
            sl_pct = 0.012
            
            tp_price = curr_price * (1 + tp_pct)
            sl_price = curr_price * (1 - sl_pct)
            
            hourly_volatility = last_1h['atr']
            if hourly_volatility > 0:
                estimated_hours = (tp_price - curr_price) / hourly_volatility
                eta_str = f"약 {max(1, int(estimated_hours))}~{max(2, int(estimated_hours * 1.5))}시간"
            else:
                eta_str = "시간 예측 불가"
                
            return {"현재가": curr_price, "익절가": tp_price, "손절가": sl_price, "예상시간": eta_str}
        return None
    except Exception:
        return None

# ----------------------------------------
# 2. 브라우저 알림음 재생 함수
# ----------------------------------------
def play_alarm_sound():
    """웹 브라우저에서 삐빅! 하는 경고음을 재생합니다."""
    # 구글에서 제공하는 기본 알림음 오디오 링크
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
st.set_page_config(page_title="웹 자동 감시 스캐너", layout="wide")

TARGET_COINS = [
    "KRW-BTC", "KRW-ETH", "KRW-XRP", "KRW-DOGE", "KRW-SOL", 
    "KRW-SHIB", "KRW-SEI", "KRW-SUI", "KRW-AVAX", "KRW-LINK", 
    "KRW-STX", "KRW-POL", "KRW-ALGO", "KRW-SAND", "KRW-TRX"
] # 5분 주기에 맞게 안정적인 상위 15개 코인으로 최적화

st.markdown("""
    <style>
    .stApp { background-color: #0b0f19; color: #f0f2f6; }
    </style>
    """, unsafe_allow_html=True)

st.title("⏰ 실시간 웹 브라우저 자동 감시 모드")
st.markdown("이 탭을 켜두시면 5분마다 스스로 시장을 스캔하며, 완벽한 타점이 발견될 경우 **알림음 소리**와 함께 화면 우측 하단에 팝업을 띄웁니다.")

# 자동 모드 토글 스위치
auto_mode = st.toggle("🤖 24시간 웹 자동 스캔 켜기", value=False)

if auto_mode:
    st.info("🔄 현재 자동 스캔 모드가 가동 중입니다. (브라우저 탭을 닫지 마세요)")
    
    # 1. 15개 코인 전수 검사
    results = []
    progress_bar = st.progress(0)
    
    for idx, coin in enumerate(TARGET_COINS):
        time.sleep(0.3) # API 제한 방지
        scan_result = mtf_precision_scan(coin)
        
        if scan_result:
            results.append({
                "코인명": coin.replace("KRW-", ""),
                "현재가": f"{scan_result['현재가']:,.4f} 원",
                "🎯 익절 예약가": f"{scan_result['익절가']:,.4f} 원",
                "🛡️ 손절 예약가": f"{scan_result['손절가']:,.4f} 원",
                "⏳ 예상시간": scan_result['예상시간']
            })
        progress_bar.progress((idx + 1) / len(TARGET_COINS))
        
    progress_bar.empty() # 스캔 완료 후 진행바 숨기기
    
    # 2. 결과 출력 및 알림 발생
    if results:
        res_df = pd.DataFrame(results)
        st.success(f"🔥 {time.strftime('%H:%M:%S')} 기준 - {len(results)}개 종목 매수 타점 포착!")
        st.dataframe(res_df, use_container_width=True, hide_index=True)
        
        # 브라우저 알림음 재생 및 우측 하단 팝업(Toast) 띄우기
        play_alarm_sound()
        for idx, row in res_df.iterrows():
            st.toast(f"🚨 {row['코인명']} 강력 매수 신호! (현재가: {row['현재가']})", icon="🔥")
            
    else:
        st.write(f"🕒 마지막 스캔 시간: {time.strftime('%H:%M:%S')} - 발견된 타점 없음 (관망 유지)")

    # 3. 5분 대기 후 화면 자동 새로고침(루프)
    with st.spinner("다음 5분봉 갱신을 기다리는 중... (약 5분 대기)"):
        time.sleep(300) # 300초(5분) 대기
        st.rerun()      # 5분 뒤 코드를 처음부터 다시 실행 (새로고침)

else:
    st.warning("스위치를 켜면 5분 주기 자동 감시가 시작됩니다.")