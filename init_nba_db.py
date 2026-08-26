import sqlite3
import pandas as pd
import time
import sys
from datetime import datetime
from nba_api.stats.endpoints import commonteamroster, leaguedashplayerstats

DB_NAME = "nba_uv_2026_27.db"
ROSTER_SEASON = "2026-27"
STATS_SEASON = "2025-26"

TEAMS = {
    'ATL': {'id': '1610612737', 'name': 'Atlanta Hawks'},
    'BOS': {'id': '1610612738', 'name': 'Boston Celtics'},
    'BKN': {'id': '1610612751', 'name': 'Brooklyn Nets'},
    'CHA': {'id': '1610612766', 'name': 'Charlotte Hornets'},
    'CHI': {'id': '1610612741', 'name': 'Chicago Bulls'},
    'CLE': {'id': '1610612739', 'name': 'Cleveland Cavaliers'},
    'DAL': {'id': '1610612742', 'name': 'Dallas Mavericks'},
    'DEN': {'id': '1610612743', 'name': 'Denver Nuggets'},
    'DET': {'id': '1610612765', 'name': 'Detroit Pistons'},
    'GSW': {'id': '1610612744', 'name': 'Golden State Warriors'},
    'HOU': {'id': '1610612745', 'name': 'Houston Rockets'},
    'IND': {'id': '1610612754', 'name': 'Indiana Pacers'},
    'LAC': {'id': '1610612746', 'name': 'Los Angeles Clippers'},
    'LAL': {'id': '1610612747', 'name': 'Los Angeles Lakers'},
    'MEM': {'id': '1610612763', 'name': 'Memphis Grizzlies'},
    'MIA': {'id': '1610612748', 'name': 'Miami Heat'},
    'MIL': {'id': '1610612749', 'name': 'Milwaukee Bucks'},
    'MIN': {'id': '1610612750', 'name': 'Minnesota Timberwolves'},
    'NOP': {'id': '1610612740', 'name': 'New Orleans Pelicans'},
    'NYK': {'id': '1610612752', 'name': 'New York Knicks'},
    'OKC': {'id': '1610612760', 'name': 'Oklahoma City Thunder'},
    'ORL': {'id': '1610612753', 'name': 'Orlando Magic'},
    'PHI': {'id': '1610612755', 'name': 'Philadelphia 76ers'},
    'PHX': {'id': '1610612756', 'name': 'Phoenix Suns'},
    'POR': {'id': '1610612757', 'name': 'Portland Trail Blazers'},
    'SAC': {'id': '1610612758', 'name': 'Sacramento Kings'},
    'SAS': {'id': '1610612759', 'name': 'San Antonio Spurs'},
    'TOR': {'id': '1610612761', 'name': 'Toronto Raptors'},
    'UTA': {'id': '1610612762', 'name': 'Utah Jazz'},
    'WAS': {'id': '1610612764', 'name': 'Washington Wizards'}
}

# 선수 개별 UV 산출 공식 (0.1 ~ 3.5 범위)
def calculate_individual_uv(pie):
    uv = 1.0 + (pie - 0.10) * 20
    return max(0.1, min(uv, 3.5))

def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("DROP TABLE IF EXISTS teams_uv")
    cursor.execute("DROP TABLE IF EXISTS players_uv")
    
    cursor.execute('''
    CREATE TABLE teams_uv (
        team_abbr TEXT PRIMARY KEY,
        team_name TEXT,
        top2_usg REAL,
        usg_penalty REAL,
        starters_uv_sum REAL,
        starters_adj_uv_sum REAL,
        starters_contrib REAL,
        rotation_uv_avg REAL,
        rotation_contrib REAL,
        bench_uv_avg REAL,
        bench_contrib REAL,
        final_team_uv REAL,
        updated_at TEXT
    )
    ''')
    
    cursor.execute('''
    CREATE TABLE players_uv (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        team_abbr TEXT,
        player_name TEXT,
        position TEXT,
        min_per_game REAL,
        pts REAL,
        reb REAL,
        ast REAL,
        pie REAL,
        usg_pct REAL,
        individual_uv REAL,
        role_group TEXT,
        min_rank INTEGER,
        FOREIGN KEY (team_abbr) REFERENCES teams_uv(team_abbr)
    )
    ''')
    conn.commit()
    conn.close()
    print("📁 SQLite 데이터베이스 테이블 초기화 완료: nba_uv_2026_27.db")

