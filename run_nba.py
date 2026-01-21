"""
================================================================================
[파일명: run_nba.py] - 미국 현지 시간 기준 저장 Ver (최종 수정)
================================================================================
"""
import sqlite3
import pandas as pd
import requests
import time
import config  # config.py 설정 불러오기
from bs4 import BeautifulSoup
from nba_api.stats.endpoints import leaguedashplayerstats, commonteamroster, scoreboardv2
from datetime import datetime, timedelta
from thefuzz import fuzz

# -----------------------------------------------------------------------------
# 1. 설정 및 상수
# -----------------------------------------------------------------------------
SEASON = '2025-26'
DB_PATH = "nba_data.db"

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
    'IND': {'id': '1610612754', 'slug': 'ind/indiana-pacers'},
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

# -----------------------------------------------------------------------------
# 2. 로직 함수
# -----------------------------------------------------------------------------
def calculate_individual_uv(pie):
    uv = 1.0 + (pie - 0.10) * 20
    return max(0.1, min(uv, 3.5))

def select_best_lineup(roster):
    sorted_players = roster.sort_values(by='contribution', ascending=False)
    starters = []
    
    guards = sorted_players[sorted_players['pos'].str.contains('G', na=False)]
    forwards = sorted_players[sorted_players['pos'].str.contains('F', na=False)]
    centers = sorted_players[sorted_players['pos'].str.contains('C', na=False)]
    
    selected_indices = set()
    
    def pick_player(pool, count):
        picked = 0
        for idx, row in pool.iterrows():
            if picked >= count: break
            if idx not in selected_indices:
                starters.append(row)
                selected_indices.add(idx)
                picked += 1
    
    pick_player(centers, 1)
    pick_player(guards, 2)
    pick_player(forwards, 2)
    
    if len(starters) < 5:
        for idx, row in sorted_players.iterrows():
            if len(starters) >= 5: break
            if idx not in selected_indices:
                starters.append(row)
                selected_indices.add(idx)

    return pd.DataFrame(starters)

def calculate_team_power(df, is_home=False):
    roster = df[df['availability'] != 'Out'].copy()
    if roster.empty: return 0.0, "데이터 없음"

    for col in ['pie', 'min', 'usg_pct']:
        roster[col] = pd.to_numeric(roster[col])

    roster['unit_value'] = roster['pie'].apply(calculate_individual_uv)
    roster['contribution'] = roster['unit_value'] * roster['min']
    
    total_minutes = roster['min'].sum()
    total_contribution = roster['contribution'].sum()
    
    if total_minutes < 240:
        missing = 240 - total_minutes
        total_contribution += (0.5 * missing)
        total_minutes = 240
        
    raw_score = (total_contribution / total_minutes) * 5
    
    home_adv_str = ""
    if is_home: 
        raw_score += 0.15
        home_adv_str = " + 홈이점(0.15)"

    top_2_usg = roster.nlargest(2, 'usg_pct')['usg_pct'].sum()
    penalty = 0.0
    penalty_str = ""
    if top_2_usg > 0.60:
        penalty = (top_2_usg - 0.60) * 3.0
        penalty_str = f" - 패널티({penalty:.2f})"
        
    final_score = raw_score - penalty

    starters_df = select_best_lineup(roster)
    detail_parts = []
    for _, row in starters_df.iterrows():
        detail_parts.append(f"{row['player_name']}({row['unit_value']:.1f})")
    
    detail_str = " / ".join(detail_parts)
    full_log = f"[{final_score:.2f}] = 베스트5[{detail_str}]{home_adv_str}{penalty_str}"
    
    return final_score, full_log

