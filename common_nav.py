import streamlit as st

# -----------------------------------------------------------------------------
# Master League Configuration Registry (Grouped by Sport Category)
# US Sports (4): NBA, MLB, NHL, NFL
# Soccer Leagues (6): EPL, La Liga (LLG), Bundesliga (BDL), Serie A (SRA), Ligue 1 (LG1), MLS
# -----------------------------------------------------------------------------
DEFAULT_LEAGUES_ORDER = [
    {"code": "NBA", "name": "NBA", "icon": "🏀", "url": "https://nba-uv-prediction-dashboard.streamlit.app/"},
    {"code": "MLB", "name": "MLB", "icon": "⚾", "url": "https://mlb-uv-prediction-dashboard.streamlit.app/"},
    {"code": "NHL", "name": "NHL", "icon": "🏒", "url": "https://nhl-uv-prediction-dashboard.streamlit.app/"},
    {"code": "NFL", "name": "NFL", "icon": "🏈", "url": "https://nfl-uv-prediction-dashboard.streamlit.app/"},
    {"code": "EPL", "name": "EPL", "icon": "⚽", "url": "https://epl-uv-prediction-dashboard.streamlit.app/"},
    {"code": "LLG", "name": "La Liga", "icon": "⚽", "url": "https://llg-uv-prediction.streamlit.app/"},
    {"code": "BDL", "name": "Bundesliga", "icon": "⚽", "url": "https://bdl-uv-prediction-dashboard.streamlit.app/"},
    {"code": "SRA", "name": "Serie A", "icon": "⚽", "url": "https://sra-uv-prediction-dashboard.streamlit.app/"},
    {"code": "LG1", "name": "Ligue 1", "icon": "⚽", "url": "https://lg1-uv-prediction-dashboard.streamlit.app/"},
    {"code": "MLS", "name": "MLS", "icon": "⚽", "url": "https://mls-uv-prediction.streamlit.app/"},
]

def render_common_nav(current_league_code: str):
    """
    Renders a common expandable navigation component across league dashboards.
    - Default state: Collapsed (expanded=False).
    - Top line: Shows current active league label.
    - Active League Rule: Current league comes FIRST, followed by others in grouped order.
    """
    current_item = next((item for item in DEFAULT_LEAGUES_ORDER if item["code"] == current_league_code), None)
    current_label = f"{current_item['icon']} {current_item['name']}" if current_item else current_league_code

    # Place current active league FIRST, followed by the rest in default grouped order
    other_items = [item for item in DEFAULT_LEAGUES_ORDER if item["code"] != current_league_code]
    ordered_leagues = [current_item] + other_items if current_item else DEFAULT_LEAGUES_ORDER

    with st.expander(f"📍 League Selector: **{current_label}** (Click to switch leagues)", expanded=False):
        cols = st.columns(5)  # 5 columns per row (2 rows total)
        for idx, item in enumerate(ordered_leagues):
            is_current = (item["code"] == current_league_code)
            label = f"{item['icon']} {item['name']}"
            col_idx = idx % 5
            with cols[col_idx]:
                if is_current:
                    st.button(f"{label} (Active)", disabled=True, key=f"nav_btn_{item['code']}", use_container_width=True)
                else:
                    st.markdown(
                        f'''<a href="{item['url']}" target="_self" style="
                            display: block;
                            width: 100%;
                            padding: 0.45rem 0.2rem;
                            background-color: #f0f2f6;
                            color: #31333F;
                            text-align: center;
                            text-decoration: none;
                            border-radius: 8px;
                            font-size: 13px;
                            font-weight: 600;
                            border: 1px solid #d6d8db;
                            margin-bottom: 0.5rem;
                        ">{label} ↗</a>''',
                        unsafe_allow_html=True
                    )
