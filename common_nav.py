import streamlit as st

# -----------------------------------------------------------------------------
# Master League Configuration Registry
# Add or update any new league here to update across all dashboards.
# -----------------------------------------------------------------------------
LEAGUES_CONFIG = [
    {"code": "NBA", "name": "NBA", "icon": "🏀", "url": "https://nba-uv-prediction.streamlit.app/"},
    {"code": "MLB", "name": "MLB", "icon": "⚾", "url": "https://mlb-uv-prediction.streamlit.app/"},
    {"code": "EPL", "name": "EPL", "icon": "⚽", "url": "https://epl-uv-prediction.streamlit.app/"},
    {"code": "LLG", "name": "La Liga", "icon": "⚽", "url": "https://llg-uv-prediction.streamlit.app/"},
    {"code": "NHL", "name": "NHL", "icon": "🏒", "url": "https://nhl-uv-prediction.streamlit.app/"},
    {"code": "NFL", "name": "NFL", "icon": "🏈", "url": "https://nfl-uv-prediction.streamlit.app/"},
    {"code": "MLS", "name": "MLS", "icon": "⚽", "url": "https://mls-uv-prediction.streamlit.app/"},
]

def render_common_nav(current_league_code: str):
    """
    Renders a common expandable navigation component across league dashboards.
    - Default state: Collapsed (expanded=False).
    - Top line: Shows current active league label.
    - Expanded view: Shows grid buttons/links for all leagues with target="_self" (same tab navigation).
    """
    current_item = next((item for item in LEAGUES_CONFIG if item["code"] == current_league_code), None)
    current_label = f"{current_item['icon']} {current_item['name']}" if current_item else current_league_code

    with st.expander(f"📍 League Selector: **{current_label}** (Click to switch leagues)", expanded=False):
        cols = st.columns(len(LEAGUES_CONFIG))
        for idx, item in enumerate(LEAGUES_CONFIG):
            is_current = (item["code"] == current_league_code)
            label = f"{item['icon']} {item['name']}"
            with cols[idx]:
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
                        ">{label} ↗</a>''',
                        unsafe_allow_html=True
                    )
