import os
from dotenv import load_dotenv

load_dotenv(encoding="utf-8")

SRT_ID = os.getenv("SRT_ID")
SRT_PW = os.getenv("SRT_PW")
KORAIL_ID = os.getenv("KORAIL_ID")
KORAIL_PW = os.getenv("KORAIL_PW")
DEP_STATION = os.getenv("DEP_STATION", "수서")
ARR_STATION = os.getenv("ARR_STATION", "부산")
DEP_DATE = os.getenv("DEP_DATE")
DEP_TIME = os.getenv("DEP_TIME", "060000")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
CARD_NUMBER = os.getenv("CARD_NUMBER")
CARD_PASSWORD = os.getenv("CARD_PASSWORD")
CARD_EXPIRE = os.getenv("CARD_EXPIRE")
CARD_BIRTH = os.getenv("CARD_BIRTH", "")
CARD_INSTALLMENT = int(os.getenv("CARD_INSTALLMENT", 0))
REFRESH_MIN = int(os.getenv("REFRESH_INTERVAL_MIN", 3))
REFRESH_MAX = int(os.getenv("REFRESH_INTERVAL_MAX", 10))
MAX_ATTEMPTS = int(os.getenv("MAX_ATTEMPTS", 1000))
