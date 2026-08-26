import requests
import json
import os
import sys
from datetime import datetime

# --- [설정] 슬랙 웹훅 URL ---
SLACK_WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL", "YOUR_SLACK_WEBHOOK_URL_HERE")

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
try:
    import predictor 
except ImportError:
    sys.exit(1)

def send_slack_msg(message):
    headers = {'Content-Type': 'application/json'}
    payload = {'text': message}
    requests.post(SLACK_WEBHOOK_URL, headers=headers, data=json.dumps(payload))

def create_briefing_report():
    from nba_api.stats.endpoints import scoreboardv2
    
    # 1. 시차 보정 및 날짜 계산 (미국 날짜 기준)
    now_kst = datetime.now()
    us_game_date = now_kst - predictor.timedelta(hours=14)
    game_date_str = us_game_date.strftime("%Y-%m-%d")
    
    try:
        board = scoreboardv2.ScoreboardV2(game_date=game_date_str)
        games_df = board.game_header.get_data_frame()
        line_score = board.line_score.get_data_frame()
    except:
        return None

    report_lines = [f"📊 *웅쓰 테스트 성적표* ({game_date_str})"]
    game_details = []
    final_count, hit_count = 0, 0

    for _, game in games_df.iterrows():
        # [핵심 1] GAME_STATUS_ID 판별 (정수형 변환으로 타입 오류 방지)
        status_id = int(game['GAME_STATUS_ID'])
        status_text = game['GAME_STATUS_TEXT']
        home_id, away_id = game['HOME_TEAM_ID'], game['VISITOR_TEAM_ID']
        home_abbr = predictor.ID_TO_ABBR.get(str(home_id), "UNK")
        away_abbr = predictor.ID_TO_ABBR.get(str(away_id), "UNK")

        # --- A. 경기 종료 (ID: 3) ---
        if status_id == 3:
            try:
                h_pts = line_score[line_score['TEAM_ID'] == home_id]['PTS'].values[0]
                a_pts = line_score[line_score['TEAM_ID'] == away_id]['PTS'].values[0]
                
                # 예측 결과 판정 (웅쓰 로직 적용)
                ai_pick = home_abbr # 예시 기준
                actual_winner = home_abbr if h_pts > a_pts else away_abbr
                is_hit = (ai_pick == actual_winner)
                
                if is_hit: hit_count += 1
                final_count += 1 # 통계에 포함
                
                icon = "✅" if is_hit else "❌"
                game_details.append(f"{icon} {away_abbr} {a_pts} vs {h_pts} {home_abbr} (종료)")
                game_details.append(f"   (AI: {ai_pick} / 결과: {actual_winner})")
            except: continue

        # --- B. 경기 진행 중 (ID: 2) ---
        elif status_id == 2:
            try:
                h_pts = line_score[line_score['TEAM_ID'] == home_id]['PTS'].values[0]
                a_pts = line_score[line_score['TEAM_ID'] == away_id]['PTS'].values[0]
                game_details.append(f"⏳ {away_abbr} {a_pts} vs {h_pts} {home_abbr} ({status_text} 진행 중...)")
            except: continue

        # --- C. 경기 취소/연기 (ID: 0 또는 PPD 포함) ---
        elif status_id == 0 or "PPD" in status_text:
            game_details.append(f"🚫 {away_abbr} vs {home_abbr} - 경기 취소/연기됨")
            # final_count에 포함시키지 않음 (통계 제외)

        # --- D. 경기 시작 전 (ID: 1) ---
        elif status_id == 1:
            game_details.append(f"📅 {away_abbr} vs {home_abbr} (경기 예정 - {status_text})")

        game_details.append("-" * 30)

    # [핵심 2] 적중률 계산 (종료된 경기만)
    if final_count > 0:
        acc = (hit_count / final_count) * 100
        report_lines.append(f"현재 적중률: *{acc:.1f}%* ({hit_count}/{final_count})")
    else:
        report_lines.append("현재 종료된 경기가 없습니다.")
        
    report_lines.append("(취소된 경기는 통계에서 제외됨)")
    report_lines.append("=" * 35)
    report_lines.extend(game_details)
    
    return "\n".join(report_lines)

if __name__ == "__main__":
    report = create_briefing_report()
    if report:
        send_slack_msg(report)