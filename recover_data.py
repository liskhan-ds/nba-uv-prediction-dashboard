"""
================================================================================
[파일명: recover_data.py] - 1월 19일 데이터 긴급 복구 도구 (채점 기능 포함)
================================================================================
"""
import sqlite3
import pandas as pd
from datetime import datetime
from nba_api.live.nba.endpoints import scoreboard 
from nba_api.stats.endpoints import scoreboardv2

# -----------------------------------------------------------------------------
# 1. 설정
# -----------------------------------------------------------------------------
DB_PATH = "nba_data.db"
TARGET_DATE_US = "2026-01-19" # 복구할 미국 현지 날짜
SAVE_DATE_KST = "2026-01-20"  # DB에 저장될 한국 날짜 (대시보드 표기용)

# 웅쓰님이 주신 슬랙 데이터 파싱 (순서: 원정, 홈, 예측팀, 격차)
# [주의] 슬랙 원본 포맷: [팀1] vs [팀2]
RECOVERY_DATA = [
    {"v": "MIL", "h": "ATL", "pred": "MIL", "gap": 0.26},
    {"v": "OKC", "h": "CLE", "pred": "OKC", "gap": 0.72},
    {"v": "LAC", "h": "WAS", "pred": "LAC", "gap": 0.18},
    {"v": "DAL", "h": "NYK", "pred": "NYK", "gap": 1.81},
    {"v": "UTA", "h": "SAS", "pred": "SAS", "gap": 2.83},
    {"v": "IND", "h": "PHI", "pred": "PHI", "gap": 1.05},
    {"v": "PHX", "h": "BKN", "pred": "PHX", "gap": 1.68},
    {"v": "BOS", "h": "DET", "pred": "DET", "gap": 0.88},
    {"v": "MIA", "h": "GSW", "pred": "GSW", "gap": 0.47},
]

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

def main():
    print(f"🚀 데이터 복구 시작 (Target: {TARGET_DATE_US} US / {SAVE_DATE_KST} KST)")
    
    # 1. DB 연결
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # 혹시 중복 될까봐 해당 날짜 데이터만 깔끔하게 비우고 시작
    cursor.execute("DELETE FROM predictions WHERE date = ?", (SAVE_DATE_KST,))
    conn.commit()

    # 2. 실제 경기 결과 가져오기 (채점용)
    print("🌍 NBA 서버에서 실제 경기 결과 조회 중...")
    try:
        board = scoreboardv2.ScoreboardV2(game_date=TARGET_DATE_US)
        games_df = board.line_score.get_data_frame()
        
        # 경기별 승자 딕셔너리 생성 (Key: GameID, Value: Winner Abbr)
        # ScoreboardV2는 팀별로 row가 나뉘어 있어서 처리가 필요함
        # 간단하게 Header 정보로 승자 판별
        header_df = board.game_header.get_data_frame()
        line_df = board.line_score.get_data_frame()
        
        actual_results = {} # { 'ATL': 'W', 'MIL': 'L' ... } 형태가 아니라 매치업별 승자 찾기
        
        # 간단한 로직: ScoreboardV2의 line_score에서 점수 비교
        # 게임 ID별로 그룹화
        game_ids = line_df['GAME_ID'].unique()
        
        match_winners = {} # {'MILvsATL': 'MIL', ...}
        
        for gid in game_ids:
            g_data = line_df[line_df['GAME_ID'] == gid]
            if len(g_data) < 2: continue
            
            team_a = g_data.iloc[0]
            team_b = g_data.iloc[1]
            
            abbr_a = TEAMS.get(str(team_a['TEAM_ID']), 'Unknown')
            abbr_b = TEAMS.get(str(team_b['TEAM_ID']), 'Unknown')
            
            score_a = team_a['PTS']
            score_b = team_b['PTS']
            
            winner = abbr_a if score_a > score_b else abbr_b
            
            # 매치업 키 생성 (양방향 확인을 위해 Set 사용 또는 두가지 다 저장)
            match_winners[f"{abbr_a}vs{abbr_b}"] = winner
            match_winners[f"{abbr_b}vs{abbr_a}"] = winner
            
    except Exception as e:
        print(f"❌ 실제 결과 조회 실패: {e}")
        match_winners = {}

    # 3. 데이터 입력
    print("📝 데이터 DB 입력 중...")
    
    count = 0
    correct_count = 0
    
    for item in RECOVERY_DATA:
        v_team = item['v']
        h_team = item['h']
        pred_winner = item['pred']
        gap = item['gap']
        
        # 실제 승자 찾기
        key = f"{v_team}vs{h_team}"
        actual_winner = match_winners.get(key, None)
        
        # 정답 여부
        is_correct = None
        if actual_winner:
            is_correct = 1 if actual_winner == pred_winner else 0
            if is_correct: correct_count += 1
        
        # DB Insert
        cursor.execute('''
            INSERT INTO predictions (date, home_team, visit_team, predicted_winner, predicted_gap, actual_winner, is_correct)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (SAVE_DATE_KST, h_team, v_team, pred_winner, gap, actual_winner, is_correct))
        
        count += 1
        print(f"   -> {v_team} vs {h_team} : 예측({pred_winner}) / 실제({actual_winner}) => {'✅ 정답' if is_correct else '❌ 오답'}")

    conn.commit()
    conn.close()
    
    print("="*50)
    print(f"🎉 복구 완료! 총 {count}개 경기 저장됨.")
    if count > 0:
        acc = (correct_count / count) * 100
        print(f"📊 당시 적중률: {acc:.1f}% ({correct_count}/{count})")
    print("="*50)

if __name__ == "__main__":
    main()