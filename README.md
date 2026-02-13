# train-macro

SRT / KTX 취소표 자동 예매 매크로 + 텔레그램 봇

## 프로젝트 구조

```
train-macro/
├── .env              ← 개인 설정 (git 제외)
├── .env.example      ← 설정 템플릿
├── .gitignore
├── config.py         ← 환경변수 로드
├── bot.py            ← 텔레그램 봇 (메인)
├── notify.py         ← 텔레그램 알림 (CLI용)
├── srt_macro.py      ← SRT 매크로 (CLI)
├── ktx_macro.py      ← KTX 매크로 (CLI)
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

`.env.example`을 `.env`로 복사 후 개인 정보를 입력합니다.

```env
# SRT 계정 (SRT 이용 시)
SRT_ID=010XXXXXXXX
SRT_PW=비밀번호

# 코레일 계정 (KTX 이용 시)
KORAIL_ID=010XXXXXXXX
KORAIL_PW=비밀번호

# 열차 조건 (CLI 매크로용)
DEP_STATION=수서
ARR_STATION=부산
DEP_DATE=20260213
DEP_TIME=060000

# 텔레그램 봇 (필수)
TELEGRAM_BOT_TOKEN=봇토큰
TELEGRAM_CHAT_ID=채팅ID

# 매크로 설정
REFRESH_INTERVAL_MIN=3
REFRESH_INTERVAL_MAX=10
MAX_ATTEMPTS=1000
```

### 텔레그램 봇 토큰 발급

1. 텔레그램에서 [@BotFather](https://t.me/BotFather) 대화 시작
2. `/newbot` 입력 → 이름/유저네임 설정 → **토큰** 복사
3. 생성된 봇에게 아무 메시지 전송
4. `https://api.telegram.org/bot<토큰>/getUpdates` 접속 → `chat.id` 확인
5. `.env`에 `TELEGRAM_BOT_TOKEN`과 `TELEGRAM_CHAT_ID` 입력

## 실행 방법

### 방법 1: 텔레그램 봇 (권장)

```bash
python bot.py
```

텔레그램에서 봇에게 `/start` 입력 후 **버튼만 클릭**하여 조작합니다.

#### 봇 사용 플로우

```
/start
  → 열차 선택: [🚄 SRT] [🚅 KTX]
  → 출발역 선택 (버튼 3열)
  → 도착역 선택 (출발역 제외)
  → 날짜 선택 (오늘~2주, 4열)
  → 시간대 선택 (새벽~야간, 2열)
  → 설정 확인: [✅ 시작] [🔄 다시] [❌ 취소]
  → 매크로 실행 중: [⏹ 중지] [📊 상태]
  → 예매 성공 시 알림 + 예약번호
```

#### 봇 명령어

| 명령어 | 설명 |
|--------|------|
| `/start` | 매크로 설정 시작 |
| `/stop` | 실행 중인 모든 매크로 중지 |
| `/status` | SRT/KTX 매크로 상태 확인 |

#### 동시 실행

SRT와 KTX 매크로를 동시에 실행할 수 있습니다. `/start`로 하나 설정 후 다시 `/start`로 다른 열차를 추가하세요.

### 방법 2: CLI 직접 실행

`.env`에 열차 조건을 설정한 뒤:

```bash
python srt_macro.py    # SRT
python ktx_macro.py    # KTX
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

## 보안

- `TELEGRAM_CHAT_ID`와 일치하는 사용자만 봇 명령 수락
- `.env` 파일은 `.gitignore`로 git 추적 제외
- 비밀번호는 로컬에만 저장

## 사용 라이브러리

- [SRTrain](https://github.com/ryanking13/SRT) — SRT API
- [korail2](https://github.com/carpedm20/korail2) — 코레일 API
- [python-telegram-bot](https://github.com/python-telegram-bot/python-telegram-bot) — 텔레그램 봇
- python-dotenv — 환경변수 관리
- requests — HTTP 요청
