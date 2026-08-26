import sqlite3
import pandas as pd
import os
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
from nba_api.stats.endpoints import leaguedashplayerstats, leaguedashteamstats, scoreboardv2
from thefuzz import fuzz

# --- 설정 ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "nba_data.db")
SEASON = '2025-26'
COACH_BONUS_VAL = 0.15

TEAMS = {
    'ATL': {'id': '1610612737', 'slug': 'atl/atlanta-hawks'}, 'BOS': {'id': '1610612738', 'slug': 'bos/boston-celtics'},
    'BKN': {'id': '1610612751', 'slug': 'bkn/brooklyn-nets'}, 'CHA': {'id': '1610612766', 'slug': 'cha/charlotte-hornets'},
    'CHI': {'id': '1610612741', 'slug': 'chi/chicago-bulls'}, 'CLE': {'id': '1610612739', 'slug': 'cle/cleveland-cavaliers'},
    'DAL': {'id': '1610612742', 'slug': 'dal/dallas-mavericks'}, 'DEN': {'id': '1610612743', 'slug': 'den/denver-nuggets'},
    'DET': {'id': '1610612765', 'slug': 'det/detroit-pistons'}, 'GSW': {'id': '1610612744', 'slug': 'gs/golden-state-warriors'},
    'HOU': {'id': '1610612745', 'slug': 'hou/houston-rockets'}, 'IND': {'id': '1610612754', 'slug': 'ind/indiana-pacers'},
    'LAC': {'id': '1610612746', 'slug': 'lac/los-angeles-clippers'}, 'LAL': {'id': '1610612747', 'slug': 'lal/los-angeles-lakers'},
    'MEM': {'id': '1610612763', 'slug': 'mem/memphis-grizzlies'}, 'MIA': {'id': '1610612748', 'slug': 'mia/miami-heat'},
    'MIL': {'id': '1610612749', 'slug': 'mil/milwaukee-bucks'}, 'MIN': {'id': '1610612750', 'slug': 'min/minnesota-timberwolves'},
    'NOP': {'id': '1610612740', 'slug': 'no/new-orleans-pelicans'}, 'NYK': {'id': '1610612752', 'slug': 'ny/new-york-knicks'},
    'OKC': {'id': '1610612760', 'slug': 'okc/oklahoma-city-thunder'}, 'ORL': {'id': '1610612753', 'slug': 'orl/orlando-magic'},
    'PHI': {'id': '1610612755', 'slug': 'phi/philadelphia-76ers'}, 'PHX': {'id': '1610612756', 'slug': 'phx/phoenix-suns'},
    'POR': {'id': '1610612757', 'slug': 'por/portland-trail-blazers'}, 'SAC': {'id': '1610612758', 'slug': 'sac/sacramento-kings'},
    'SAS': {'id': '1610612759', 'slug': 'sa/san-antonio-spurs'}, 'TOR': {'id': '1610612761', 'slug': 'tor/toronto-raptors'},
    'UTA': {'id': '1610612762', 'slug': 'utah/utah-jazz'}, 'WAS': {'id': '1610612764', 'slug': 'wsh/washington-wizards'},
}
ID_TO_ABBR = {v['id']: k for k, v in TEAMS.items()}

def get_out_players(team_slug):
    out_list = []
    url = f"https://www.espn.com/nba/team/injuries/_/name/{team_slug}"
    try:
        res = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'})
        soup = BeautifulSoup(res.text, 'html.parser')
        for row in soup.find_all('tr', class_='Table__TR'):
            cols = row.find_all('td')
            if len(cols) >= 2:
                name = cols[0].get_text(strip=True)
                status = cols[1].get_text(strip=True).lower()
                # 'out' 혹은 'suspension(징계)'이 포함되면 제외 명단에 추가
                if 'out' in status or 'suspension' in status or 'suspended' in status:
                    out_list.append(name)
    except: pass
    return out_list

def calculate_individual_uv(pie):
    return max(0.1, min(1.0 + (pie - 0.10) * 20, 3.5))

