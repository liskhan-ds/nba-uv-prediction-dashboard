"""
================================================================================
[파일명: dashboard.py] - NBA AI Predictor
================================================================================
[파일명: dashboard.py] - 그래프 기능 추가 버전
================================================================================
[파일명: dashboard.py] - 그래프 디자인 업그레이드 (Dual Timezone & Last 7 Days)
================================================================================
[파일명: dashboard.py] - 그래프 최종 완성형 (Bar Chart & Conditional Colors)
================================================================================
"""
import streamlit as st
import sqlite3
import pandas as pd
import os
import plotly.graph_objects as go # 막대그래프의 세밀한 제어를 위해 추가
from datetime import datetime, timedelta

# 1. 페이지 설정
st.set_page_config(page_title="NBA AI Predictor", page_icon="🏀", layout="wide")

# 2. DB 로드 함수
def load_data():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    db_path = os.path.join(base_dir, "nba_data.db")
    conn = sqlite3.connect(db_path)
    query = "SELECT * FROM predictions"
    df = pd.read_sql(query, conn)
    conn.close()
    return df

# 3. 타이틀 영역
st.title("🏀 NBA - UV Predictor")
st.markdown("### Allakers x Google Gemini 승부예측 시스템")
st.divider()

# 데이터 불러오기
try:
    df = load_data()
except Exception as e:
    st.error(f"DB Error: {e}")
    st.stop()

if df.empty:
    st.warning("데이터가 없습니다.")
else:
    # 날짜 데이터 전처리
    df['date'] = pd.to_datetime(df['date'])
    df = df.sort_values('date', ascending=True)

    # --- [섹션 1] KPI 지표 ---
    finished = df.dropna(subset=['is_correct'])
    correct = finished[finished['is_correct'] == 1]
    
    acc = 0.0
    if len(finished) > 0:
        acc = (len(correct) / len(finished)) * 100

    c1, c2, c3 = st.columns(3)
    c1.metric("총 예측", f"{len(df)} Game")
    c2.metric("채점 완료", f"{len(finished)} Game")
    c3.metric("누적 적중률", f"{acc:.1f}%")
    
    st.divider()

    # --- [섹션 2] 적중률 그래프 (최종 완성형) ---
    if len(finished) > 0:
        st.subheader("📈 최근 적중률 변화 (Last 7 Days)")
        
        # 1. 일별 데이터 집계 (평균값 + 맞춘 개수 + 전체 개수)
        daily_stats = finished.groupby('date').agg(
            accuracy=('is_correct', 'mean'),
            correct_count=('is_correct', 'sum'),
            total_count=('is_correct', 'count')
        ).reset_index()
        
        daily_stats['accuracy'] = daily_stats['accuracy'] * 100
        
        # 2. 최근 7일치만 자르기
        daily_df = daily_stats.sort_values('date').tail(7).copy()
        
        # 3. X축 라벨 만들기 (KST / US 듀얼 표기)
        def make_dual_label(dt):
            kst_str = dt.strftime("%b %d, %Y")
            us_dt = dt - timedelta(days=1)
            us_str = us_dt.strftime("%b %d, %Y")
            return f"{kst_str}(KST)<br>{us_str}(US-ET)"

        # 4. 색상 결정 함수 (조건부 서식)
        def get_color(acc):
            if acc >= 70: return '#FF4B4B' # 빨강 (Streamlit 기본 레드)
            elif acc >= 50: return '#FFA15A' # 주황
            else: return '#1E90FF' # 파랑

        # 5. 표시 텍스트 만들기 (예: 88.89%(8/9))
        def make_text(row):
            return f"{row['accuracy']:.2f}%({int(row['correct_count'])}/{int(row['total_count'])})"

        # 데이터프레임에 적용
        daily_df['date_label'] = daily_df['date'].apply(make_dual_label)
        daily_df['color'] = daily_df['accuracy'].apply(get_color)
        daily_df['display_text'] = daily_df.apply(make_text, axis=1)

        # 6. 그래프 그리기 (go.Bar 사용)
        fig = go.Figure()
        fig.add_trace(go.Bar(
            x=daily_df['date_label'],
            y=daily_df['accuracy'],
            marker_color=daily_df['color'], # 조건부 색상 적용
            text=daily_df['display_text'],  # 상단 텍스트 적용
            textposition='outside',         # 막대 바깥에 표시
            hoverinfo='none'                # 툴팁 제거
        ))

        # 레이아웃 설정
        # 레이아웃 설정 (bargap 추가)
        fig.update_layout(
            title='일별 적중률 변화 (%)',
            template="plotly_dark",
            yaxis_range=[0, 115], 
            xaxis_title="Date",
            xaxis=dict(type='category'),
            bargap=0.8  # <--- 이 줄을 추가하세요! (0.3은 30%만큼 띄우라는 뜻)
        )
        st.plotly_chart(fig, use_container_width=True)

    # --- [섹션 3] 상세 리스트 (최신순) ---
    st.divider()
    tab1, tab2 = st.tabs(["📅 최근 예측 내역", "📊 데이터 원본"])
    
    # 화면 표시용은 다시 최신순(내림차순) 정렬
    df_display = df.sort_values('date', ascending=False)
    
    with tab1:
        dates = df_display['date'].dt.strftime('%Y-%m-%d').unique()
        for date in dates:
            st.caption(f"📅 {date}")
            day_df = df_display[df_display['date'].dt.strftime('%Y-%m-%d') == date]
            
            for _, row in day_df.iterrows():
                with st.container():
                    c1, c2, c3, c4, c5 = st.columns([1, 2, 1, 2, 1])
                    icon = "⏳"
                    if pd.notna(row['is_correct']):
                        icon = "✅ 적중" if row['is_correct'] == 1 else "❌ 실패"
                    
                    c1.text(icon)
                    c2.write(f"**{row['visit_team']}**")
                    c3.write("vs")
                    c4.write(f"**{row['home_team']}**")
                    
                    pick = row['predicted_winner']
                    gap = row['predicted_gap']
                    
                    if pd.notna(row['is_correct']) and row['is_correct'] == 0:
                        c5.error(f"Pick: {pick}\n(Gap: {gap:.2f})")
                    else:
                        c5.info(f"Pick: {pick}\n(Gap: {gap:.2f})")
                        
                st.markdown("---")

    with tab2:
        st.dataframe(df_display)