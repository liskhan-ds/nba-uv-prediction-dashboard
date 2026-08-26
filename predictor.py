import pandas as pd
import requests
import sqlite3
import os
from bs4 import BeautifulSoup
from nba_api.stats.endpoints import leaguedashplayerstats, leaguedashteamstats, commonteamroster, scoreboardv2
from datetime import datetime, timedelta
from thefuzz import fuzz

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "nba_data.db")
SEASON = '2025-26'
LAKERS_ID = '1610612747'
COACH_BONUS_VAL = 0.15

# --- [팀 정보 딕셔너리] ---
TEAMS = {
    'ATL': {'id': '1610612737', 'slug': 'atl/atlanta-hawks'},
    'BOS': {'id': '1610612738', 'slug': 'bos/boston-celtics'},
    'BKN': {'id': '1610612751', 'slug': 'bkn/brooklyn-nets'},
    'CHA': {'id': '1610612766', 'slug': 'cha/charlotte-hornets'},
    'CHI': {'id': '1610612741', 'slug': 'chi/chicago-bulls'},
    'CLE': {'id': '1610612739', 'slug': 'cle/cleveland-cavaliers'},
    'DAL': {'id': '1610612742', 'slug': 'dal/dallas-mavericks'},
    'DEN': {'id': '1610612743', 'slug': 'den/denver-nuggets'},
    'DET': {'id': '1610612765', 'slug': 'det/detroit-pistons'},
    'GSW': {'id': '1610612744', 'slug': 'gs/golden-state-warriors'},
    'HOU': {'id': '1610612745', 'slug': 'hou/houston-rockets'},
    'IND': {'id': '1610612754', 'slug': 'ind/indiana- Bloomers'}, # 가끔 명칭 오타 방지용
    'LAC': {'id': '1610612746', 'slug': 'lac/los-angeles-clippers'},
    'LAL': {'id': '1610612747', 'slug': 'lal/los-angeles-lakers'},
    'MEM': {'id': '1610612763', 'slug': 'mem/memphis-grizzlies'},
    'MIA': {'id': '1610612748', 'slug': 'mia/miami-heat'},
    'MIL': {'id': '1610612749', 'slug': 'mil/milwaukee-bucks'},
    'MIN': {'id': '1610612750', 'slug': 'min/minnesota-timberwolves'},
    'NOP': {'id': '1610612740', 'slug': 'no/new-orleans-pelicans'},
    'NYK': {'id': '1610612752', 'slug': 'ny/new-york-knicks'},
    'OKC': {'id': '1610612760', 'slug': 'okc/oklahoma-city-thunder'},
    'ORL': {'id': '1610612753', 'slug': 'orl/orlando-magic'},
    'PHI': {'id': '1610612755', 'slug': 'phi/philadelphia-76ers'},
    'PHX': {'id': '1610612756', 'slug': 'phx/phoenix-suns'},
    'POR': {'id': '1610612757', 'slug': 'por/portland-trail-blazers'},
    'SAC': {'id': '1610612758', 'slug': 'sac/sacramento-kings'},
    'SAS': {'id': '1610612759', 'slug': 'sa/san-antonio-spurs'},
    'TOR': {'id': '1610612761', 'slug': 'tor/toronto-raptors'},
    'UTA': {'id': '1610612762', 'slug': 'utah/utah-jazz'},
    'WAS': {'id': '1610612764', 'slug': 'wsh/washington-wizards'},
}
ID_TO_ABBR = {v['id']: k for k, v in TEAMS.items()}

# --- [보너스 가중치 계산기] ---
def get_wr_bonus(wr):
    if wr >= 1.0: return 0.50
    if wr >= 0.8: return 0.20
    if wr >= 0.6: return 0.10
    if wr >= 0.4: return 0.00
    if wr >= 0.2: return -0.10
    return -0.20

def get_nrtg_bonus(nrtg):
    if nrtg >= 15: return 0.50
    if nrtg >= 6: return 0.20
    if nrtg >= 2: return 0.10
    if nrtg >= -2: return 0.00
    if nrtg >= -10: return -0.10
    return -0.20

def calculate_individual_uv(pie):
    uv = 1.0 + (pie - 0.10) * 20
    return max(0.1, min(uv, 3.5))

