import streamlit as st
import sqlite3
import pandas as pd
import altair as alt
import os
from datetime import datetime

# -----------------------------------------------------------------------------
# 1. Page Configuration & Data Loading
# -----------------------------------------------------------------------------
st.set_page_config(page_title="NBA AI Prediction", page_icon="🏀", layout="wide")

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

# Top Navigation Tabs (7 Sports)
# Top Navigation Bar (7 Leagues)
nav_cols = st.columns(7)
with nav_cols[0]:
    st.button("🏀 NBA (Current)", disabled=True, use_container_width=True)
with nav_cols[1]:
    st.link_button("⚾ MLB ↗", "https://mlb-uv-prediction.streamlit.app/", use_container_width=True)
with nav_cols[2]:
    st.link_button("⚽ EPL ↗", "https://epl-uv-prediction.streamlit.app/", use_container_width=True)
with nav_cols[3]:
    st.link_button("⚽ La Liga ↗", "https://llg-uv-prediction.streamlit.app/", use_container_width=True)
with nav_cols[4]:
    st.link_button("🏒 NHL ↗", "https://nhl-uv-prediction.streamlit.app/", use_container_width=True)
with nav_cols[5]:
    st.link_button("🏈 NFL ↗", "https://nfl-uv-prediction.streamlit.app/", use_container_width=True)
with nav_cols[6]:
    st.link_button("⚽ MLS ↗", "https://mls-uv-prediction.streamlit.app/", use_container_width=True)

st.divider()

st.title("🏀 NBA AI Game Predictions (by WUV Predictor)")

if df.empty:
    st.warning("⚠️ No prediction data available or unable to load database. Please run `run_nba.py` to populate data.")
    st.stop()

# -----------------------------------------------------------------------------
# Data Processing
# -----------------------------------------------------------------------------
df['total_no'] = None
valid_mask = df['actual_winner'] != 'Postponed'
df.loc[valid_mask, 'total_no'] = range(1, len(df[valid_mask]) + 1)
df['total_no'] = df['total_no'].fillna('Canceled')

stats_df = df[
    (df['actual_winner'] != 'Postponed') & 
    (df['actual_winner'].notna()) & 
    (df['actual_winner'] != '')
].copy()

# -----------------------------------------------------------------------------
# 1. Cumulative Prediction Scorecard
# -----------------------------------------------------------------------------
st.header("📊 Cumulative Prediction Scorecard")
total_stats = len(stats_df)
correct_total = stats_df['is_correct'].sum()

col_acc, col_track = st.columns([2, 1])

if total_stats > 0:
    total_acc = (correct_total / total_stats) * 100
    status_suffix = " (⚡ God-tier, Market-distorting)" if total_acc >= 60 else ""
    
    with col_acc:
        st.subheader(f"Overall Accuracy: `{total_acc:.2f}%`{status_suffix}")
        st.markdown(f"**Correct Predictions:** {int(correct_total)} / **Total Games:** {total_stats}")
    
    with col_track:
        remaining = 100 - total_stats
        if remaining > 0:
            st.metric("System Verification (100 Games)", f"{remaining} games left")
        else:
            st.metric("System Verification Status", "Verified (God-tier)")
else:
    st.subheader("Collecting data...")

st.markdown("---")

# -----------------------------------------------------------------------------
# 2. Daily Prediction Scorecard (Last 7 Days)
# -----------------------------------------------------------------------------
st.header("📈 Daily Prediction Scorecard (Last 7 Days)")

if not stats_df.empty:
    daily_stats = stats_df.groupby('date').agg(
        total_games=('home_team', 'count'), 
        correct_games=('is_correct', 'sum') 
    ).reset_index()

    daily_stats['accuracy'] = (daily_stats['correct_games'] / daily_stats['total_games']) * 100
    
    def get_bar_color(acc):
        if acc >= 60: return '#A020F0'      # Purple (God-tier)
        elif acc >= 55: return '#FF0000'    # Red (Master/AI)
        elif acc >= 52.4: return '#FFA500'  # Orange (Pro)
        elif acc >= 45: return '#1E90FF'    # Blue (Average)
        elif acc >= 35: return '#008000'    # Green (Casual)
        else: return '#808080'             # Gray (No Prediction)

    daily_stats['bar_color'] = daily_stats['accuracy'].apply(get_bar_color)
    
    daily_stats['label_text'] = daily_stats.apply(
        lambda x: f"{int(x['correct_games'])}/{int(x['total_games'])}", 
        axis=1
    )

    daily_stats_7d = daily_stats.sort_values('date', ascending=True).tail(7)

    base = alt.Chart(daily_stats_7d).encode(x=alt.X('date', title='Date (US Local)'))
    bars = base.mark_bar().encode(
        y=alt.Y('accuracy', title='Accuracy (%)', scale=alt.Scale(domain=[0, 110])),
        color=alt.Color('bar_color', scale=None),
        tooltip=['date', 'accuracy', 'total_games']
    )
    text = base.mark_text(align='center', baseline='bottom', dy=-5, fontSize=14, fontWeight='bold').encode(
        y='accuracy', text='label_text'
    )
    st.altair_chart((bars + text).properties(height=350), use_container_width=True)
