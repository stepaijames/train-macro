import time
import random
import sys
from korail2 import Korail, AdultPassenger
from config import (
    KORAIL_ID, KORAIL_PW, DEP_STATION, ARR_STATION,
    DEP_DATE, DEP_TIME, REFRESH_MIN, REFRESH_MAX, MAX_ATTEMPTS,
)
from notify import send_telegram


def main():
    if not KORAIL_ID or not KORAIL_PW:
        print("[오류] .env 파일에 KORAIL_ID, KORAIL_PW를 입력하세요.")
        sys.exit(1)
    if not DEP_DATE:
        print("[오류] .env 파일에 DEP_DATE를 입력하세요.")
        sys.exit(1)

    print(f"[KTX] 로그인 중... (ID: {KORAIL_ID[:3]}***)")
    korail = Korail(KORAIL_ID, KORAIL_PW)
    print("[KTX] 로그인 성공")
    print(f"[KTX] {DEP_STATION} → {ARR_STATION} | {DEP_DATE} | {DEP_TIME} 이후")
    print(f"[KTX] 조회 간격: {REFRESH_MIN}~{REFRESH_MAX}초 | 최대 {MAX_ATTEMPTS}회\n")

    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            trains = korail.search_train(DEP_STATION, ARR_STATION, DEP_DATE, DEP_TIME)
        except Exception as e:
            print(f"\n[조회 실패] {e}")
            time.sleep(REFRESH_MAX)
            continue

        for train in trains:
            if train.has_general_seat():
                print(f"\n\n[빈 좌석 발견!] {train}")
                try:
                    reservation = korail.reserve(train, passengers=[AdultPassenger()])
                    msg = (
                        f"🚄 KTX 예매 성공!\n"
                        f"{train.dep_name} → {train.arr_name}\n"
                        f"{train.dep_date} {train.dep_time}\n"
                        f"예약번호: {reservation.reservation_number}"
                    )
                    print(msg)
                    send_telegram(msg)
                    return
                except Exception as e:
                    print(f"[예매 실패] {e}")

        interval = random.uniform(REFRESH_MIN, REFRESH_MAX)
        sys.stdout.write(f"\r[KTX] 조회 #{attempt}/{MAX_ATTEMPTS} — 빈 좌석 없음 ({interval:.1f}초 대기)")
        sys.stdout.flush()
        time.sleep(interval)

    print(f"\n[KTX] {MAX_ATTEMPTS}회 조회 완료 — 예매 실패")
    send_telegram(f"KTX 매크로 종료: {MAX_ATTEMPTS}회 조회 후 예매 실패")


if __name__ == "__main__":
    main()
