"""
================================================================================
[파일명: espnapicheck.py] - 진단 키트 (Diagnostic Kit)
================================================================================

[역할]
1. 크롤링 디버깅 도구:
   - ESPN 같은 사이트가 HTML 구조를 바꿨을 때(예: Table -> Div 변경),
     데이터가 제대로 긁히는지 테스트하는 용도입니다.

2. 구조 파악:
   - 특정 선수의 이름이나 부상 상태 태그가 어떤 Class 이름을 쓰는지 
     확인할 때 사용합니다.

[참고]
- 평소에는 실행할 필요가 없으며, nbaapi.py에서 부상자가 0명으로 뜨는 등
  문제가 발생했을 때만 꺼내서 사용합니다.
================================================================================
"""
import requests
from bs4 import BeautifulSoup

url = "https://www.espn.com/nba/team/injuries/_/name/lal/los-angeles-lakers"
headers = {'User-Agent': 'Mozilla/5.0'}
res = requests.get(url, headers=headers)
soup = BeautifulSoup(res.text, 'html.parser')

print("=== [ESPN 태그 구조 정밀 분석] ===")

# "Austin Reaves"라는 글자가 포함된 태그를 직접 찾습니다.
# (태그 종류 상관없이 텍스트 내용으로 검색)
target = soup.find(string=lambda text: text and "Austin Reaves" in text)

if target:
    parent = target.parent # 텍스트를 감싸고 있는 바로 위 태그
    grandparent = parent.parent # 그 위의 부모 태그
    
    print(f"1. 찾은 텍스트: '{target}'")
    print(f"2. 감싸고 있는 태그 이름: <{parent.name}>") # div인지 span인지 a인지
    print(f"3. 그 태그의 속성(Class 등): {parent.attrs}")
    print(f"4. 부모 태그 이름: <{grandparent.name}>")
    print(f"5. 부모 태그의 속성(Class 등): {grandparent.attrs}")
else:
    print("텍스트는 있는데 태그를 못 찾았습니다. (매우 희박한 경우)")