import pandas as pd
from nba_api.stats.endpoints import leaguedashplayerstats, leaguedashteamstats

# --- [TEAM_ID 딕셔너리] ---
TEAMS = {
    'ATL': {'id': '1610612737'}, 'BOS': {'id': '1610612738'}, 'BKN': {'id': '1610612751'},
    'CHA': {'id': '1610612766'}, 'CHI': {'id': '1610612741'}, 'CLE': {'id': '1610612739'},
    'DAL': {'id': '1610612742'}, 'DEN': {'id': '1610612743'}, 'DET': {'id': '1610612765'},
    'GSW': {'id': '1610612744'}, 'HOU': {'id': '1610612745'}, 'IND': {'id': '1610612754'},
    'LAC': {'id': '1610612746'}, 'LAL': {'id': '1610612747'}, 'MEM': {'id': '1610612763'},
    'MIA': {'id': '1610612748'}, 'MIL': {'id': '1610612749'}, 'MIN': {'id': '1610612750'},
    'NOP': {'id': '1610612740'}, 'NYK': {'id': '1610612752'}, 'OKC': {'id': '1610612760'},
    'ORL': {'id': '1610612753'}, 'PHI': {'id': '1610612755'}, 'PHX': {'id': '1610612756'},
    'POR': {'id': '1610612757'}, 'SAC': {'id': '1610612758'}, 'SAS': {'id': '1610612759'},
    'TOR': {'id': '1610612761'}, 'UTA': {'id': '1610612762'}, 'WAS': {'id': '1610612764'}
}

SEASON = '2025-26'
COACH_BONUS_VAL = 0.15

# 1. 웅쓰의 오리지널 V1 개인 UV 계산기
def calculate_individual_uv_v1(pie):
    uv = 1.0 + (pie - 0.10) * 20
    return max(0.1, min(uv, 3.5))

# 2. 최근 10경기 승률 가중치 (60% 비중용)
def get_wr_bonus_raw(wr):
    if wr >= 1.0: return 0.50
    if wr >= 0.8: return 0.20
    if wr >= 0.6: return 0.10
    if wr >= 0.4: return 0.00
    if wr >= 0.2: return -0.10
    return -0.20

# 3. 최근 10경기 NRTG 가중치 (40% 비중용)
def get_nrtg_bonus_raw(nrtg):
    if nrtg >= 15: return 0.50
    if nrtg >= 6: return 0.20
    if nrtg >= 2: return 0.10
    if nrtg >= -2: return 0.00
    if nrtg >= -10: return -0.10
    return -0.20

def run_wuv_v2_5_final():
    print(f"🏀 [WUV V2.5] V1 베이스 유지 + 신규 보너스 로직 산출 중...")
    
    # [데이터 수집] 시즌 전체(BASE용) + 최근 10G(보너스용)
    stats = leaguedashplayerstats.LeagueDashPlayerStats(season=SEASON, measure_type_detailed_defense='Advanced', per_mode_detailed='PerGame').get_data_frames()[0]
    r_t = leaguedashteamstats.LeagueDashTeamStats(season=SEASON, last_n_games=10, measure_type_detailed_defense='Advanced').get_data_frames()[0]
    
    # V1 기준 필터링 (트레이드 선수 반영: GP >= 1)
    df = stats[(stats['GP'] >= 1) & (stats['MIN'] >= 10)].copy()
    df['unit_value'] = df['PIE'].apply(calculate_individual_uv_v1)
    df['contribution'] = df['unit_value'] * df['MIN']
    
    # 리그 평균 (감독 보너스 판단용)
    temp_team_scores = []

    # [BASE 계산 - 웅쓰 V1 로직 그대로]
    team_base_map = {}
    for team_abbr in df['TEAM_ABBREVIATION'].unique():
        roster = df[df['TEAM_ABBREVIATION'] == team_abbr].copy()
        total_minutes = roster['MIN'].sum()
        total_contribution = roster['contribution'].sum()
        
        if total_minutes < 240:
            missing = 240 - total_minutes
            total_contribution += (0.5 * missing)
            total_minutes = 240
            
        base_score = (total_contribution / total_minutes) * 5
        team_base_map[team_abbr] = base_score

    league_avg = sum(team_base_map.values()) / len(team_base_map)
    print(f"💡 리그 평균 UV: {league_avg:.3f}")

    # [보너스 적용 및 최종 산출]
    final_results = []
    for team_abbr, base in team_base_map.items():
        target_id = int(TEAMS.get(team_abbr, {}).get('id', 0))
        t_row = r_t[r_t['TEAM_ID'] == target_id]
        
        wr = t_row.iloc[0]['W_PCT'] if not t_row.empty else 0.5
        nrtg = t_row.iloc[0]['NET_RATING'] if not t_row.empty else 0.0
        
        # 보너스 1: 최근 10경기 기세 (6:4 결합)
        adj_bonus = (get_wr_bonus_raw(wr) * 0.6) + (get_nrtg_bonus_raw(nrtg) * 0.4)
        
        # 보너스 2: 감독 역량 (시즌 체급 < 평균인데 최근 승률 50% 이상)
        coach_b = COACH_BONUS_VAL if (base < league_avg and wr >= 0.5) else 0.0
        
        v2_total = base + adj_bonus + coach_b
        
        final_results.append({
            'TEAM': team_abbr,
            'V2_TOTAL': round(v2_total, 3),
            'BASE': round(base, 3),
            'ADJ_BONUS': round(adj_bonus, 3),
            'COACH': 'O' if coach_b > 0 else 'X'
        })

    # 결과 정렬 및 출력
    result_df = pd.DataFrame(final_results).sort_values(by='V2_TOTAL', ascending=False)
    
    print("\n" + "="*75)
    print(f"📊 NBA 30개 팀 V2.5 최종 리포트 (V1 베이스 + 2종 보너스)")
    print("="*75)
    print(result_df[['TEAM', 'V2_TOTAL', 'BASE', 'ADJ_BONUS', 'COACH']].to_string(index=False))
    print("="*75)
    
    result_df.to_csv('nba_30_teams_v2_5_final.csv', index=False, encoding='utf-8-sig')

if __name__ == "__main__":
    run_wuv_v2_5_final()