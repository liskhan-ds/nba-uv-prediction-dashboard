"""
================================================================================
[파일명: check_results.py] - 취소 경기(Postponed) 완벽 대응 및 리포트 버전
================================================================================
"""
import sqlite3
import requests
import pandas as pd
import config
import os
from datetime import datetime, timedelta
from nba_api.stats.endpoints import scoreboardv2

# -----------------------------------------------------------------------------
# 1. 설정 (웅쓰님 환경 유지)
# -----------------------------------------------------------------------------
BASE_DIR = "/Users/kimwoongsub/Desktop/nba_test"
DB_PATH = os.path.join(BASE_DIR, "nba_data.db")
DASHBOARD_URL = "https://nba-uv-prediction-dashboard-6ahdkhmixcsa3uybaz6ez6.streamlit.app/"

# 팀 ID -> 약어 매핑
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
        # 모드에 따른 채널 선택
        if config.MODE == "REAL":
            channel_id = config.SLACK_REAL_CHANNEL_ID
        else:
            channel_id = config.SLACK_TEST_CHANNEL_ID

        url = "https://slack.com/api/chat.postMessage"
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        data = {"channel": channel_id, "text": text}
        requests.post(url, headers=headers, json=data)
        print("✅ 슬랙 전송 완료!")
    except Exception as e:
        print(f"❌ 슬랙 에러: {e}")

def main():
    print("🕵️‍♂️ 경기 결과 확인 및 채점 시작...")
    
    if not os.path.exists(DB_PATH):
        print(f"❌ 에러: DB 파일을 찾을 수 없습니다.\n경로: {DB_PATH}")
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # 채점 대상 날짜 (미국 기준 어제)
    target_date_us = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    print(f"📅 채점 대상 날짜 (US): {target_date_us}")
    
    # [중요] 웅쓰님 DB 컬럼명 사용 (visit_team, predicted_winner)
    cursor.execute("SELECT rowid, home_team, visit_team, predicted_winner, actual_winner FROM predictions WHERE date = ?", (target_date_us,))
    rows = cursor.fetchall()
    
    if not rows:
        print(f"❌ {target_date_us} 날짜에 저장된 예측 데이터가 없습니다.")
        conn.close()
        return

    # NBA 공식 데이터 가져오기
    try:
        board_v2 = scoreboardv2.ScoreboardV2(game_date=target_date_us)
        header_df = board_v2.game_header.get_data_frame()
        line_df = board_v2.line_score.get_data_frame()
    except Exception as e:
        print(f"❌ NBA 서버 접속 실패: {e}")
        conn.close()
        return

    # 결과 매핑 딕셔너리
    actual_results = {}
    
    # 1. 경기 취소/진행 상태 확인
    if not header_df.empty:
        for index, row in header_df.iterrows():
            status_text = str(row.get('GAME_STATUS_TEXT', '')).upper()
            home_id = str(row['HOME_TEAM_ID'])
            visit_id = str(row['VISITOR_TEAM_ID'])
            
            home_abbr = TEAMS.get(home_id, 'Unknown')
            visit_abbr = TEAMS.get(visit_id, 'Unknown')
            
            key1 = f"{visit_abbr}vs{home_abbr}"
            key2 = f"{home_abbr}vs{visit_abbr}"

            # [핵심] 취소(PPD)된 경기 감지
            if "PPD" in status_text or "POSTPONED" in status_text:
                actual_results[key1] = "Postponed"
                actual_results[key2] = "Postponed"

    # 2. 종료된 경기 승자 확인 (점수 비교)
    if not line_df.empty:
        game_ids = line_df['GAME_ID'].unique()
        for gid in game_ids:
            g_data = line_df[line_df['GAME_ID'] == gid]
            if len(g_data) < 2: continue
            
            team_a = g_data.iloc[0]
            team_b = g_data.iloc[1]
            
            # 점수가 없으면(NaN) 패스
            if pd.isna(team_a['PTS']) or pd.isna(team_b['PTS']):
                continue
                
            id_a = str(team_a['TEAM_ID'])
            id_b = str(team_b['TEAM_ID'])
            abbr_a = TEAMS.get(id_a, 'Unknown')
            abbr_b = TEAMS.get(id_b, 'Unknown')

            winner = abbr_a if team_a['PTS'] > team_b['PTS'] else abbr_b
            
            actual_results[f"{abbr_a}vs{abbr_b}"] = winner
            actual_results[f"{abbr_b}vs{abbr_a}"] = winner

    # 3. 채점 및 메시지 작성
    correct_count = 0
    total_valid_games = 0  # 취소되지 않은 경기 수
    results_msg = []
    
    for row in rows:
        r_id = row[0]
        h_team = row[1]
        v_team = row[2]
        pred = row[3]
        db_actual = row[4] # DB에 이미 저장된 결과 (방금 fix_history로 수정한 값 포함)
        
        key = f"{v_team}vs{h_team}"
        
        # 라이브 데이터에서 확인하거나, DB에 이미 'Postponed'라고 되어 있는지 확인
        current_status = actual_results.get(key)
        
        # [Case A] 경기 취소 (라이브에서 PPD거나, DB에 이미 Postponed로 박혀있을 때)
        if current_status == "Postponed" or db_actual == "Postponed":
            results_msg.append(f"🆖 {v_team} vs {h_team} (경기 취소/연기)")
            results_msg.append("-" * 30)
            
            # DB 상태 업데이트 (확실하게 하기 위해)
            cursor.execute("UPDATE predictions SET actual_winner = 'Postponed', is_correct = NULL WHERE rowid = ?", (r_id,))
            
        # [Case B] 경기 종료 (승자가 나온 경우)
        elif current_status:
            is_correct = 1 if current_status == pred else 0
            if is_correct: correct_count += 1
            total_valid_games += 1
            
            cursor.execute("UPDATE predictions SET actual_winner = ?, is_correct = ? WHERE rowid = ?", (current_status, is_correct, r_id))
            
            icon = "✅" if is_correct else "❌"
            results_msg.append(f"{icon} {v_team} vs {h_team}\n   (AI: {pred} / 결과: {current_status})")
            results_msg.append("-" * 30)
            
        # [Case C] 아직 진행 중
        else:
            results_msg.append(f"⏳ {v_team} vs {h_team} 경기 진행 중...")
            
    conn.commit()
    conn.close()
    
    # 4. 슬랙 리포트 발송
    if total_valid_games > 0:
        acc = (correct_count / total_valid_games) * 100
        header = f"📊 *NBA AI 예측 성적표* ({target_date_us})\n"
        header += f"현재 적중률: *{acc:.1f}%* ({correct_count}/{total_valid_games})\n"
        header += "(취소된 경기는 통계에서 제외됨)\n"
    else:
        header = f"📊 *NBA AI 예측 성적표* ({target_date_us})\n"
        if len(rows) > 0 and len(results_msg) > 0:
             header += "모든 경기가 취소되었거나 진행 중입니다.\n"
        else:
             header += "종료된 경기가 없습니다.\n"
        
    slack_text = header
    slack_text += "================================\n"
    slack_text += "\n".join(results_msg)
    slack_text += "\n================================\n"
    slack_text += "※ 상세 데이터 및 그래프:\n"
    slack_text += f"👉 {DASHBOARD_URL}"
    
    send_to_slack(slack_text)

if __name__ == "__main__":
    main()