def get_momentum_bonus(wr, nrtg):
    """6:4 기세 보너스 산출 (Syntax Error 방지를 위해 if-elif 사용)"""
    # 승률 보너스 (60%)
    if wr >= 1.0: wr_b = 0.5
    elif wr >= 0.8: wr_b = 0.2
    elif wr >= 0.6: wr_b = 0.1
    elif wr >= 0.4: wr_b = 0.0
    elif wr >= 0.2: wr_b = -0.1
    else: wr_b = -0.2

    # NRTG 보너스 (40%)
    if nrtg >= 15: n_b = 0.5
    elif nrtg >= 6: n_b = 0.2
    elif nrtg >= 2: n_b = 0.1
    elif nrtg >= -2: n_b = 0.0
    elif nrtg >= -10: n_b = -0.1
    else: n_b = -0.2
    
    return (wr_b * 0.6) + (n_b * 0.4)

def run_final_scanner():
    # 미국 현지 경기 날짜 계산
    game_date = (datetime.now() - timedelta(hours=14)).strftime("%Y-%m-%d")
    print(f"📅 [WUV 2.0 스캔] 날짜: {game_date}")
    
    # 데이터 수집
    s_p = leaguedashplayerstats.LeagueDashPlayerStats(season=SEASON, measure_type_detailed_defense='Advanced', per_mode_detailed='PerGame').get_data_frames()[0]
    r_t = leaguedashteamstats.LeagueDashTeamStats(season=SEASON, last_n_games=10, measure_type_detailed_defense='Advanced').get_data_frames()[0]
    games = scoreboardv2.ScoreboardV2(game_date=game_date).game_header.get_data_frame()
    
    if games.empty:
        print("📭 오늘 경기가 없습니다."); return

    league_bases = []
    team_results = {}

    # 모든 팀 전력 사전 계산
    for abbr, t_info in TEAMS.items():
        t_id = int(t_info['id'])
        outs = get_out_players(t_info['slug'])
        
        roster = s_p[s_p['TEAM_ID'] == t_id].copy()
        roster = roster[(roster['GP'] >= 1) & (roster['MIN'] >= 10)]
        
        # 부상/징계 필터링
        roster['is_out'] = roster['PLAYER_NAME'].apply(lambda x: any(fuzz.partial_ratio(x.lower(), o.lower()) >= 85 for o in outs))
        available = roster[roster['is_out'] == False].copy()
        
        available['uv'] = available['PIE'].apply(calculate_individual_uv)
        available['cont'] = available['uv'] * available['MIN']
        
        t_min = available['MIN'].sum()
        t_cont = available['cont'].sum()
        if t_min < 240:
            t_cont += (0.5 * (240 - t_min))
            t_min = 240
        
        base = (t_cont / t_min) * 5
        
        t_row = r_t[r_t['TEAM_ID'] == t_id]
        wr, nrtg = (t_row.iloc[0]['W_PCT'], t_row.iloc[0]['NET_RATING']) if not t_row.empty else (0.5, 0.0)
        mom = get_momentum_bonus(wr, nrtg)
        
        team_results[abbr] = {'base': base, 'mom': mom, 'wr': wr}
        league_bases.append(base)

    avg_base = sum(league_bases) / len(league_bases)
    
    print("\n" + "="*85)
    print(f"{'HOME':<10} {'V2.0':<8} {'VS':<4} {'AWAY':<10} {'V2.0':<8} {'DIFF':<8} {'PRED'}")
    print("-" * 85)
    
    for _, g in games.iterrows():
        h_abbr = ID_TO_ABBR.get(str(g['HOME_TEAM_ID']))
        a_abbr = ID_TO_ABBR.get(str(g['VISITOR_TEAM_ID']))
        
        h, a = team_results[h_abbr], team_results[a_abbr]
        
        h_c = 0.15 if (h['base'] < avg_base and h['wr'] >= 0.5) else 0.0
        a_c = 0.15 if (a['base'] < avg_base and a['wr'] >= 0.5) else 0.0
        
        h_final = h['base'] + h['mom'] + h_c + 0.15 # 홈 어드밴티지
        a_final = a['base'] + a['mom'] + a_c
        
        diff = h_final - a_final
        pred = f"🎉 {h_abbr} 승" if diff > 0 else f"💀 {a_abbr} 승"
        print(f"{h_abbr:<10} {h_final:<8.3f} vs   {a_abbr:<10} {a_final:<8.3f} {abs(diff):<8.2f} {pred}")
    print("="*85)

if __name__ == "__main__":
    run_final_scanner()