def select_best_lineup(roster):
    # (웅쓰 기존 로직 유지: G-G-F-F-C 밸런스 선발)
    sorted_players = roster.sort_values(by='contribution', ascending=False)
    starters, selected_indices = [], set()
    guards = sorted_players[sorted_players['pos'].str.contains('G', na=False)]
    forwards = sorted_players[sorted_players['pos'].str.contains('F', na=False)]
    centers = sorted_players[sorted_players['pos'].str.contains('C', na=False)]
    
    def pick(pool, count):
        p_count = 0
        for idx, row in pool.iterrows():
            if p_count >= count: break
            if idx not in selected_indices:
                starters.append(row)
                selected_indices.add(idx)
                p_count += 1
    pick(centers, 1); pick(guards, 2); pick(forwards, 2)
    
    if len(starters) < 5:
        for idx, row in sorted_players.iterrows():
            if len(starters) >= 5: break
            if idx not in selected_indices:
                starters.append(row)
                selected_indices.add(idx)
    return pd.DataFrame(starters)

# --- [팀 전력 통합 산출 함수] ---
def calculate_team_power_v2(df, team_abbr, is_home=False, league_avg=5.0):
    roster = df[df['availability'] != 'Out'].copy()
    if roster.empty: return 0.0, 0.0, 0.0, "데이터 없음"

    # 1. BASE 점수 계산 (V1 로직 유지)
    roster['unit_value'] = roster['pie'].apply(calculate_individual_uv)
    roster['contribution'] = roster['unit_value'] * roster['min']
    
    total_min = roster['min'].sum()
    total_cont = roster['contribution'].sum()
    
    if total_min < 240:
        total_cont += (0.5 * (240 - total_min))
        total_min = 240
        
    base_score = (total_cont / total_min) * 5
    
    # 2. 최근 10경기 기세 보너스 (6:4 비중)
    # API에서 해당 팀의 최근 10G 스탯 호출
    try:
        r_t = leaguedashteamstats.LeagueDashTeamStats(
            season=SEASON, last_n_games=10, measure_type_detailed_defense='Advanced'
        ).get_data_frames()[0]
        team_id = int(TEAMS[team_abbr]['id'])
        t_row = r_t[r_t['TEAM_ID'] == team_id].iloc[0]
        wr, nrtg = t_row['W_PCT'], t_row['NET_RATING']
    except:
        wr, nrtg = 0.5, 0.0
        
    adj_bonus = (get_wr_bonus(wr) * 0.6) + (get_nrtg_bonus(nrtg) * 0.4)
    
    # 3. 감독 보너스
    coach_b = COACH_BONUS_VAL if (base_score < league_avg and wr >= 0.5) else 0.0
    
    # 4. 홈 이점 및 USG 패널티
    home_adv = 0.15 if is_home else 0.0
    top_2_usg = roster.nlargest(2, 'usg_pct')['usg_pct'].sum()
    penalty = max(0, (top_2_usg - 0.60) * 3.0) if top_2_usg > 0.60 else 0.0

    final_total = base_score + adj_bonus + coach_b + home_adv - penalty

    # 라인업 정보 생성
    starters = select_best_lineup(roster)
    detail = " + ".join([f"{r['player_name']}({r['unit_value']:.1f})" for _, r in starters.iterrows()])
    if coach_b > 0: detail += " + 명장보너스(+0.15)"
    if home_adv > 0: detail += " + 홈이점(+0.15)"
    
    return final_total, base_score, adj_bonus, detail

# --- [상대 팀 데이터 및 부상자 수집] ---
def get_opponent_data_v2(abbr):
    team_info = TEAMS.get(abbr)
    if not team_info: return None
    print(f"\n🔄 [{abbr}] 시즌 데이터 및 부상자 정보 수집 중...")
    
    try:
        # BASE 점수용 시즌 데이터 (100%)
        stats = leaguedashplayerstats.LeagueDashPlayerStats(
            season=SEASON, team_id_nullable=team_info['id'], 
            measure_type_detailed_defense='Advanced', per_mode_detailed='PerGame'
        ).get_data_frames()[0]
        stats = stats[(stats['GP'] >= 1) & (stats['MIN'] >= 10)].copy()
        
        roster_api = commonteamroster.CommonTeamRoster(season=SEASON, team_id=team_info['id']).get_data_frames()[0]
        df = pd.merge(stats, roster_api[['PLAYER', 'POSITION']], left_on='PLAYER_NAME', right_on='PLAYER', how='left')
        df = df[['PLAYER_NAME', 'MIN', 'PIE', 'USG_PCT', 'POSITION']].copy()
        df.columns = ['player_name', 'min', 'pie', 'usg_pct', 'pos']
        df['pos'] = df['pos'].fillna('F')
        
        # ESPN 부상자 크롤링 (Fuzzy Matching 적용)
        injury_url = f"https://www.espn.com/nba/team/injuries/_/name/{team_info['slug']}"
        out_players = []
        res = requests.get(injury_url, headers={'User-Agent': 'Mozilla/5.0'})
        soup = BeautifulSoup(res.text, 'html.parser')
        for tag in soup.find_all('span', class_='Athlete__PlayerName'):
            if "out" in tag.parent.parent.get_text().lower():
                out_players.append(tag.text.strip())
        
        df['availability'] = 'OK'
        for idx, row in df.iterrows():
            for out_n in out_players:
                if fuzz.partial_ratio(out_n.lower(), row['player_name'].lower()) >= 85:
                    df.at[idx, 'availability'] = 'Out'
                    
        return df, out_players
    except Exception as e:
        print(f"❌ 에러: {e}"); return None

