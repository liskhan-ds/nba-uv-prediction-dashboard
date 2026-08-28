import sqlite3
import pandas as pd
import requests
import time
import sys
import config  # config.py 설정 불러오기
from bs4 import BeautifulSoup
from nba_api.stats.endpoints import leaguedashplayerstats, leaguedashteamstats, commonteamroster, scoreboardv2
from datetime import datetime, timedelta
from thefuzz import fuzz

# -----------------------------------------------------------------------------
# 1. 설정 및 상수
# -----------------------------------------------------------------------------
SEASON = '2025-26'
DB_PATH = "nba_data.db"
DASHBOARD_URL = "https://nba-uv-prediction.streamlit.app/"
COACH_BONUS_VAL = 0.15

TEAMS = {
    'ATL': {'id': '1610612737', 'slug': 'atl/atlanta-hawks'}, 'BOS': {'id': '1610612738', 'slug': 'bos/boston-celtics'},
    'BKN': {'id': '1610612751', 'slug': 'bkn/brooklyn-nets'}, 'CHA': {'id': '1610612766', 'slug': 'cha/charlotte-hornets'},
    'CHI': {'id': '1610612741', 'slug': 'chi/chicago-bulls'}, 'CLE': {'id': '1610612739', 'slug': 'cle/cleveland-cavaliers'},
    'DAL': {'id': '1610612742', 'slug': 'dal/dallas-mavericks'}, 'DEN': {'id': '1610612743', 'slug': 'den/denver-nuggets'},
    'DET': {'id': '1610612765', 'slug': 'det/detroit-stats'}, 'GSW': {'id': '1610612744', 'slug': 'gs/golden-state-warriors'},
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

ALL_PLAYER_STATS_CACHE = None

# -----------------------------------------------------------------------------
# 2. 로직 함수
# -----------------------------------------------------------------------------
def calculate_individual_uv(pie):
    uv = 1.0 + (pie - 0.10) * 20
    return max(0.1, min(uv, 3.5))

def get_momentum_bonus(wr, nrtg, is_reg_season=True):
    if not is_reg_season: return 0.0
    if wr >= 1.0: wr_b = 0.5
    elif wr >= 0.8: wr_b = 0.2
    elif wr >= 0.6: wr_b = 0.1
    elif wr >= 0.4: wr_b = 0.0
    elif wr >= 0.2: wr_b = -0.1
    else: wr_b = -0.2

    if nrtg >= 15: n_b = 0.5
    elif nrtg >= 6: n_b = 0.2
    elif nrtg >= 2: n_b = 0.1
    elif nrtg >= -2: n_b = 0.0
    elif nrtg >= -10: n_b = -0.1
    else: n_b = -0.2
    
    current_month = (datetime.now() - timedelta(hours=14)).month
    if current_month in [10, 11]:      w_weight, n_weight = 0.50, 0.75
    elif current_month in [12, 1, 2]:  w_weight, n_weight = 0.75, 1.00
    elif current_month in [3, 4]:      w_weight, n_weight = 1.00, 0.50
    else:                              w_weight, n_weight = 0.0, 0.0
    return (wr_b * w_weight) + (n_b * n_weight)

def select_best_lineup(roster):
    sorted_players = roster.sort_values(by='contribution', ascending=False)
    starters = []
    selected_indices = set()
    
    def pick_player(pool, count):
        picked = 0
        for idx, row in pool.iterrows():
            if picked >= count: break
            if idx not in selected_indices:
                starters.append(row)
                selected_indices.add(idx)
                picked += 1
    
    pick_player(sorted_players[sorted_players['pos'].str.contains('C', na=False)], 1)
    pick_player(sorted_players[sorted_players['pos'].str.contains('G', na=False)], 2)
    pick_player(sorted_players[sorted_players['pos'].str.contains('F', na=False)], 2)
    
    if len(starters) < 5:
        for idx, row in sorted_players.iterrows():
            if len(starters) >= 5: break
            if idx not in selected_indices:
                starters.append(row)
                selected_indices.add(idx)
    return pd.DataFrame(starters)

def calculate_team_power(df, team_metrics=None, is_home=False, is_reg_season=True):
    # [1] 로스터 확정 (Out 제외)
    roster = df[df['availability'] != 'Out'].copy()
    if roster.empty: return 0.0, "데이터 없음"
    for col in ['pie', 'min', 'usg_pct']: roster[col] = pd.to_numeric(roster[col])

    # [2] 개별 UV 및 기여도 계산
    roster['unit_value'] = roster['pie'].apply(calculate_individual_uv)
    roster['contribution'] = roster['unit_value'] * roster['min']
    
    total_minutes = roster['min'].sum()
    total_contribution = roster['contribution'].sum()
    if total_minutes < 240:
        total_contribution += (0.5 * (240 - total_minutes))
        total_minutes = 240
        
    # [3] 순수 팀 전력 점수 생성 (raw_score)
    base_score = (total_contribution / total_minutes) * 5
    
    # [4] 페널티 계산 및 적용 (오직 선수 데이터 기반)
    top_2_usg = roster.nlargest(2, 'usg_pct')['usg_pct'].sum()
    penalty = (top_2_usg - 0.60) * 3.0 if top_2_usg > 0.60 else 0.0
    
    # 최종 raw_score 확정 (선수 전력 + 페널티)
    raw_score = base_score - penalty

    # [5] 보너스 및 홈 이점 독립 연산 (변수 덮어쓰기 금지)
    m_bonus = get_momentum_bonus(team_metrics['wr'], team_metrics['nrtg'], is_reg_season) if team_metrics else 0.0
    c_bonus = COACH_BONUS_VAL if (is_reg_season and team_metrics and raw_score < 5.0 and team_metrics['wr'] >= 0.6) else 0.0
    home_adv = 0.15 if is_home else 0.0
    
    # [6] 최종 점수 합산 (1 + 2 + 3 + 4 원칙)
    final_score = raw_score + m_bonus + c_bonus + home_adv

    # 로그 구성
    home_adv_str = " + 홈이점(0.15)" if is_home else ""
    penalty_str = f" - 패널티({penalty:.2f})" if penalty > 0 else ""
    starters_df = select_best_lineup(roster)
    detail_str = " / ".join([f"{r['player_name']}({r['unit_value']:.1f})" for _, r in starters_df.iterrows()])
    full_log = f"[{final_score:.2f}] = 베스트5[{detail_str}]{home_adv_str}{penalty_str}"
    
    return final_score, full_log

def get_team_stats_df(team_abbr):
    global ALL_PLAYER_STATS_CACHE
    print(f"   Using Logic -> {team_abbr} 데이터 수집 중...", end=" ", flush=True)
    t_info = TEAMS.get(team_abbr)
    
    try:
        if ALL_PLAYER_STATS_CACHE is None:
            ALL_PLAYER_STATS_CACHE = leaguedashplayerstats.LeagueDashPlayerStats(
                season=SEASON, 
                team_id_nullable=0, 
                measure_type_detailed_defense='Advanced', 
                per_mode_detailed='PerGame', 
                timeout=60
            ).get_data_frames()[0]

        roster_api = commonteamroster.CommonTeamRoster(season=SEASON, team_id=t_info['id'], timeout=60).get_data_frames()[0]
        current_player_names = roster_api['PLAYER'].tolist()
        df = ALL_PLAYER_STATS_CACHE[ALL_PLAYER_STATS_CACHE['PLAYER_NAME'].isin(current_player_names)].copy()
        df = df[(df['GP'] >= 1) & (df['MIN'] >= 10)].copy()

        df = pd.merge(df, roster_api[['PLAYER', 'POSITION']], left_on='PLAYER_NAME', right_on='PLAYER', how='left')
        df = df[['PLAYER_NAME', 'MIN', 'PIE', 'USG_PCT', 'POSITION']].copy()
        df.columns = ['player_name', 'min', 'pie', 'usg_pct', 'pos']
        df['pos'] = df['pos'].fillna('F')
        
        out_players = []
        res = requests.get(f"https://www.espn.com/nba/team/injuries/_/name/{t_info['slug']}", headers={'User-Agent': 'Mozilla/5.0'}, timeout=5)
        soup = BeautifulSoup(res.text, 'html.parser')
        for tag in soup.find_all('span', class_='Athlete__PlayerName'):
            name = tag.text.strip()
            status_text = tag.parent.parent.get_text(" ", strip=True).lower()
            if "out" in status_text or "suspension" in status_text or "suspended" in status_text: 
                out_players.append(name)
        
        df['availability'] = 'OK'
        for idx, row in df.iterrows():
            if any(fuzz.partial_ratio(row['player_name'].lower(), o.lower()) >= 80 for o in out_players):
                df.at[idx, 'availability'] = 'Out'
        
        print("✅ 완료")
        return df, out_players
    except Exception as e:
        print(f"❌ 실패 ({e})")
        return None, []

def send_to_slack(text):
    try:
        token, c_id = config.SLACK_BOT_TOKEN, (config.SLACK_REAL_CHANNEL_ID if config.MODE == "REAL" else config.SLACK_TEST_CHANNEL_ID)
        requests.post("https://slack.com/api/chat.postMessage", headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"}, json={"channel": c_id, "text": ("" if config.MODE == "REAL" else "🛠 [테스트] ") + text})
    except: pass

def main():
    if len(sys.argv) > 1:
        target_date = sys.argv[1]
    else:
        target_date = (datetime.now() - timedelta(hours=14)).strftime("%Y-%m-%d")

    print(f"🗓️ 예측 대상 날짜: {target_date}")
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM predictions WHERE date = ?", (target_date,))
    conn.commit()

    try:
        r_t = leaguedashteamstats.LeagueDashTeamStats(season=SEASON, last_n_games=10, measure_type_detailed_defense='Advanced').get_data_frames()[0]
        board = scoreboardv2.ScoreboardV2(game_date=target_date, timeout=60).game_header.get_data_frame()
    except Exception as e:
        print(f"❌ Scoreboard / TeamStats 수집 실패: {e}")
        return
    if board.empty:
        print(f"⚠️ {target_date} 에 진행된 경기 일정이 없습니다.")
        return

    slack_msg = f"🏀 *NBA AI 승부예측 리포트* ({target_date} US)\n================================\n"
    processed_games = set()

    for _, row in board.iterrows():
        g_id = row['GAME_ID']
        if g_id in processed_games: continue
        processed_games.add(g_id)
        
        is_reg_season = g_id.startswith('002')
        season_type_str = "정규시즌" if is_reg_season else "플레이오프"
        
        h_id, v_id = str(row['HOME_TEAM_ID']), str(row['VISITOR_TEAM_ID'])
        h_team, v_team = ID_TO_ABBR.get(h_id, 'Unknown'), ID_TO_ABBR.get(v_id, 'Unknown')
        if h_team == 'Unknown' or v_team == 'Unknown': continue

        def get_m(t_id):
            r = r_t[r_t['TEAM_ID'] == int(t_id)]
            return {'wr': r.iloc[0]['W_PCT'], 'nrtg': r.iloc[0]['NET_RATING']} if not r.empty else {'wr': 0.5, 'nrtg': 0.0}

        h_res, h_out = get_team_stats_df(h_team)
        v_res, v_out = get_team_stats_df(v_team)
        if h_res is None or v_res is None: continue
            
        h_score, h_log = calculate_team_power(h_res, team_metrics=get_m(h_id), is_home=True, is_reg_season=is_reg_season)
        v_score, v_log = calculate_team_power(v_res, team_metrics=get_m(v_id), is_home=False, is_reg_season=is_reg_season)

        gap = abs(h_score - v_score)
        predicted_winner = h_team if h_score > v_score else v_team
        
        slack_msg += f"\n[{v_team}] vs [{h_team}] ({season_type_str})\n"
        slack_msg += f"UV: {'*' if v_score > h_score else ''}{v_score:.2f}{'*' if v_score > h_score else ''} "
        slack_msg += f"{'>' if v_score > h_score else '<'} {'*' if h_score > v_score else ''}{h_score:.2f}{'*' if h_score > v_score else ''}\n"
        
        icon = "💪" if gap >= 1.0 else "👉"
        slack_msg += f"{icon} [{predicted_winner}] 우세 (`+{gap:.2f}`)\n"
        
        if h_out or v_out:
            slack_msg += "🚑 주요 결장:\n"
            if h_out: slack_msg += f"   {h_team}: {', '.join(h_out)}\n"
            if v_out: slack_msg += f"   {v_team}: {', '.join(v_out)}\n"
        slack_msg += "--------------------------------\n"

        cursor.execute("INSERT INTO predictions (date, home_team, visit_team, predicted_winner, predicted_gap) VALUES (?, ?, ?, ?, ?)", (target_date, h_team, v_team, predicted_winner, gap))
        conn.commit()

    conn.close()
    print("\n" + slack_msg)
    print(f"※ DB 적재 완료 ({target_date} 대상 predictions 테이블)")
    send_to_slack(slack_msg + f"※ 상세 데이터는 대시보드를 확인하세요.\n👉 {DASHBOARD_URL}")

if __name__ == "__main__": main()