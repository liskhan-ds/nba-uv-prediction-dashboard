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
[파일명: dashboard.py] - UI/UX Final Upgrade (Logo, Mobile, Actual Result)
================================================================================
[파일명: dashboard.py] - UI/UX Final Upgrade (Fix: Syntax Error)
================================================================================
"""
import streamlit as st
import sqlite3
import pandas as pd
import os
import plotly.graph_objects as go
from datetime import datetime, timedelta

# 1. 페이지 설정
st.set_page_config(page_title="NBA AI Predictor", page_icon="🏀", layout="wide")

# --- [추가] NBA 로고 URL 딕셔너리 ---
TEAM_LOGOS = {
    'ATL': 'https://upload.wikimedia.org/wikipedia/en/2/24/Atlanta_Hawks_logo.svg',
    'BOS': 'https://upload.wikimedia.org/wikipedia/en/8/8f/Boston_Celtics.svg',
    'BKN': 'https://upload.wikimedia.org/wikipedia/commons/4/44/Brooklyn_Nets_newlogo.svg',
    'CHA': 'https://upload.wikimedia.org/wikipedia/en/c/c4/Charlotte_Hornets_%282014%29.svg',
    'CHI': 'https://upload.wikimedia.org/wikipedia/en/6/67/Chicago_Bulls_logo.svg',
    'CLE': 'https://upload.wikimedia.org/wikipedia/en/4/4b/Cleveland_Cavaliers_logo.svg',
    'DAL': 'https://upload.wikimedia.org/wikipedia/en/9/97/Dallas_Mavericks_logo14.svg',
    'DEN': 'https://upload.wikimedia.org/wikipedia/en/7/76/Denver_Nuggets.svg',
    'DET': 'https://upload.wikimedia.org/wikipedia/commons/7/7c/Pistons_logo17.svg',
    'GSW': 'https://upload.wikimedia.org/wikipedia/en/0/01/Golden_State_Warriors_logo.svg',
    'HOU': 'https://upload.wikimedia.org/wikipedia/en/2/28/Houston_Rockets.svg',
    'IND': 'https://upload.wikimedia.org/wikipedia/en/1/1b/Indiana_Pacers.svg',
    'LAC': 'https://upload.wikimedia.org/wikipedia/en/b/bb/Los_Angeles_Clippers_%282015%29.svg',
    'LAL': 'https://upload.wikimedia.org/wikipedia/commons/3/3c/Los_Angeles_Lakers_logo.svg',
    'MEM': 'https://upload.wikimedia.org/wikipedia/en/f/f1/Memphis_Grizzlies.svg',
    'MIA': 'https://upload.wikimedia.org/wikipedia/en/f/fb/Miami_Heat_logo.svg',
    'MIL': 'https://upload.wikimedia.org/wikipedia/en/4/4a/Milwaukee_Bucks_logo.svg',
    'MIN': 'https://upload.wikimedia.org/wikipedia/en/c/c2/Minnesota_Timberwolves_logo.svg',
    'NOP': 'https://upload.wikimedia.org/wikipedia/en/0/0d/New_Orleans_Pelicans_logo.svg',
    'NYK': 'https://upload.wikimedia.org/wikipedia/en/2/25/New_York_Knicks_logo.svg',
    'OKC': 'https://upload.wikimedia.org/wikipedia/en/5/5d/Oklahoma_City_Thunder.svg',
    'ORL': 'https://upload.wikimedia.org/wikipedia/en/1/10/Orlando_Magic_logo.svg',
    'PHI': 'https://upload.wikimedia.org/wikipedia/en/0/0e/Philadelphia_76ers_logo.svg',
    'PHX': 'https://upload.wikimedia.org/wikipedia/en/5/56/Phoenix_Suns_logo.svg',
    'POR': 'https://upload.wikimedia.org/wikipedia/en/2/21/Portland_Trail_Blazers_logo.svg',
    'SAC': 'https://upload.wikimedia.org/wikipedia/en/c/c7/SacramentoKings.svg',
    'SAS': 'https://upload.wikimedia.org/wikipedia/en/a/a2/San_Antonio_Spurs.svg',
    'TOR': 'https://upload.wikimedia.org/wikipedia/en/3/36/Toronto_Raptors_logo.svg',
    'UTA': 'https://upload.wikimedia.org/wikipedia/en/0/04/Utah_Jazz_logo_%282016%29.svg',
    'WAS': 'https://upload.wikimedia.org/wikipedia/en/0/02/Washington_Wizards_logo.svg'
}

def get_logo_html(team_abbr, width=25):
    """HTML 태그로 로고 이미지 생성"""
    url = TEAM_LOGOS.get(team_abbr, "")
    if url:
        return f'<img src="{url}" width="{width}" style="vertical-align:middle; margin-right:5px;">'
    return ""

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

try:
    df = load_data()
except Exception as e:
    st.error(f"DB Error: {e}")
    st.stop()

if df.empty:
    st.warning("데이터가 없습니다.")
else:
    df['date'] = pd.to_datetime(df['date'])
    df = df.sort_values('date', ascending=True)

    # --- [KPI 섹션] ---
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

    # --- [그래프 섹션] ---
    if len(finished) > 0:
        st.subheader("📈 최근 적중률 변화 (Last 7 Days)")
        
        daily_stats = finished.groupby('date').agg(
            accuracy=('is_correct', 'mean'),
            correct_count=('is_correct', 'sum'),
            total_count=('is_correct', 'count')
        ).reset_index()
        
        daily_stats['accuracy'] = daily_stats['accuracy'] * 100
        daily_df = daily_stats.sort_values('date').tail(7).copy()
        
        def make_dual_label(dt):
            kst_str = dt.strftime("%b %d")
            return f"{kst_str}"

        def get_color(acc):
            if acc >= 70: return '#FF4B4B'
            elif acc >= 50: return '#FFA15A'
            else: return '#1E90FF'

        def make_text(row):
            return f"{row['accuracy']:.1f}%({int(row['correct_count'])}/{int(row['total_count'])})"

        daily_df['date_label'] = daily_df['date'].apply(make_dual_label)
        daily_df['color'] = daily_df['accuracy'].apply(get_color)
        daily_df['display_text'] = daily_df.apply(make_text, axis=1)

        fig = go.Figure()
        fig.add_trace(go.Bar(
            x=daily_df['date_label'],
            y=daily_df['accuracy'],
            marker_color=daily_df['color'],
            text=daily_df['display_text'],
            textposition='outside',
            hoverinfo='none'
        ))

        fig.update_layout(
            title='',
            template="plotly_dark",
            yaxis_range=[0, 115],
            bargap=0.3,
            margin=dict(l=20, r=20, t=30, b=20)
        )
        st.plotly_chart(fig, use_container_width=True)

    # --- [리스트 섹션] (모바일 최적화) ---
    st.divider()
    tab1, tab2 = st.tabs(["📅 경기 예측 리스트", "📊 원본 데이터"])
    
    df_display = df.sort_values('date', ascending=False)
    
    with tab1:
        dates = df_display['date'].dt.strftime('%Y-%m-%d').unique()
        for date in dates:
            # 날짜 헤더 (크게)
            st.markdown(f"#### 📅 {date}")
            
            day_df = df_display[df_display['date'].dt.strftime('%Y-%m-%d') == date]
            
            for _, row in day_df.iterrows():
                # 모바일 최적화를 위해 2개 컬럼으로 단순화
                c_match, c_result = st.columns([1.5, 1])
                
                with c_match:
                    v_logo = get_logo_html(row['visit_team'])
                    h_logo = get_logo_html(row['home_team'])
                    
                    st.markdown(
                        f"""
                        <div style="display:flex; align-items:center; height:100%;">
                            <span style="font-size:16px; font-weight:bold;">
                                {v_logo} {row['visit_team']} <span style="color:#aaa; margin:0 5px;">vs</span> {h_logo} {row['home_team']}
                            </span>
                        </div>
                        """, 
                        unsafe_allow_html=True
                    )

                with c_result:
                    pick = row['predicted_winner']
                    actual = row['actual_winner']
                    
                    if pd.isna(row['is_correct']):
                        st.info(f"🤖 Pick: {pick}")
                    elif row['is_correct'] == 1:
                        st.success(f"✅ Pick: {pick} / 실제: {actual}")
                    else:
                        st.error(f"❌ Pick: {pick} / 실제: {actual}")
                
                st.markdown("---") # 구분선

    with tab2:
        st.dataframe(df_display)