"""
================================================================================
[파일명: dashboard.py] - 넘버링 시스템 적용 (디자인 수정 전 안정화 버전)
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
    # 누적 번호 계산을 위해 일단 날짜순(오름차순)으로 가져옴
    query = "SELECT * FROM predictions ORDER BY date ASC, rowid ASC"
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
# [NEW] 넘버링 로직 (족보 정리)
# -----------------------------------------------------------------------------
# 1. 누적 경기 수 (Total No) 계산 : 1월 19일부터 순서대로 1, 2, 3... 부여
df['total_no'] = range(1, len(df) + 1)

# -----------------------------------------------------------------------------
# 2. [상단] 적중률 추이 그래프 (최근 7일)
# -----------------------------------------------------------------------------
st.header("📊 일별 예측 성적표 (최근 7일)")

# 취소된 경기 제외하고 통계용 데이터 생성
valid_df = df[df['actual_winner'] != 'Postponed'].copy()

# 데이터 가공
daily_stats = valid_df.groupby('date').agg(
    total_games=('home_team', 'count'), 
    correct_games=('is_correct', 'sum') 
).reset_index()

# 적중률(%) 계산
daily_stats['accuracy'] = (daily_stats['correct_games'] / daily_stats['total_games']) * 100
daily_stats['accuracy'] = daily_stats['accuracy'].fillna(0)

# 색상 컬럼 계산
def get_bar_color(acc):
    if acc >= 65: return 'red'
    elif acc >= 50: return 'orange'
    else: return 'blue'

daily_stats['bar_color'] = daily_stats['accuracy'].apply(get_bar_color)

# 라벨 텍스트
daily_stats['label_text'] = daily_stats.apply(
    lambda x: f"{int(x['correct_games'])}/{int(x['total_games'])} ({x['accuracy']:.1f}%)", 
    axis=1
)

# 최근 7일치만 자르기
daily_stats = daily_stats.sort_values('date', ascending=True).tail(7)

# 그래프 그리기
base = alt.Chart(daily_stats).encode(x=alt.X('date', title='날짜'))
bars = base.mark_bar().encode(
    y=alt.Y('accuracy', title='적중률(%)', scale=alt.Scale(domain=[0, 110])),
    color=alt.Color('bar_color', scale=None),
    tooltip=['date', 'accuracy', 'total_games']
)
text = base.mark_text(align='center', baseline='bottom', dy=-5, fontSize=14, fontWeight='bold').encode(
    y='accuracy', text='label_text'
)
final_chart = (bars + text).properties(height=350)
st.altair_chart(final_chart, use_container_width=True)

st.markdown("---")

# -----------------------------------------------------------------------------
# 3. [하단] 상세 데이터 (넘버링 적용)
# -----------------------------------------------------------------------------
st.header("📋 일별 상세 예측 리포트")

# 날짜 선택을 위해 다시 내림차순 정렬된 리스트 생성
df['date_dt'] = pd.to_datetime(df['date']).dt.date
unique_dates = sorted(df['date_dt'].unique(), reverse=True)

if not unique_dates:
    st.stop()

selected_date = st.date_input(
    "확인하고 싶은 날짜(미국 동부 ET)를 선택하세요:", 
    value=unique_dates[0],
    min_value=min(unique_dates),
    max_value=max(unique_dates)
)

# 해당 날짜 데이터 필터링
filtered_df = df[df['date_dt'] == selected_date].copy()

if filtered_df.empty:
    st.info(f"선택하신 날짜 ({selected_date})에는 데이터가 없습니다.")
else:
    # 2. 일별 경기 순번 (Day No) 계산: 해당 날짜 내에서 1, 2, 3... 부여
    filtered_df = filtered_df.reset_index(drop=True)
    filtered_df['day_no'] = range(1, len(filtered_df) + 1)

    # 통계 계산
    total = len(filtered_df)
    postponed_count = len(filtered_df[filtered_df['actual_winner'] == 'Postponed'])
    finished_games = filtered_df[
        (filtered_df['actual_winner'].notnull()) & 
        (filtered_df['actual_winner'] != 'Postponed')
    ]
    finished_count = len(finished_games)
    
    # 메트릭 표시
    col1, col2, col3 = st.columns(3)
    if postponed_count > 0:
        col1.metric("총 경기 수", f"{total} 경기", f"(취소 {postponed_count})", delta_color="off")
    else:
        col1.metric("총 경기 수", f"{total} 경기")
    
    if finished_count > 0:
        correct = finished_games['is_correct'].sum()
        acc = (correct / finished_count) * 100
        col2.metric("진행된 경기", f"{finished_count} 경기")
        col3.metric("적중률", f"{acc:.1f}%")
    else:
        status_msg = "전 경기 취소" if (postponed_count == total and total > 0) else "경기 예정/진행중"
        col2.metric("상태", status_msg)
        col3.metric("적중률", "-")

    # 테이블 컬럼 구성 및 한글 매핑
    display_df = filtered_df[[
        'day_no', 'total_no', 'home_team', 'visit_team', 
        'predicted_winner', 'predicted_gap', 'actual_winner', 'is_correct'
    ]].copy()
    
    display_df.columns = [
        'No.(Day)', 'No.(Total)', '홈 팀', '원정 팀', 
        '예측 승리팀', '예상 격차(uv)', '실제 승리팀', '적중 여부'
    ]
    
    # OX 마킹 및 서식
    def mark_ox(row):
        actual = row['실제 승리팀']
        is_cor = row['적중 여부']
        if actual == 'Postponed': return "🆖 취소"
        if pd.isna(is_cor): return "⏳ 대기"
        return "✅ 정답" if is_cor == 1 else "❌ 오답"
    
    display_df['적중 여부'] = display_df.apply(mark_ox, axis=1)
    display_df['예상 격차(uv)'] = display_df['예상 격차(uv)'].apply(lambda x: f"{x:.2f}")
    display_df['실제 승리팀'] = display_df['실제 승리팀'].replace('Postponed', '취소됨')

    # [원복 완료] 복잡한 column_config 없이 깔끔하게 출력
    st.dataframe(
        display_df,
        hide_index=True,
        use_container_width=True
    )

if st.button("데이터 새로고침"):
    st.rerun()