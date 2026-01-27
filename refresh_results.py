"""
================================================================================
[파일명: refresh_results.py] - 과거 데이터 전수 조사 및 동기화 (Data Sync)
================================================================================
"""
import sqlite3
import pandas as pd
import os
from datetime import datetime, timedelta
from nba_api.stats.endpoints import scoreboardv2

# 1. 설정
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "nba_data.db")

# 팀 ID -> 약어 매핑 (필요시 추가)
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

def sync_data():
    print("🔄 NBA 데이터 동기화 시작 (1월 19일 ~ 오늘)...")
    
    if not os.path.exists(DB_PATH):
        print("❌ DB 파일이 없습니다.")
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # 동기화 기간 설정 (1월 19일부터 오늘까지)
    start_date = datetime(2026, 1, 19)
    end_date = datetime.now()
    
    current_date = start_date
    total_updated = 0

    while current_date <= end_date:
        target_date = current_date.strftime("%Y-%m-%d")
        print(f"\n📅 [확인 중] {target_date}")
        
        # 1. DB에서 그날의 예측 데이터 가져오기
        cursor.execute("SELECT rowid, home_team, visit_team, predicted_winner FROM predictions WHERE date = ?", (target_date,))
        db_rows = cursor.fetchall()
        
        if not db_rows:
            print(" - 저장된 예측 데이터 없음. 패스.")
            current_date += timedelta(days=1)
            continue

        # 2. NBA API에서 실제 결과 가져오기
        try:
            board = scoreboardv2.ScoreboardV2(game_date=target_date)
            header_df = board.game_header.get_data_frame()
            line_df = board.line_score.get_data_frame()
        except Exception as e:
            print(f"❌ API 접속 실패 ({target_date}): {e}")
            current_date += timedelta(days=1)
            continue

        # API 데이터를 보기 좋게 가공 (매치업 -> 결과/상태)
        api_results = {} # Key: "VISITvsHOME", Value: {"status": "Final/PPD", "winner": "LAL"}
        
        if not header_df.empty:
            for _, row in header_df.iterrows():
                h_id = str(row['HOME_TEAM_ID'])
                v_id = str(row['VISITOR_TEAM_ID'])
                h_abbr = TEAMS.get(h_id, 'Unknown')
                v_abbr = TEAMS.get(v_id, 'Unknown')
                
                key = f"{v_abbr}vs{h_abbr}"
                status_text = str(row.get('GAME_STATUS_TEXT', '')).upper()
                
                # 승자 확인
                winner = None
                if "Final" in status_text or row['GAME_STATUS_ID'] == 3:
                    # 점수 확인
                    try:
                        pts_h = line_df[line_df['TEAM_ID'] == int(h_id)]['PTS'].values[0]
                        pts_v = line_df[line_df['TEAM_ID'] == int(v_id)]['PTS'].values[0]
                        winner = h_abbr if pts_h > pts_v else v_abbr
                    except:
                        winner = None
                
                api_results[key] = {
                    "status_text": status_text,
                    "winner": winner
                }

        # 3. DB와 API 대조 및 업데이트
        for row in db_rows:
            r_id, h_team, v_team, pred = row
            key = f"{v_team}vs{h_team}"
            
            # API에 해당 경기가 있는가?
            if key in api_results:
                api_data = api_results[key]
                status = api_data["status_text"]
                real_winner = api_data["winner"]
                
                # [Case A] PPD (연기됨)
                if "PPD" in status or "POSTPONED" in status:
                    print(f"   => 🆖 {key} : API 상태 '{status}' -> 'Postponed' 처리")
                    cursor.execute("UPDATE predictions SET actual_winner = 'Postponed', is_correct = NULL WHERE rowid = ?", (r_id,))
                    total_updated += 1
                
                # [Case B] 정상 종료 (Final)
                elif real_winner:
                    # 채점 로직
                    is_correct = 1 if pred == real_winner else 0
                    print(f"   => ✅ {key} : 결과 '{real_winner}' (예측 {pred}) -> 채점 완료")
                    cursor.execute("UPDATE predictions SET actual_winner = ?, is_correct = ? WHERE rowid = ?", (real_winner, is_correct, r_id))
                    total_updated += 1
            
            else:
                # [Case C] DB엔 있는데 API엔 없음 (날짜 변경/증발) -> 1월 24일 GSW 사례
                print(f"   => 👻 {key} : API 목록에 없음 (날짜 변경됨) -> 'Postponed' 처리")
                cursor.execute("UPDATE predictions SET actual_winner = 'Postponed', is_correct = NULL WHERE rowid = ?", (r_id,))
                total_updated += 1

        conn.commit()
        current_date += timedelta(days=1)

    conn.close()
    print(f"\n✅ 동기화 완료! 총 {total_updated}개의 데이터가 최신화되었습니다.")
    print("👉 이제 대시보드를 새로고침 해보세요.")

if __name__ == "__main__":
    sync_data()