else:
    st.info("No completed games available for statistics yet.")

st.markdown("""
<div style="text-align: center; padding: 12px; background-color: #f0f2f6; border-radius: 10px; line-height: 1.6;">
    <span style="color: #A020F0;">●</span> <b>God-Tier</b> (60%↑) &nbsp;&nbsp;
    <span style="color: #FF0000;">●</span> <b>Master/AI</b> (55%~60%) &nbsp;&nbsp;
    <span style="color: #FFA500;">●</span> <b>Pro</b> (52.4%~55%) &nbsp;&nbsp;
    <span style="color: #1E90FF;">●</span> <b>Average</b> (45%~52.4%) &nbsp;&nbsp;
    <span style="color: #008000;">●</span> <b>Casual</b> (35%~45%) &nbsp;&nbsp;
    <span style="color: #808080;">●</span> <b>No Prediction</b> (35%↓)
    <br><small>* 52.4% represents the statistical breakeven threshold.</small>
</div>
""", unsafe_allow_html=True)

st.markdown("---")

# -----------------------------------------------------------------------------
# 3. Daily Detailed Prediction Report
# -----------------------------------------------------------------------------
st.header("📋 Daily Detailed Prediction Report")

df['date_dt'] = pd.to_datetime(df['date']).dt.date
unique_dates = sorted(df['date_dt'].unique(), reverse=True)

selected_date = st.date_input("Select Date:", value=unique_dates[0])
filtered_df = df[df['date_dt'] == selected_date].copy().reset_index(drop=True)

if not filtered_df.empty:
    filtered_df['day_no'] = None
    day_valid_mask = filtered_df['actual_winner'] != 'Postponed'
    filtered_df.loc[day_valid_mask, 'day_no'] = range(1, len(filtered_df[day_valid_mask]) + 1)
    filtered_df['day_no'] = filtered_df['day_no'].fillna('Canceled')

    day_stats_mask = (filtered_df['actual_winner'] != 'Postponed') & (filtered_df['actual_winner'].notna()) & (filtered_df['actual_winner'] != '')
    finished_games = filtered_df[day_stats_mask]
    finished_count = len(finished_games)
    
    col1, col2, col3 = st.columns(3)
    col1.metric("Total Games", f"{len(filtered_df)} games")
    col2.metric("Finished Games", f"{finished_count} games")
    if finished_count > 0:
        acc = (finished_games['is_correct'].sum() / finished_count) * 100
        col3.metric("Daily Accuracy", f"{acc:.1f}%")
    else:
        col3.metric("Daily Accuracy", "-")

    display_df = filtered_df[[
        'day_no', 'total_no', 'home_team', 'visit_team', 
        'predicted_winner', 'predicted_gap', 'actual_winner', 'is_correct'
    ]].copy()
    
    display_df.columns = [
        'No. (Day)', 'No. (Total)', 'Home Team', 'Away Team', 
        'Predicted Winner', 'Predicted Gap (UV)', 'Actual Winner', 'Result'
    ]
    
    def mark_ox(row):
        if row['Actual Winner'] == 'Postponed': return "🆖 Canceled"
        if pd.isna(row['Result']) or row['Actual Winner'] == '': return "⏳ Pending"
        return "✅ Correct" if row['Result'] == 1 else "❌ Incorrect"
    
    display_df['Result'] = display_df.apply(mark_ox, axis=1)
    display_df['Predicted Gap (UV)'] = display_df['Predicted Gap (UV)'].apply(lambda x: f"{x:.2f}")
    display_df['Actual Winner'] = display_df['Actual Winner'].replace('Postponed', 'Canceled').fillna('⏳ Pending')

    st.dataframe(display_df, hide_index=True, use_container_width=True, height=600)

# -----------------------------------------------------------------------------
# 4. Footer
# -----------------------------------------------------------------------------
st.markdown("---")
st.markdown(
    """
    <div style="text-align: center; color: #888888; padding-top: 20px;">
        <p>ⓒ DROPSHOT (Business Reg. No: 578-81-03214)</p>
        <p>Contact us: liskhan@gmail.com</p>
    </div>
    """,
    unsafe_allow_html=True
)