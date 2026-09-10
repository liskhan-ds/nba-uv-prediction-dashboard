import streamlit as st

US_SPORTS = [
    {"code": "NBA", "name": "NBA", "icon": "🏀", "url": "https://nba-uv-prediction.streamlit.app/"},
    {"code": "MLB", "name": "MLB", "icon": "⚾", "url": "https://mlb-uv-prediction.streamlit.app/"},
    {"code": "NHL", "name": "NHL", "icon": "🏒", "url": "https://nhl-uv-prediction.streamlit.app/"},
    {"code": "NFL", "name": "NFL", "icon": "🏈", "url": "https://nfl-uv-prediction.streamlit.app/"},
]

def render_common_nav(current_league_code: str):
    current_item = next((item for item in US_SPORTS if item["code"] == current_league_code), None)
    current_label = f"{current_item['icon']} {current_item['name']}" if current_item else current_league_code

    with st.expander(f"📍 League Selector: **{current_label}**", expanded=False):
        cols = st.columns(len(US_SPORTS))
        for idx, item in enumerate(US_SPORTS):
            is_current = (item["code"] == current_league_code)
            label = f"{item['icon']} {item['name']}"
            with cols[idx]:
                if is_current:
                    st.button(f"{label} (Active)", disabled=True, key=f"nav_btn_{item['code']}", use_container_width=True)
                else:
                    st.link_button(f"{label} ↗", item["url"], key=f"nav_link_{item['code']}", use_container_width=True)
