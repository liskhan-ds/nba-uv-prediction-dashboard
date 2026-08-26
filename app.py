import streamlit as st
import sqlite3
import pandas as pd
import altair as alt
import os
from datetime import datetime

# -----------------------------------------------------------------------------
# 1. 설정 및 데이터 로드
# -----------------------------------------------------------------------------
st.set_page_config(page_title="NBA AI 승부 예측", page_icon="🏀", layout="wide")

# 실행 경로와 관계없이 DB를 찾을 수 있도록 절대 경로 설정
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "nba_data.db")

def load_data():
    if not os.path.exists(DB_PATH):
        return pd.DataFrame()
    try:
        conn = sqlite3.connect(DB_PATH)
        query = "SELECT * FROM predictions ORDER BY date ASC, rowid ASC"
        df = pd.read_sql(query, conn)
        conn.close()
        return df
    except Exception as e:
        return pd.DataFrame()

df = load_data()

# 제목 및 상단 네비게이션
col_title, col_nav = st.columns([3, 1])
with col_title:
    st.title("🏀 NBA AI 승부예측(by WUV predictor)")
with col_nav:
    st.write("")
    st.link_button("⚾ MLB 대시보드 바로가기 ↗", "https://mlb-uv-prediction-dashboard.streamlit.app/")

if df.empty:
    st.warning("⚠️ 아직 예측 데이터가 없거나 DB를 불러올 수 없습니다. `run_nba.py`를 실행하여 데이터를 적재해주세요.")
    st.stop()

# -----------------------------------------------------------------------------
# [로직 수정] 적중률 계산 및 넘버링 필터링
# -----------------------------------------------------------------------------
# 1. 취소 경기 제외 넘버링
df['total_no'] = None
valid_mask = df['actual_winner'] != 'Postponed'
df.loc[valid_mask, 'total_no'] = range(1, len(df[valid_mask]) + 1)
df['total_no'] = df['total_no'].fillna('취소')

# 2. 통계용 데이터: 취소된 경기도 아니고, 실제 결과(actual_winner)가 기록된 경기만!
stats_df = df[
    (df['actual_winner'] != 'Postponed') & 
    (df['actual_winner'].notna()) & 
    (df['actual_winner'] != '')
].copy()

# -----------------------------------------------------------------------------
# 1. [상단] 누적 예측 성적표 & 100경기 트래킹
# -----------------------------------------------------------------------------
st.header("📊 누적 예측 성적표")
total_stats = len(stats_df)
correct_total = stats_df['is_correct'].sum()

col_acc, col_track = st.columns([2, 1])

if total_stats > 0:
    total_acc = (correct_total / total_stats) * 100
    # 60% 이상이면 '신계' 문구 추가
    status_suffix = " (⚡ 신계, 시장 왜곡급)" if total_acc >= 60 else ""
    
    with col_acc:
        st.subheader(f"전체 예측률: `{total_acc:.2f}%`{status_suffix}")
        st.markdown(f"**적중 경기 수:** {int(correct_total)} / **통산 경기 수:** {total_stats}")
    
    with col_track:
        remaining = 100 - total_stats
        if remaining > 0:
            st.metric("100경기 시스템 검증까지", f"{remaining}경기 남음")
        else:
            st.metric("시스템 검증 상태", "검증 완료 (신계 등급)")
else:
    st.subheader("데이터 수집 중...")

st.markdown("---")

# -----------------------------------------------------------------------------
# 2. [중단] 일별 예측 성적표 (6단계 등급 및 라벨 수정)
# -----------------------------------------------------------------------------
st.header("📈 일별 예측 성적표 (최근 7일)")

if not stats_df.empty:
    daily_stats = stats_df.groupby('date').agg(
        total_games=('home_team', 'count'), 
        correct_games=('is_correct', 'sum') 
    ).reset_index()

    daily_stats['accuracy'] = (daily_stats['correct_games'] / daily_stats['total_games']) * 100
    
    # 6단계 색상 로직 함수
    def get_bar_color(acc):
        if acc >= 60: return '#A020F0'      # 보라 (신계)
        elif acc >= 55: return '#FF0000'    # 빨강 (초고수/AI)
        elif acc >= 52.4: return '#FFA500'  # 주황 (프로/고수)
        elif acc >= 45: return '#1E90FF'    # 파랑 (노력하는 일반인)
        elif acc >= 35: return '#008000'    # 녹색 (지극히 정상인)
        else: return '#808080'             # 회색 (예측 금지)

    daily_stats['bar_color'] = daily_stats['accuracy'].apply(get_bar_color)
    
    # [수정] 모바일 겹침 방지를 위해 예측 성공 숫자만 노출 (예: 6/7)
    daily_stats['label_text'] = daily_stats.apply(
        lambda x: f"{int(x['correct_games'])}/{int(x['total_games'])}", 
        axis=1
    )

    daily_stats_7d = daily_stats.sort_values('date', ascending=True).tail(7)

    base = alt.Chart(daily_stats_7d).encode(x=alt.X('date', title='날짜(미국 현지)'))
    bars = base.mark_bar().encode(
        y=alt.Y('accuracy', title='적중률(%)', scale=alt.Scale(domain=[0, 110])),
        color=alt.Color('bar_color', scale=None),
        tooltip=['date', 'accuracy', 'total_games']
    )
    text = base.mark_text(align='center', baseline='bottom', dy=-5, fontSize=14, fontWeight='bold').encode(
        y='accuracy', text='label_text'
    )
    st.altair_chart((bars + text).properties(height=350), use_container_width=True)
