"""
================================================================================
[파일명: dashboard.py] - 문구 수정 완료 (미국 동부 ET 명시)
================================================================================
"""
import streamlit as st
import sqlite3
import pandas as pd
import altair as alt
from datetime import datetime

# -----------------------------------------------------------------------------
# 1. 설정 및 데이터 로드
# -----------------------------------------------------------------------------
st.set_page_config(page_title="NBA AI 예측 대시보드", page_icon="🏀", layout="wide")
DB_PATH = "nba_data.db"

def load_data():
    conn = sqlite3.connect(DB_PATH)
    # 날짜순 정렬해서 가져오기
    query = "SELECT * FROM predictions ORDER BY date DESC"
    df = pd.read_sql(query, conn)
    conn.close()
    return df

# 데이터 불러오기
df = load_data()

# 제목
st.title("🏀 NBA UV predictor 승부예측 대시보드")

if df.empty:
    st.warning("아직 데이터가 없습니다. run_nba.py를 실행해주세요.")
    st.stop()

# -----------------------------------------------------------------------------
# 2. [상단] 적중률 추이 그래프 (막대 그래프 + 색상)
# -----------------------------------------------------------------------------
st.header("📊 일별 예측 성적표 (최근 7일)")

# 1) 데이터 가공
daily_stats = df.groupby('date').agg(
    total_games=('home_team', 'count'), 
    correct_games=('is_correct', 'sum') 
).reset_index()

# 적중률(%) 계산
daily_stats['accuracy'] = (daily_stats['correct_games'] / daily_stats['total_games']) * 100
daily_stats['accuracy'] = daily_stats['accuracy'].fillna(0)

# 색상 컬럼을 미리 계산
def get_bar_color(acc):
    if acc >= 65:
        return 'red'
    elif acc >= 50:
        return 'orange'
    else:
        return 'blue'

daily_stats['bar_color'] = daily_stats['accuracy'].apply(get_bar_color)

# 라벨 텍스트 생성
daily_stats['label_text'] = daily_stats.apply(
    lambda x: f"{int(x['correct_games'])}/{int(x['total_games'])} ({x['accuracy']:.1f}%)", 
    axis=1
)

# 최근 7일치만 자르기
daily_stats = daily_stats.sort_values('date', ascending=True).tail(7)

# 2) 그래프 그리기
base = alt.Chart(daily_stats).encode(
    x=alt.X('date', title='날짜')
)

# 막대 그래프
bars = base.mark_bar().encode(
    y=alt.Y('accuracy', title='적중률(%)', scale=alt.Scale(domain=[0, 110])),
    color=alt.Color('bar_color', scale=None),
    tooltip=alt.value(None)
)

# 텍스트 라벨
text = base.mark_text(
    align='center',
    baseline='bottom',
    dy=-5,
    fontSize=14,
    fontWeight='bold'
).encode(
    y='accuracy',
    text='label_text'
)

final_chart = (bars + text).properties(height=350)

st.altair_chart(final_chart, use_container_width=True)

st.markdown("---")

# -----------------------------------------------------------------------------
# 3. [하단] 상세 데이터 (달력 필터)
# -----------------------------------------------------------------------------
st.header("📋 일별 상세 예측 리포트")

# 날짜 컬럼 변환
df['date_dt'] = pd.to_datetime(df['date']).dt.date
unique_dates = sorted(df['date_dt'].unique(), reverse=True)

if not unique_dates:
    st.stop()

# [수정됨] 문구 변경: 확인하고 싶은 날짜(미국 동부 ET)를 선택하세요
selected_date = st.date_input(
    "확인하고 싶은 날짜(미국 동부 ET)를 선택하세요:", 
    value=unique_dates[0],
    min_value=min(unique_dates),
    max_value=max(unique_dates)
)

filtered_df = df[df['date_dt'] == selected_date].copy()

if filtered_df.empty:
    st.info(f"선택하신 날짜 ({selected_date})에는 데이터가 없습니다.")
else:
    total = len(filtered_df)
    finished_games = filtered_df[filtered_df['actual_winner'].notnull()]
    finished_count = len(finished_games)
    
    col1, col2, col3 = st.columns(3)
    col1.metric("총 경기 수", f"{total} 경기")
    
    if finished_count > 0:
        correct = finished_games['is_correct'].sum()
        acc = (correct / finished_count) * 100
        col2.metric("진행된 경기", f"{finished_count} 경기")
        col3.metric("적중률", f"{acc:.1f}%")
    else:
        col2.metric("상태", "경기 예정")
        col3.metric("적중률", "-")

    display_df = filtered_df[['home_team', 'visit_team', 'predicted_winner', 'predicted_gap', 'actual_winner', 'is_correct']]
    display_df.columns = ['홈 팀', '원정 팀', '예측 승리팀', '예상 격차(uv)', '실제 승리팀', '적중 여부']
    
    def mark_ox(val):
        if pd.isna(val): return "⏳ 대기"
        return "✅ 정답" if val == 1 else "❌ 오답"
    
    display_df['적중 여부'] = display_df['적중 여부'].apply(mark_ox)
    display_df['예상 격차(uv)'] = display_df['예상 격차(uv)'].apply(lambda x: f"{x:.2f}")

    st.table(display_df)

if st.button("데이터 새로고침"):
    st.rerun()