import sqlite3
import requests
import pandas as pd
import config
import os
import time
import sys
from datetime import datetime, timedelta
from nba_api.stats.endpoints import scoreboardv2

# -----------------------------------------------------------------------------
# 1. 설정 (웅쓰님 환경 유지)
# -----------------------------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "nba_data.db")
DASHBOARD_URL = "https://nba-uv-prediction-dashboard-6ahdkhmixcsa3uybaz6ez6.streamlit.app/"

TEAMS = {
    '1610612737': 'ATL', '1610612738': 'BOS', '1610612751': 'BKN', '1610612766': 'CHA',
    '1610612741': 'CHI', '1610612739': 'CLE', '1610612742': 'DAL', '1610612743': 'DEN',
    '1610612765': 'DET', '1610612744': 'GSW', '1610612745': 'HOU', '1610612754': 'IND',
    '1610612746': 'LAC', '1610612747': 'LAL', '1610612763': 'MEM', '1610612748': 'MIA',
    '1610612749': 'MIL', '1610612750': 'MIN', '1610612740': 'NOP', '1610612752': 'NYK',
    '1610612760': 'OKC', '1610612753': 'ORL', '1610612755': 'PHI', '1610612756': 'PHX',
    '1610612757': 'POR', '1610612758': 'SAC', '1610612759': 'SAS', '1610612761': 'TOR',
    '1610612762': 'UTA', '1610612764': 'WAS'
}

def send_to_slack(text):
    try:
        token = config.SLACK_BOT_TOKEN
        channel_id = config.SLACK_REAL_CHANNEL_ID if config.MODE == "REAL" else config.SLACK_TEST_CHANNEL_ID
        url = "https://slack.com/api/chat.postMessage"
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        data = {"channel": channel_id, "text": text}
        requests.post(url, headers=headers, json=data)
        print("✅ 슬랙 전송 완료!")
    except Exception as e:
        print(f"❌ 슬랙 에러: {e}")

