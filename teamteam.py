import pandas as pd
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
from nba_api.stats.endpoints import leaguedashplayerstats, leaguedashteamstats, commonteamroster
from thefuzz import fuzz

# --- [1. 기본 설정 및 상수] ---
SEASON = '2025-26' 
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

# [run_nba 연동] 전역 캐시 변수 추가
ALL_PLAYER_STATS_CACHE = None

# --- [2. 핵심 로직 함수] ---
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
    starters, selected_indices = [], set()
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

# --- [3. 분석 실행 함수] ---
def main():
    global ALL_PLAYER_STATS_CACHE
    while True: 
        print("\n" + "="*75)
        target = input(" 상세 분석할 팀 약어 (Q 종료): ").upper()
        if target == 'Q':
            print(" 프로그램을 종료합니다.")
            break
        
        t_info = TEAMS.get(target)
        if not t_info:
            print(f" '{target}'은(는) 존재하지 않는 팀 약어입니다. 다시 입력해주세요.")
            continue

        print(f" {target} 로스터 및 TOT 스탯 데이터 수집 중...")
        try:
            # [로직 6 & run_nba TOT 방식 적용]
            if ALL_PLAYER_STATS_CACHE is None:
                ALL_PLAYER_STATS_CACHE = leaguedashplayerstats.LeagueDashPlayerStats(
                    season=SEASON, team_id_nullable=0, measure_type_detailed_defense='Advanced', 
                    per_mode_detailed='PerGame', timeout=60
                ).get_data_frames()[0]

            roster_df = commonteamroster.CommonTeamRoster(season=SEASON, team_id=t_info['id'], timeout=60).get_data_frames()[0]
            current_player_names = roster_df['PLAYER'].tolist()
            
            # 명단 필터링 및 최소 출전 조건 (GP >= 1 / MIN >= 10) 적용
            df = ALL_PLAYER_STATS_CACHE[ALL_PLAYER_STATS_CACHE['PLAYER_NAME'].isin(current_player_names)].copy()
            df = df[(df['GP'] >= 1) & (df['MIN'] >= 10)].copy()
            
            df = pd.merge(df, roster_df[['PLAYER', 'POSITION']], left_on='PLAYER_NAME', right_on='PLAYER', how='left')
            df = df[['PLAYER_NAME', 'MIN', 'PIE', 'USG_PCT', 'POSITION']].copy()
            df.columns = ['player_name', 'min', 'pie', 'usg_pct', 'pos']
            df['pos'] = df['pos'].fillna('F')
            
            # ESPN 부상자 로직 (run_nba와 일치)
            out_players = []
            res = requests.get(f"https://www.espn.com/nba/team/injuries/_/name/{t_info['slug']}", headers={'User-Agent': 'Mozilla/5.0'}, timeout=5)
            soup = BeautifulSoup(res.text, 'html.parser')
            for tag in soup.find_all('span', class_='Athlete__PlayerName'):
                name = tag.text.strip()
                status_text = tag.parent.parent.get_text(" ", strip=True).lower()
                if any(x in status_text for x in ["out", "suspension", "suspended"]): 
                    out_players.append(name)
            
            df['availability'] = 'OK'
            for idx, row in df.iterrows():
                if any(fuzz.partial_ratio(row['player_name'].lower(), o.lower()) >= 80 for o in out_players):
                    df.at[idx, 'availability'] = 'Out'

            print("  완료")

            # [run_nba.rtf 5단계 연산 로직 이식]
            roster = df[df['availability'] != 'Out'].copy()
            for col in ['pie', 'min', 'usg_pct']: roster[col] = pd.to_numeric(roster[col])
            roster['unit_value'] = roster['pie'].apply(calculate_individual_uv)
            roster['contribution'] = roster['unit_value'] * roster['min']
            
            total_minutes = roster['min'].sum()
            total_contribution = roster['contribution'].sum()
            if total_minutes < 240:
                total_contribution += (0.5 * (240 - total_minutes))
                total_minutes = 240
            
            # 1. 선수 로스터 기반 base_score
            base_score = (total_contribution / total_minutes) * 5
            
            # 2. 페널티 계산
            top_2_usg = roster.nlargest(2, 'usg_pct')['usg_pct'].sum()
            penalty = (top_2_usg - 0.60) * 3.0 if top_2_usg > 0.60 else 0.0
            
            # 3. 순수 팀 전력 (raw_score) 확정
            raw_score = base_score - penalty
            
            # 4. 보너스 연산
            team_stats = leaguedashteamstats.LeagueDashTeamStats(season=SEASON, last_n_games=10, measure_type_detailed_defense='Advanced').get_data_frames()[0]
            t_row = team_stats[team_stats['TEAM_ID'] == int(t_info['id'])]
            wr, nrtg = (t_row.iloc[0]['W_PCT'], t_row.iloc[0]['NET_RATING']) if not t_row.empty else (0.5, 0.0)
            
            is_reg_season = True 
            m_bonus = get_momentum_bonus(wr, nrtg, is_reg_season)
            c_bonus = COACH_BONUS_VAL if (is_reg_season and raw_score < 5.0 and wr >= 0.6) else 0.0
            
            # 5. 최종 합산 (상세 분석은 홈 이점 제외 1+2+3 원칙)
            final_uv = raw_score + m_bonus + c_bonus

            starters = select_best_lineup(roster)
            print(f"\n [{target}] UV 상세 분석 (기준: 5.0 / L10 승률 0.6)")
            print("-" * 75)
            for _, p in roster.sort_values(by='contribution', ascending=False).iterrows():
                is_starter = "★" if p['player_name'] in starters['player_name'].values else "  "
                print(f"{is_starter} {p['player_name']:<22} | UV: {p['unit_value']:.2f} | MIN: {p['min']:.1f} | USG: {p['usg_pct']:.2f}")
            
            print("-" * 75)
            print(f" > Raw Score: {raw_score:.3f} (Penalty 포함)")
            print(f" > 보너스: 기세({m_bonus:+.3f}), 감독({c_bonus:+.3f})")
            print(f" > 패널티: {penalty:.3f}")
            print(f" >> 최종 UV: {final_uv:.3f} (홈이점 미적용 수치)")
            if out_players: print(f"  주요 결장: {', '.join(out_players)}")
            
        except Exception as e:
            print(f"  분석 중 오류 발생: {e}")

if __name__ == "__main__":
    main()