def get_team_stats_df(team_abbr):
    print(f"   Using Logic -> {team_abbr} 데이터 수집 중...", end=" ", flush=True)
    team_info = TEAMS.get(team_abbr)
    if not team_info: 
        print("❌ 정보 없음")
        return None, []
    
    for attempt in range(1, 4):
        try:
            stats = leaguedashplayerstats.LeagueDashPlayerStats(
                season=SEASON, team_id_nullable=team_info['id'],
                measure_type_detailed_defense='Advanced', per_mode_detailed='PerGame',
                timeout=60 
            )
            stats_df = stats.get_data_frames()[0]
            stats_df = stats_df[ (stats_df['GP'] >= 3) & (stats_df['MIN'] >= 10) ].copy()
            
            roster = commonteamroster.CommonTeamRoster(season=SEASON, team_id=team_info['id'], timeout=60)
            roster_df = roster.get_data_frames()[0]
            
            df = pd.merge(stats_df, roster_df[['PLAYER', 'POSITION']], left_on='PLAYER_NAME', right_on='PLAYER', how='left')
            df = df[['PLAYER_NAME', 'MIN', 'PIE', 'USG_PCT', 'POSITION']].copy()
            df.columns = ['player_name', 'min', 'pie', 'usg_pct', 'pos']
            df['pos'] = df['pos'].fillna('F')
            
            out_players = []
            try:
                injury_url = f"https://www.espn.com/nba/team/injuries/_/name/{team_info['slug']}"
                headers = {'User-Agent': 'Mozilla/5.0'}
                res = requests.get(injury_url, headers=headers, timeout=5)
                soup = BeautifulSoup(res.text, 'html.parser')
                for tag in soup.find_all('span', class_='Athlete__PlayerName'):
                    name = tag.text.strip()
                    parent_text = tag.parent.parent.get_text(" ", strip=True).lower()
                    if "out" in parent_text: out_players.append(name)
            except: pass

            df['availability'] = 'OK'
            for idx, row in df.iterrows():
                nba_name = row['player_name']
                for out_name in out_players:
                    if fuzz.partial_ratio(out_name.lower(), nba_name.lower()) >= 80:
                        df.at[idx, 'availability'] = 'Out'
                        break
            
            print("✅ 완료")
            return df, out_players
            
        except Exception as e:
            if attempt < 3:
                print(f"\n      ⚠️ 통신 지연(Attempt {attempt}/3)... 3초 후 재시도", end=" ")
                time.sleep(3)
            else:
                print(f"\n      ❌ 최종 실패: {e}")
                return None, []

def send_to_slack(text):
    try:
        token = config.SLACK_BOT_TOKEN
        if config.MODE == "REAL":
            channel_id = config.SLACK_REAL_CHANNEL_ID
            prefix = ""
        else:
            channel_id = config.SLACK_TEST_CHANNEL_ID
            prefix = "🛠 [테스트] "

        url = "https://slack.com/api/chat.postMessage"
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        data = {"channel": channel_id, "text": prefix + text}
        requests.post(url, headers=headers, json=data)
        print("✅ 슬랙 전송 완료!")
    except Exception as e:
        print(f"❌ 슬랙 에러: {e}")

