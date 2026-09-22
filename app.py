import streamlit as st
import pyupbit
import pandas as pd
import time

# ----------------------------------------
# 1. 4대 주요 매매 전략 시그널 생성기
# ----------------------------------------
def apply_strategies(df):
    df = df.copy()
    
    # 공통 지표
    df['ma5'] = df['close'].rolling(5).mean()
    df['ma20'] = df['close'].rolling(20).mean()
    df['std20'] = df['close'].rolling(20).std()
    df['bb_upper'] = df['ma20'] + (df['std20'] * 2)
    df['bb_lower'] = df['ma20'] - (df['std20'] * 2)
    
    ema12 = df['close'].ewm(span=12, adjust=False).mean()
    ema26 = df['close'].ewm(span=26, adjust=False).mean()
    df['macd'] = ema12 - ema26
    df['macd_signal'] = df['macd'].ewm(span=9, adjust=False).mean()
    
    delta = df['close'].diff()
    up = delta.clip(lower=0)
    down = -1 * delta.clip(upper=0)
    df['rsi'] = 100 - (100 / (1 + (up.ewm(com=13, adjust=False).mean() / (down.ewm(com=13, adjust=False).mean() + 1e-9))))
    
    df['noise'] = 1 - (abs(df['close'] - df['open']) / (df['high'] - df['low'] + 1e-9))
    df['dynamic_k'] = df['noise'].rolling(20).mean().shift(1).fillna(0.5)
    df['target_price'] = df['open'] + (df['high'].shift(1) - df['low'].shift(1)) * df['dynamic_k']

    # 전략 1: 변동성 돌파
    df['S1_Buy'] = (df['high'] >= df['target_price']) & (df['close'] > df['ma5'])
    # 전략 2: MACD + RSI 모멘텀
    df['S2_Buy'] = (df['macd'] > df['macd_signal']) & (df['rsi'] > 50) & (df['rsi'] < 70) & (df['close'] > df['ma20'])
    # 전략 3: 볼린저 밴드 하단 반등
    df['S3_Buy'] = (df['low'] < df['bb_lower']) & (df['close'] > df['bb_lower']) & (df['rsi'] < 40)
    # 전략 4: 정통 이동평균 골든크로스 + 거래량
    df['vol_ma20'] = df['volume'].rolling(20).mean()
    df['S4_Buy'] = (df['ma5'] > df['ma20']) & (df['ma5'].shift(1) <= df['ma20'].shift(1)) & (df['volume'] > df['vol_ma20'] * 1.5)

    return df

# ----------------------------------------
# 2. 백테스트 및 최적화 엔진
# ----------------------------------------
def run_backtest(df, signal_col, tp_pct, sl_pct, fee=0.001):
    in_pos = False
    buy_price = 0.0
    equity = 1.0
    
    closes = df['close'].values
    highs = df['high'].values
    lows = df['low'].values
    signals = df[signal_col].values
    
    for i in range(60, len(df)):
        if not in_pos:
            if signals[i]:
                in_pos = True
                buy_price = closes[i]
                equity *= (1 - fee)
        else:
            if (highs[i] - buy_price) / buy_price >= tp_pct:
                equity *= (1 + tp_pct - fee)
                in_pos = False
            elif (lows[i] - buy_price) / buy_price <= -sl_pct:
                equity *= (1 - sl_pct - fee)
                in_pos = False
                
    return (equity - 1) * 100

def optimize_strategy(df):
    strategies = ["S1_Buy", "S2_Buy", "S3_Buy", "S4_Buy"]
    strategy_names = {
        "S1_Buy": "변동성 돌파 (우승자 기법)",
        "S2_Buy": "MACD 모멘텀 트렌드",
        "S3_Buy": "볼린저 하단 반등",
        "S4_Buy": "거래량 동반 골든크로스"
    }
    risk_profiles = [
        {"tp": 0.02, "sl": 0.01},
        {"tp": 0.03, "sl": 0.015},
        {"tp": 0.05, "sl": 0.02}
    ]
    
    best_return = -999
    best_config = None
    
    for s in strategies:
        for rp in risk_profiles:
            ret = run_backtest(df, s, rp["tp"], rp["sl"])
            if ret > best_return:
                best_return = ret
                best_config = {
                    "strategy_col": s,
                    "strategy_name": strategy_names[s],
                    "tp_pct": rp["tp"],
                    "sl_pct": rp["sl"],
                    "return": ret
                }
    return best_config

# ----------------------------------------
# Streamlit UI
# ----------------------------------------
st.set_page_config(page_title="AI 실시간 매수 타점 스캐너", layout="wide")

# ----------------------------------------
# 🎈 귀여운 UI 및 캐릭터 테마 적용 
# ----------------------------------------