else:
    st.info("통계를 표시할 수 있는 종료된 경기가 아직 없습니다.")

# [수정] 6단계 등급 범례 하단 표시
st.markdown("""
<div style="text-align: center; padding: 12px; background-color: #f0f2f6; border-radius: 10px; line-height: 1.6;">
    <span style="color: #A020F0;">●</span> <b>신계</b> (60%↑) &nbsp;&nbsp;
    <span style="color: #FF0000;">●</span> <b>초고수/AI</b> (55%~60%) &nbsp;&nbsp;
    <span style="color: #FFA500;">●</span> <b>프로/고수</b> (52.4%~55%) &nbsp;&nbsp;
    <span style="color: #1E90FF;">●</span> <b>노력하는 일반인</b> (45%~52.4%) &nbsp;&nbsp;
    <span style="color: #008000;">●</span> <b>지극히 정상인</b> (35%~45%) &nbsp;&nbsp;
    <span style="color: #808080;">●</span> <b>예측 금지</b> (35%↓)
    <br><small>* 52.4%는 통계적 손익분기점(Breakeven) 기준입니다.</small>
</div>
""", unsafe_allow_html=True)

st.markdown("---")

# -----------------------------------------------------------------------------
# 3. [하단] 일별 상세 예측 리포트
# -----------------------------------------------------------------------------
st.header("📋 일별 상세 예측 리포트")

df['date_dt'] = pd.to_datetime(df['date']).dt.date
unique_dates = sorted(df['date_dt'].unique(), reverse=True)

selected_date = st.date_input("확인하고 싶은 날짜를 선택하세요:", value=unique_dates[0])
filtered_df = df[df['date_dt'] == selected_date].copy().reset_index(drop=True)

if not filtered_df.empty:
    filtered_df['day_no'] = None
    day_valid_mask = filtered_df['actual_winner'] != 'Postponed'
    filtered_df.loc[day_valid_mask, 'day_no'] = range(1, len(filtered_df[day_valid_mask]) + 1)
    filtered_df['day_no'] = filtered_df['day_no'].fillna('취소')

    day_stats_mask = (filtered_df['actual_winner'] != 'Postponed') & (filtered_df['actual_winner'].notna()) & (filtered_df['actual_winner'] != '')
    finished_games = filtered_df[day_stats_mask]
    finished_count = len(finished_games)
    
    col1, col2, col3 = st.columns(3)
    col1.metric("해당일 총 경기 수", f"{len(filtered_df)} 경기")
    col2.metric("종료된 경기", f"{finished_count} 경기")
    if finished_count > 0:
        acc = (finished_games['is_correct'].sum() / finished_count) * 100
        col3.metric("일일 적중률", f"{acc:.1f}%")
    else:
        col3.metric("일일 적중률", "-")

    display_df = filtered_df[[
        'day_no', 'total_no', 'home_team', 'visit_team', 
        'predicted_winner', 'predicted_gap', 'actual_winner', 'is_correct'
    ]].copy()
    
    display_df.columns = [
        'No.(Day)', 'No.(Total)', '홈 팀', '원정 팀', 
        '예측 승리팀', '예상 격차(uv)', '실제 승리팀', '적중 여부'
    ]
    
    def mark_ox(row):
        if row['실제 승리팀'] == 'Postponed': return "🆖 취소"
        if pd.isna(row['적중 여부']) or row['실제 승리팀'] == '': return "⏳ 대기"
        return "✅ 정답" if row['적중 여부'] == 1 else "❌ 오답"
    
    display_df['적중 여부'] = display_df.apply(mark_ox, axis=1)
    display_df['예상 격차(uv)'] = display_df['예상 격차(uv)'].apply(lambda x: f"{x:.2f}")
    display_df['실제 승리팀'] = display_df['실제 승리팀'].replace('Postponed', '취소됨').fillna('⏳ 대기 중')

    st.dataframe(display_df, hide_index=True, use_container_width=True)

if st.button("데이터 새로고침"):
    st.rerun()

# -----------------------------------------------------------------------------
# 4. [최하단] 푸터 문구
# -----------------------------------------------------------------------------
st.markdown("---")
st.markdown(
    """
    <div style="text-align: center; color: #888888; padding-top: 20px;">
        <p>ⓒ DROPSHOT (사업자 번호: 578-81-03214)</p>
        <p>Contact us: liskhan@gmail.com</p>
    </div>
    """,
    unsafe_allow_html=True
)