def main():
    print("🕵️‍♂️ 경기 결과 확인 및 채점 시작 (보안 우회 및 에러 수정 버전)...")
    
    if not os.path.exists(DB_PATH):
        print(f"❌ 에러: DB 파일을 찾을 수 없습니다.\n경로: {DB_PATH}")
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # 채점 대상 날짜
    if len(sys.argv) > 1:
        target_date_us = sys.argv[1]
    else:
        target_date_us = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    print(f"📅 채점 대상 날짜 (US): {target_date_us}")
    
    cursor.execute("SELECT rowid, home_team, visit_team, predicted_winner, actual_winner FROM predictions WHERE date = ?", (target_date_us,))
    rows = cursor.fetchall()
    
    if not rows:
        print(f"❌ {target_date_us} 날짜에 저장된 예측 데이터가 없습니다.")
        conn.close()
        return

    # [수정] NBA 서버 차단을 피하기 위한 커스텀 헤더 설정
    custom_headers = {
        'Host': 'stats.nba.com',
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Referer': 'https://www.nba.com/',
        'Origin': 'https://www.nba.com',
        'x-nba-stats-origin': 'stats',
        'x-nba-stats-token': 'true',
    }

    # [수정] 재시도 로직 및 헤더 주입
    board_v2 = None
    for i in range(3):
        try:
            print(f"📡 NBA 서버 연결 시도 중... ({i+1}/3)")
            board_v2 = scoreboardv2.ScoreboardV2(
                game_date=target_date_us, 
                timeout=60
            )
            break 
        except Exception as e:
            print(f"⚠️ 연결 지연 발생: {e}")
            if i < 2: 
                print("5초 후 다시 시도합니다...")
                time.sleep(5)
            else:
                print("❌ 최종 연결 실패. 서버가 응답하지 않습니다.")
                conn.close()
                return

    try:
        header_df = board_v2.game_header.get_data_frame()
        line_df = board_v2.line_score.get_data_frame()
    except Exception as e:
        print(f"❌ 데이터 파싱 에러: {e}")
        conn.close()
        return

    actual_results = {}
    
    # 1. 경기 상태(Status) 기반 1차 분류
    game_status_map = {}
    if not header_df.empty:
        for _, row in header_df.iterrows():
            gid = str(row['GAME_ID'])
            status_text = str(row.get('GAME_STATUS_TEXT', '')).upper()
            home_id, visit_id = str(row['HOME_TEAM_ID']), str(row['VISITOR_TEAM_ID'])
            home_abbr, visit_abbr = TEAMS.get(home_id, 'Unknown'), TEAMS.get(visit_id, 'Unknown')
            
            key = f"{visit_abbr}vs{home_abbr}"
            game_status_map[gid] = status_text

            if "PPD" in status_text or "POSTPONED" in status_text:
                actual_results[key] = "Postponed"
            elif "FINAL" not in status_text:
                actual_results[key] = "Live"

    # 2. 종료된 경기(FINAL)에 대해서만 승자 확인
    if not line_df.empty:
        game_ids = line_df['GAME_ID'].unique()
        for gid in game_ids:
            status = game_status_map.get(gid, "")
            if "FINAL" in status:
                g_data = line_df[line_df['GAME_ID'] == gid]
                if len(g_data) < 2: continue
                
                team_a, team_b = g_data.iloc[0], g_data.iloc[1]
                if pd.isna(team_a['PTS']) or pd.isna(team_b['PTS']): continue
                    
                abbr_a, abbr_b = TEAMS.get(str(team_a['TEAM_ID']), 'Unknown'), TEAMS.get(str(team_b['TEAM_ID']), 'Unknown')
                winner = abbr_a if team_a['PTS'] > team_b['PTS'] else abbr_b
                actual_results[f"{abbr_a}vs{abbr_b}"] = winner
                actual_results[f"{abbr_b}vs{abbr_a}"] = winner

    # 3. 채점 및 메시지 작성
    correct_count = 0
    total_valid_games = 0
    results_msg = []
    
    for row in rows:
        r_id, h_team, v_team, pred, db_actual = row
        key = f"{v_team}vs{h_team}"
        current_status = actual_results.get(key)
        
        # [Case A] 경기 취소
        if current_status == "Postponed" or db_actual == "Postponed":
            results_msg.append(f"🆖 {v_team} vs {h_team} (경기 취소/연기)")
            results_msg.append("-" * 30)
            cursor.execute("UPDATE predictions SET actual_winner = 'Postponed', is_correct = NULL WHERE rowid = ?", (r_id,))
            
        # [Case B] 경기 종료 (승자가 확실히 나온 경우)
        elif current_status and current_status != "Live":
            is_correct = 1 if current_status == pred else 0
            if is_correct: correct_count += 1
            total_valid_games += 1
            cursor.execute("UPDATE predictions SET actual_winner = ?, is_correct = ? WHERE rowid = ?", (current_status, is_correct, r_id))
            icon = "✅" if is_correct else "❌"
            results_msg.append(f"{icon} {v_team} vs {h_team}\n   (AI: {pred} / 결과: {current_status})")
            results_msg.append("-" * 30)
            
        # [Case C] 아직 진행 중 (Live)
        else:
            results_msg.append(f"⏳ {v_team} vs {h_team} 경기 진행 중...")
            results_msg.append("-" * 30)
            
    conn.commit()
    conn.close()
    
    # 4. 리포트 완성 및 발송
    header = f"📊 *UV Predictor NBA 예측 성적표* ({target_date_us})\n"
    if total_valid_games > 0:
        acc = (correct_count / total_valid_games) * 100
        header += f"현재 적중률: *{acc:.1f}%* ({correct_count}/{total_valid_games})\n"
        header += "(취소된 경기는 통계에서 제외됨)\n"
    else:
        header += "현재 종료된 경기가 없습니다. (모든 경기가 진행 중이거나 취소됨)\n"
        
    slack_text = f"{header}================================\n" + "\n".join(results_msg) + \
                 f"\n================================\n※ 상세 데이터:\n👉 {DASHBOARD_URL}"
    
    print("\n" + slack_text)
    send_to_slack(slack_text)

if __name__ == "__main__":
    main()