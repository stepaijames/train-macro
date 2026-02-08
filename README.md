# train-macro

SRT / KTX 취소표 자동 예매 매크로

## 프로젝트 구조

```
train-macro/
├── .env              ← 개인 설정 (git 제외)
├── .env.example      ← 설정 템플릿
├── .gitignore
├── config.py         ← 환경변수 로드
├── notify.py         ← 텔레그램 알림
├── srt_macro.py      ← SRT 매크로
├── ktx_macro.py      ← KTX 매크로
├── requirements.txt
└── README.md
```

## 설치

```bash
cd ~/train-macro

# 가상환경 생성 및 활성화
python -m venv venv
.\venv\Scripts\activate        # Windows CMD/PowerShell
source venv/Scripts/activate   # Git Bash

# 라이브러리 설치
pip install -r requirements.txt
```

## 설정

`.env` 파일을 열어 개인 정보를 입력합니다.

```env
# SRT 계정 (SRT 이용 시)
SRT_ID=010XXXXXXXX
SRT_PW=비밀번호

# 코레일 계정 (KTX 이용 시)
KORAIL_ID=010XXXXXXXX
KORAIL_PW=비밀번호

# 열차 조건
DEP_STATION=수서          # 출발역
ARR_STATION=부산          # 도착역
DEP_DATE=20260213         # 출발일 (YYYYMMDD)
DEP_TIME=060000           # 조회 시작 시각 (HHMMSS)

# 텔레그램 알림 (선택)
TELEGRAM_BOT_TOKEN=봇토큰
TELEGRAM_CHAT_ID=채팅ID

# 매크로 설정
REFRESH_INTERVAL_MIN=3    # 최소 조회 간격 (초)
REFRESH_INTERVAL_MAX=10   # 최대 조회 간격 (초)
MAX_ATTEMPTS=1000         # 최대 조회 횟수
```

### 주요 역 이름

| SRT | KTX |
|-----|-----|
| 수서 | 서울 |
| 동탄 | 용산 |
| 평택지제 | 광명 |
| 천안아산 | 천안아산 |
| 오송 | 오송 |
| 대전 | 대전 |
| 동대구 | 동대구 |
| 부산 | 부산 |

## 실행

```bash
# SRT 취소표 매크로
python srt_macro.py

# KTX 취소표 매크로
python ktx_macro.py
```

## 텔레그램 알림 설정 (선택)

1. [@BotFather](https://t.me/BotFather)에서 봇 생성 → 토큰 복사
2. 봇에게 아무 메시지 전송
3. `https://api.telegram.org/bot<토큰>/getUpdates` 접속 → `chat.id` 확인
4. `.env`에 `TELEGRAM_BOT_TOKEN`과 `TELEGRAM_CHAT_ID` 입력

## 사용 라이브러리

- [SRTrain](https://github.com/ryanking13/SRT) — SRT API
- [korail2](https://github.com/carpedm20/korail2) — 코레일 API
- python-dotenv — 환경변수 관리
- requests — HTTP 요청