# 1. 파스텔톤 배경 및 둥근 버튼 CSS 주입
st.markdown("""
    <style>
    /* 전체 배경색을 연한 파스텔 핑크로 변경 */
    .stApp {
        background-color: #FFF0F5;
    }
    
    /* 사이드바 배경색 변경 */
    [data-testid="stSidebar"] {
        background-color: #FFE4E1;
    }
    
    /* 텍스트 폰트 색상 및 굵기 변경 */
    h1, h2, h3, p {
        color: #5C4033 !important; 
        font-family: 'Comic Sans MS', 'Malgun Gothic', sans-serif;
    }
    
    /* 메인 버튼을 귀엽고 둥글게 */
    .stButton>button {
        background-color: #FFB6C1;
        color: white;
        border-radius: 20px;
        border: none;
        box-shadow: 2px 2px 5px rgba(0,0,0,0.1);
        transition: all 0.3s;
    }
    .stButton>button:hover {
        background-color: #FF69B4;
        transform: scale(1.05);
    }
    </style>
    """, unsafe_allow_html=True)

# 2. 메인 화면에 귀여운 애니메이션 캐릭터(GIF) 배치
col1, col2 = st.columns([1, 4])
with col1:
    # Giphy의 귀여운 고양이 해커 GIF 불러오기
    st.image("https://media.giphy.com/media/JIX9t2j0ZTN9S/giphy.gif", width=120)
with col2:
    st.title("🐾 AI 실시간 매수 타점 스캐너 V6")
    st.markdown("**나만의 귀여운 코인 비서가 25개 알트코인을 감시 중이에요!** 🚀")

# 분석 대상 25종으로 확대 (업비트 원화 마켓 고거래량 알트코인)
TARGET_COINS = [
    "KRW-XRP", "KRW-DOGE", "KRW-ADA", "KRW-SEI", "KRW-SUI", 
    "KRW-ALGO", "KRW-STX", "KRW-SAND", "KRW-EOS", "KRW-POL",
    "KRW-TRX", "KRW-SHIB", "KRW-CHZ", "KRW-MANA", "KRW-ENJ",
    "KRW-HBAR", "KRW-ZIL", "KRW-VET", "KRW-SC", "KRW-MOC",
    "KRW-BTT", "KRW-T", "KRW-AERGO", "KRW-IQ", "KRW-ORBS"
]

st.title("🚨 실시간 매수 급소 검출기 V6")
st.markdown("25개 알트코인의 최근 14일 치 5분봉(4,000개)을 학습하여, **현재 즉시 매수해야 할 종목과 정확한 매도 체결가**만 선별해 안내합니다.")

if st.button("🚀 25개 알트코인 전수 스캔 및 타점 포착"):
    progress_bar = st.progress(0)
    status_text = st.empty()
    results = []
    
    for idx, coin in enumerate(TARGET_COINS):
        status_text.text(f"[{idx+1}/{len(TARGET_COINS)}] {coin} 데이터 분석 및 최적화 진행 중...")
        
        # API 제한 방지 및 속도 향상을 위해 4000캔들(약 14일) 사용
        df = pyupbit.get_ohlcv(coin, interval="minute5", count=4000)
        
        if df is not None and len(df) > 500:
            df_signals = apply_strategies(df)
            best_setup = optimize_strategy(df_signals)
            
            last_candle = df_signals.iloc[-1]
            curr_price = pyupbit.get_current_price(coin)
            is_buy_now = last_candle[best_setup["strategy_col"]]
            
            # 매도/손절 틱 단위(소수점 등) 처리 단순화를 위해 float 형태로 보존 후 포맷팅
            tp_price = curr_price * (1 + best_setup["tp_pct"])
            sl_price = curr_price * (1 - best_setup["sl_pct"])
            
            # 오직 "현재 매수 시그널"이 뜬 종목만 결과 리스트에 추가
            if is_buy_now:
                results.append({
                    "코인명": coin.replace("KRW-", ""),
                    "현재가(매수단가)": f"{curr_price:,.4f} 원",
                    "적중 매매법": best_setup["strategy_name"],
                    "예측 승률(백테스트)": f"{best_setup['return']:+.2f}%",
                    "🎯 익절 예약주문가": f"{tp_price:,.4f} 원 (+{best_setup['tp_pct']*100:.1f}%)",
                    "🛡️ 손절 예약주문가": f"{sl_price:,.4f} 원 (-{best_setup['sl_pct']*100:.1f}%)",
                    "_ret": best_setup['return']
                })
                
        time.sleep(0.25) # 다수 코인 스캔 시 업비트 API 차단 방지 딜레이
        progress_bar.progress((idx + 1) / len(TARGET_COINS))
        
    status_text.text("✅ 25개 알트코인 전수 스캔 완료!")
    
    if results:
        res_df = pd.DataFrame(results).sort_values(by="_ret", ascending=False)
        st.success(f"🔥 **총 {len(results)}개의 종목에서 강력 매수 시그널이 포착되었습니다.** 아래 지표를 참고하여 즉시 진입하세요.")
        
        # 화면을 간결하게 구성하기 위해 데이터프레임 하나로 통일
        st.dataframe(
            res_df.drop(columns=["_ret"]), 
            use_container_width=True, 
            hide_index=True
        )
        
        st.info("💡 **매매 가이드:** 위 표의 [현재가] 근처에서 매수한 직후, 업비트 앱에서 [🎯 익절 예약주문가]와 [🛡️ 손절 예약주문가]에 각각 '지정가 매도'를 미리 걸어두세요.")
    else:
        st.warning("⚠️ 현재 25개 알트코인 중, 최적화 매매법의 돌파 타점을 만족하는 종목이 단 하나도 없습니다. 가짜 반등에 속지 말고 현금을 보유하세요.")