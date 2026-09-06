import streamlit as st

# -----------------------------------------------------------------------------
# Master League Configuration Registry (Grouped by Sport Category)
# US Sports (4): NBA, MLB, NHL, NFL
# Soccer (6): EPL, La Liga (LLG), Bundesliga (BDL), Serie A (SRA), Ligue 1 (LG1), MLS
# -----------------------------------------------------------------------------
US_SPORTS = [
    {"code": "NBA", "name": "NBA", "icon": "🏀", "url": "https://nba-uv-prediction.streamlit.app/"},
    {"code": "MLB", "name": "MLB", "icon": "⚾", "url": "https://mlb-uv-prediction.streamlit.app/"},
    {"code": "NHL", "name": "NHL", "icon": "🏒", "url": "https://nhl-uv-prediction.streamlit.app/"},
    {"code": "NFL", "name": "NFL", "icon": "🏈", "url": "https://nfl-uv-prediction.streamlit.app/"},
]

SOCCER_LEAGUES = [
    {"code": "EPL", "name": "EPL", "icon": "⚽", "url": "https://epl-uv-prediction.streamlit.app/"},
    {"code": "LLG", "name": "La Liga", "icon": "⚽", "url": "https://llg-uv-prediction.streamlit.app/"},
    {"code": "BDL", "name": "Bundesliga", "icon": "⚽", "url": "https://bdl-uv-prediction.streamlit.app/"},
    {"code": "SRA", "name": "Serie A", "icon": "⚽", "url": "https://sra-uv-prediction.streamlit.app/"},
    {"code": "LG1", "name": "Ligue 1", "icon": "⚽", "url": "https://lg1-uv-prediction.streamlit.app/"},
    {"code": "MLS", "name": "MLS", "icon": "⚽", "url": "https://mls-uv-prediction.streamlit.app/"},
]

def render_common_nav(current_league_code: str):
    """
    Renders a common expandable navigation component across league dashboards.
    - Uses native Streamlit st.link_button for 100% reliable click navigation across all devices.
    """
    all_leagues = US_SPORTS + SOCCER_LEAGUES
    current_item = next((item for item in all_leagues if item["code"] == current_league_code), None)
    current_label = f"{current_item['icon']} {current_item['name']}" if current_item else current_league_code

    is_us = any(item["code"] == current_league_code for item in US_SPORTS)
    
    if is_us:
        first_group = ([current_item] + [i for i in US_SPORTS if i["code"] != current_league_code]) if current_item else US_SPORTS
        second_group = SOCCER_LEAGUES
    else:
        first_group = ([current_item] + [i for i in SOCCER_LEAGUES if i["code"] != current_league_code]) if current_item else SOCCER_LEAGUES
        second_group = US_SPORTS

    with st.expander(f"📍 League Selector: **{current_label}** (Click to switch leagues)", expanded=False):
        # First Sport Group Row
        cols1 = st.columns(len(first_group))
        for idx, item in enumerate(first_group):
            is_current = (item["code"] == current_league_code)
            label = f"{item['icon']} {item['name']}"
            with cols1[idx]:
                if is_current:
                    st.button(f"{label} (Active)", disabled=True, key=f"nav_btn_{item['code']}", use_container_width=True)
                else:
                    st.link_button(f"{label} ↗", item["url"], key=f"nav_link_{item['code']}", use_container_width=True)

        # Second Sport Group Row
        cols2 = st.columns(len(second_group))
        for idx, item in enumerate(second_group):
            is_current = (item["code"] == current_league_code)
            label = f"{item['icon']} {item['name']}"
            with cols2[idx]:
                if is_current:
                    st.button(f"{label} (Active)", disabled=True, key=f"nav_btn_{item['code']}", use_container_width=True)
                else:
                    st.link_button(f"{label} ↗", item["url"], key=f"nav_link_{item['code']}", use_container_width=True)
