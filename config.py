"""
================================================================================
[파일명: config.py] - 슬랙 설정 파일
================================================================================
"""

# 1. 봇 토큰 (xoxb- 로 시작하는 값)
# -> https://api.slack.com/apps > OAuth & Permissions > Bot User OAuth Token
SLACK_BOT_TOKEN = "xoxb-10321508716741-10328534004116-feJ69S4fJzDRjYbrD9MwA7oa" 

# 2. 테스트용 채널 ID (C 로 시작하는 값)
# -> 슬랙 채널 우클릭 > 세부정보 보기 > 맨 아래 Channel ID 복사
SLACK_TEST_CHANNEL_ID = "C0A9UFCE5PE" 

# 3. 실제 배포용 채널 ID (리얼 모드일 때 발송될 곳)
# -> 모르면 위 테스트 채널 ID와 똑같이 적으셔도 됩니다.
SLACK_REAL_CHANNEL_ID = "C0A9GSZQD1U" 

# 4. 현재 모드 설정
# "TEST" -> 테스트 채널로만 발송 (개발 중일 때 추천)
# "REAL" -> 실제 채널로 발송 (사람들에게 보여줄 때)
MODE = "REAL"