# -----------------------------------------------------------------------------
# 3. 메인 실행
# -----------------------------------------------------------------------------
def main():
    print("\n" + "="*60)
    print("🚀 [1/3] NBA AI 분석 시스템 가동 (미국 현지 날짜 기준)")
    print("="*60 + "\n")
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS predictions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT, home_team TEXT, visit_team TEXT,
            predicted_winner TEXT, predicted_gap REAL,
            actual_winner TEXT, is_correct INTEGER
        )
    ''')
    conn.commit()

    # 한국 시간 기준 내일 경기 (미국 오늘)
    # [수정] target_date_us(미국 날짜)를 그대로 DB에 저장합니다. (+1일 안함)
    target_date_us = (datetime.now() - timedelta(hours=14)).strftime("%Y-%m-%d")
    print(f"📅 분석 대상 날짜 (US Date): {target_date_us}")
    
    save_date = target_date_us # 미국 날짜 그대로 사용
    
    print(f"🔄 [DB] '{save_date}' 데이터 갱신 모드 (중복 제거)")
    cursor.execute("DELETE FROM predictions WHERE date = ?", (save_date,))
    conn.commit()

    try:
        board = scoreboardv2.ScoreboardV2(game_date=target_date_us, timeout=60)
        games_df = board.game_header.get_data_frame()
    except Exception as e:
        print(f"❌ 경기 일정 조회 실패: {e}")
        return

    if games_df.empty:
        print("❌ 예정된 경기가 없습니다.")
        return

    slack_msg = f"🏀 *NBA AI 승부예측 리포트* ({save_date} US)\n"
    slack_msg += "================================\n"

    print("\n🚀 [2/3] 경기별 정밀 분석 시작...\n")

    processed_games = set()

    for idx, row in games_df.iterrows():
        game_id = row['GAME_ID']
        if game_id in processed_games: continue
        processed_games.add(game_id)

        h_id = str(row['HOME_TEAM_ID'])
        v_id = str(row['VISITOR_TEAM_ID'])
        h_team = ID_TO_ABBR.get(h_id, 'Unknown')
        v_team = ID_TO_ABBR.get(v_id, 'Unknown')
        
        if h_team == 'Unknown' or v_team == 'Unknown': continue

        print(f"⚔️  MATCHUP: {v_team} (원정) vs {h_team} (홈)")
        print("-" * 50)
        
        h_res, h_out = get_team_stats_df(h_team)
        v_res, v_out = get_team_stats_df(v_team)
        
        if h_res is None or v_res is None:
            print("   -> ⚠️ 데이터 부족으로 패스")
            continue
            
        h_score, h_log = calculate_team_power(h_res, is_home=True)
        v_score, v_log = calculate_team_power(v_res, is_home=False)
        
        print(f"   🏠 {h_team}: {h_log}")
        if h_out: print(f"      🚑 결장: {', '.join(h_out)}")
        
        print(f"   🚌 {v_team}: {v_log}")
        if v_out: print(f"      🚑 결장: {', '.join(v_out)}")

        gap = abs(h_score - v_score)
        predicted_winner = h_team if h_score > v_score else v_team
        
        print(f"   🔮 예측: {predicted_winner} 승리 (격차: {gap:.2f})")
        print("=" * 50 + "\n")

        # 슬랙 메시지
        slack_msg += f"\n[✈️{v_team}] vs [🏠{h_team}]\n"
        
        if v_score > h_score:
            slack_msg += f"UV: *{v_score:.2f}* > {h_score:.2f}\n"
        else:
            slack_msg += f"UV: {v_score:.2f} < *{h_score:.2f}*\n"
        
        icon = "💪" if gap >= 1.0 else "👉"
        
        if predicted_winner == h_team:
            slack_msg += f"{icon} [🏠{h_team}] 우세 (`+{gap:.2f}`)\n"
        else:
            slack_msg += f"{icon} [✈️{v_team}] 우세 (`+{gap:.2f}`)\n"
            
        if h_out or v_out:
            slack_msg += "🚑 주요 결장:\n"
            if h_out: slack_msg += f"   {h_team}: {', '.join(h_out)}\n"
            if v_out: slack_msg += f"   {v_team}: {', '.join(v_out)}\n"
            
        slack_msg += "--------------------------------\n"

        # DB 저장 (미국 날짜 그대로)
        actual_winner = None
        is_correct = None
        
        cursor.execute('''
            INSERT INTO predictions (date, home_team, visit_team, predicted_winner, predicted_gap, actual_winner, is_correct)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (save_date, h_team, v_team, predicted_winner, gap, actual_winner, is_correct))
        conn.commit()

    conn.close()
    
    print("🚀 [3/3] 결과 리포트 전송 중...")
    slack_msg += "※ 상세 데이터는 대시보드를 확인하세요."
    
    send_to_slack(slack_msg)
    print("✅ 모든 작업 완료!")

if __name__ == "__main__":
    main()