# --- [KST 날짜 감지] ---
def detect_todays_game_kst():
    us_game_date = (datetime.now() - timedelta(hours=14)).strftime("%Y-%m-%d")
    try:
        games = scoreboardv2.ScoreboardV2(game_date=us_game_date).game_header.get_data_frame()
        lal_game = games[(games['HOME_TEAM_ID'] == int(LAKERS_ID)) | (games['VISITOR_TEAM_ID'] == int(LAKERS_ID))]
        if lal_game.empty: return None, None
        row = lal_game.iloc[0]
        is_home = int(row['HOME_TEAM_ID']) == int(LAKERS_ID)
        opp_id = str(row['VISITOR_TEAM_ID'] if is_home else row['HOME_TEAM_ID'])
        return is_home, ID_TO_ABBR.get(opp_id)
    except: return None, None

# --- [메인 실행부] ---
def main():
    print("=== [WUV V2.5] NBA 승부 예측기 (시즌 BASE + 6:4 기세) ===")
    
    # 리그 평균 UV 미리 계산 (감독 보너스용)
    all_stats = leaguedashplayerstats.LeagueDashPlayerStats(season=SEASON, measure_type_detailed_defense='Advanced').get_data_frames()[0]
    all_stats['uv'] = all_stats['PIE'].apply(calculate_individual_uv)
    league_avg = ( (all_stats['uv'] * all_stats['MIN']).sum() / all_stats['MIN'].sum() ) * 5

    detected_home, detected_opp = detect_todays_game_kst()
    lal_is_home, target_opp = (detected_home, detected_opp) if detected_opp else (False, None)
    
    if target_opp:
        print(f"🚀 [자동감지] 오늘 LAL vs {target_opp} ({'홈' if lal_is_home else '원정'})")
    else:
        print("\n📭 일정 없음 -> 수동 모드"); lal_is_home = input("🏟️  LAL 홈? (Y/N): ").upper() == 'Y'

    conn = sqlite3.connect(DB_PATH)
    lakers_df = pd.read_sql(f"SELECT * FROM daily_stats WHERE date = '{datetime.now().strftime('%Y-%m-%d')}'", conn)
    conn.close()

    while True:
        opp_abbr = target_opp if target_opp else input("\n🥊 상대 팀 약어 (종료 Q): ").upper()
        if opp_abbr == 'Q' or not opp_abbr: break
        
        opp_data = get_opponent_data_v2(opp_abbr)
        if not opp_data: continue
        opp_df, opp_out = opp_data
        
        l_total, l_base, l_bonus, l_detail = calculate_team_power_v2(lakers_df, 'LAL', lal_is_home, league_avg)
        o_total, o_base, o_bonus, o_detail = calculate_team_power_v2(opp_df, opp_abbr, not lal_is_home, league_avg)

        print("\n" + "="*70)
        print(f"⚔️  MATCHUP: LAL(BASE {l_base:.2f}) vs {opp_abbr}(BASE {o_base:.2f})")
        print("="*70)
        print(f"🟣 LAL 최종: {l_total:.3f} (기세: {l_bonus:+.2f}) | {l_detail}")
        print(f"⚪ {opp_abbr} 최종: {o_total:.3f} (기세: {o_bonus:+.2f}) | {o_detail}")
        print("-" * 70)
        
        diff = l_total - o_total
        print(f"🔮 결과: {'🎉 LAL 승리 예상' if diff > 0 else f'💀 {opp_abbr} 우세'} (격차: {abs(diff):.2f})")
        if target_opp: break

if __name__ == "__main__":
    main()