def main():
    init_db()
    
    print("\n📡 리그 전체 선수 스탯 데이터 수집 중 (NBA Stats API)...", flush=True)
    try:
        stats_adv = leaguedashplayerstats.LeagueDashPlayerStats(
            season=STATS_SEASON,
            team_id_nullable=0,
            measure_type_detailed_defense='Advanced',
            per_mode_detailed='PerGame',
            timeout=60
        ).get_data_frames()[0]

        stats_base = leaguedashplayerstats.LeagueDashPlayerStats(
            season=STATS_SEASON,
            team_id_nullable=0,
            per_mode_detailed='PerGame',
            timeout=60
        ).get_data_frames()[0]
    except Exception as e:
        print(f"❌ 리그 전체 스탯 수집 실패: {e}")
        sys.exit(1)
        
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    updated_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    total_teams = len(TEAMS)
    
    print(f"\n🏀 NBA 30개 팀 2026-27 수집 및 [USG% 페널티 선차감 + 55:40:5 가중치] 계산 시작...\n", flush=True)
    
    for idx, (abbr, info) in enumerate(TEAMS.items(), 1):
        t_id, t_name = info['id'], info['name']
        print(f"[{idx}/{total_teams}] {abbr} ({t_name}) 수집 중...", end=" ", flush=True)
        try:
            roster_df = commonteamroster.CommonTeamRoster(
                season=ROSTER_SEASON, team_id=t_id, timeout=60
            ).get_data_frames()[0]
            
            player_names = roster_df['PLAYER'].tolist()
            df_adv = stats_adv[stats_adv['PLAYER_NAME'].isin(player_names)].copy()
            df_base = stats_base[stats_base['PLAYER_NAME'].isin(player_names)].copy()
            
            merged = pd.merge(roster_df[['PLAYER', 'POSITION']], df_adv[['PLAYER_NAME', 'MIN', 'PIE', 'USG_PCT']], left_on='PLAYER', right_on='PLAYER_NAME', how='left')
            merged = pd.merge(merged, df_base[['PLAYER_NAME', 'PTS', 'REB', 'AST']], on='PLAYER_NAME', how='left')
            
            merged['PIE'] = merged['PIE'].fillna(0.08)
            merged['MIN'] = merged['MIN'].fillna(0.0)
            merged['PTS'] = merged['PTS'].fillna(0.0)
            merged['REB'] = merged['REB'].fillna(0.0)
            merged['AST'] = merged['AST'].fillna(0.0)
            merged['USG_PCT'] = merged['USG_PCT'].fillna(0.15)
            
            merged['individual_uv'] = merged['PIE'].apply(calculate_individual_uv)
            merged = merged.sort_values(by='MIN', ascending=False).reset_index(drop=True)
            
            # 1. 주전 5인 선정
            starters = merged.head(5)
            rotation = merged.iloc[5:8]
            bench = merged.iloc[8:]
            
            # 2. Top 2 USG% 페널티 계산 (Top 2 USG > 60% 시 차감)
            top2_usg = starters.nlargest(2, 'USG_PCT')['USG_PCT'].sum()
            usg_penalty = (top2_usg - 0.60) * 3.0 if top2_usg > 0.60 else 0.0
            
            # 3. [1단계] 주전 5인 전력에서 USG% 페널티 선차감
            starters_uv_sum = starters['individual_uv'].sum()
            starters_adj_uv_sum = max(0.0, starters_uv_sum - usg_penalty)
            
            # 4. [2단계] 55:40:5 가중치 결합
            starters_contrib = starters_adj_uv_sum * 0.55
            
            rotation_avg = rotation['individual_uv'].mean() if not rotation.empty else 0.0
            rotation_contrib = (rotation_avg * 5.0) * 0.40 if not rotation.empty else 0.0
            
            bench_avg = bench['individual_uv'].mean() if not bench.empty else 0.0
            bench_contrib = (bench_avg * 5.0) * 0.05 if not bench.empty else 0.0
            
            final_team_uv = starters_contrib + rotation_contrib + bench_contrib
            
            cursor.execute('''
            INSERT INTO teams_uv 
            (team_abbr, team_name, top2_usg, usg_penalty, starters_uv_sum, starters_adj_uv_sum, starters_contrib, rotation_uv_avg, rotation_contrib, bench_uv_avg, bench_contrib, final_team_uv, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (abbr, t_name, top2_usg, usg_penalty, starters_uv_sum, starters_adj_uv_sum, starters_contrib, rotation_avg, rotation_contrib, bench_avg, bench_contrib, final_team_uv, updated_time))
            
            for rank_idx, row in merged.iterrows():
                min_rank = rank_idx + 1
                if min_rank <= 5: role_group = "주전 (Starters)"
                elif min_rank <= 8: role_group = "핵심 로테이션 (Rotation)"
                else: role_group = "딥 벤치 (Bench)"
                
                cursor.execute('''
                INSERT INTO players_uv
                (team_abbr, player_name, position, min_per_game, pts, reb, ast, pie, usg_pct, individual_uv, role_group, min_rank)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (abbr, row['PLAYER'], row['POSITION'], row['MIN'], row['PTS'], row['REB'], row['AST'], row['PIE'], row['USG_PCT'], row['individual_uv'], role_group, min_rank))
                
            print(f"✅ 완료 (최종 팀 UV: {final_team_uv:.2f} | USG 페널티: -{usg_penalty:.2f})")
            
        except Exception as e:
            print(f"❌ 실패: {e}")
        time.sleep(0.5)
        
    conn.commit()
    conn.close()
    print("\n🎉 USG% 페널티 차감 + 55:40:5 가중치 통합 DB 구축 완료!")

if __name__ == "__main__":
    main()
