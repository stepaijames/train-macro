import asyncio
import sys
import io
import threading
import time
import random
import logging
from datetime import datetime, timedelta

# Windows cp949 콘솔 인코딩 문제 해결
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ContextTypes,
)

from config import (
    TELEGRAM_BOT_TOKEN,
    TELEGRAM_CHAT_ID,
    SRT_ID,
    SRT_PW,
    KORAIL_ID,
    KORAIL_PW,
    CARD_NUMBER,
    CARD_PASSWORD,
    CARD_EXPIRE,
    CARD_BIRTH,
    CARD_INSTALLMENT,
    REFRESH_MIN,
    REFRESH_MAX,
    MAX_ATTEMPTS,
)

logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ════════════════════════════ 상수 ════════════════════════════

SRT_STATIONS = [
    "수서", "동탄", "평택지제", "천안아산", "오송", "대전",
    "김천구미", "동대구", "신경주", "울산", "부산",
    "공주", "익산", "정읍", "광주송정", "나주", "목포",
]

KTX_STATIONS = [
    "서울", "용산", "광명", "천안아산", "오송", "대전",
    "김천구미", "동대구", "경주", "울산", "부산", "밀양", "구포",
    "마산", "창원중앙", "진주", "익산", "정읍", "광주송정", "목포",
    "전주", "남원", "순천", "여수EXPO", "강릉", "동해", "원주",
]

TIME_SLOTS = [
    ("새벽 00~06", "000000"),
    ("오전 06~09", "060000"),
    ("오전 09~12", "090000"),
    ("오후 12~15", "120000"),
    ("오후 15~18", "150000"),
    ("저녁 18~21", "180000"),
    ("야간 21~24", "210000"),
]

ALL_TIME_CODES = [code for _, code in TIME_SLOTS]

# 각 시간대의 시작~끝 (HHMMSS)
TIME_RANGES = {
    "000000": (0, 6),
    "060000": (6, 9),
    "090000": (9, 12),
    "120000": (12, 15),
    "150000": (15, 18),
    "180000": (18, 21),
    "210000": (21, 24),
}

SEAT_OPTIONS = [
    ("전체 (일반+특실)", "all"),
    ("일반실만", "general_only"),
    ("특실만", "special_only"),
]

WEEKDAYS = ["월", "화", "수", "목", "금", "토", "일"]

# ════════════════════════════ 매크로 상태 ════════════════════════════

macros: dict[str, dict] = {}

# ════════════════════════════ 보안 ════════════════════════════


def authorized(update: Update) -> bool:
    chat_id = str(update.effective_chat.id)
    return not TELEGRAM_CHAT_ID or chat_id == TELEGRAM_CHAT_ID


async def deny(update: Update):
    if update.callback_query:
        await update.callback_query.answer("⛔ 권한 없음", show_alert=True)
    else:
        await update.message.reply_text("⛔ 권한이 없습니다.")


# ════════════════════════════ 헬퍼 ════════════════════════════


def grid_kb(items: list[str], cols: int, prefix: str) -> InlineKeyboardMarkup:
    btns = [InlineKeyboardButton(t, callback_data=f"{prefix}:{t}") for t in items]
    rows = [btns[i : i + cols] for i in range(0, len(btns), cols)]
    return InlineKeyboardMarkup(rows)


def fmt_date(d: datetime) -> str:
    return f"{d.month}/{d.day}({WEEKDAYS[d.weekday()]})"


def d2s(d: datetime) -> str:
    return d.strftime("%Y%m%d")


def seat_label_kr(code: str) -> str:
    m = {v: k for k, v in SEAT_OPTIONS}
    return m.get(code, code)


def has_card() -> bool:
    return bool(CARD_NUMBER and CARD_PASSWORD and CARD_EXPIRE)


def control_kb(key: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("⏹ 중지", callback_data=f"ctrl:stop:{key}"),
        InlineKeyboardButton("📊 상태", callback_data=f"ctrl:status:{key}"),
    ]])


def time_toggle_kb(selected: set, prefix: str) -> InlineKeyboardMarkup:
    """시간대 토글 키보드 생성. prefix: 'tg' (가는편) 또는 'tr' (오는편)"""
    all_on = selected == set(ALL_TIME_CODES)
    all_label = "✅ 전체 시간대" if all_on else "전체 시간대"
    rows = [[InlineKeyboardButton(all_label, callback_data=f"{prefix}all")]]
    slot_btns = []
    for label, code in TIME_SLOTS:
        mark = "✅ " if code in selected else ""
        slot_btns.append(InlineKeyboardButton(f"{mark}{label}", callback_data=f"{prefix}s:{code}"))
    rows += [slot_btns[i : i + 2] for i in range(0, len(slot_btns), 2)]
    rows.append([InlineKeyboardButton("선택 완료 →", callback_data=f"{prefix}done")])
    return InlineKeyboardMarkup(rows)


def times_summary(selected: set) -> str:
    """선택한 시간대를 요약 문자열로."""
    if selected == set(ALL_TIME_CODES):
        return "전체 (00~24시)"
    labels = []
    for label, code in TIME_SLOTS:
        if code in selected:
            labels.append(label)
    return ", ".join(labels) if labels else "미선택"


def train_in_time_ranges(dep_time_str: str, selected_codes: list[str]) -> bool:
    """열차 출발시각이 선택한 시간대 범위 안에 있는지 확인."""
    hh = int(dep_time_str[:2])
    for code in selected_codes:
        start_h, end_h = TIME_RANGES[code]
        if start_h <= hh < end_h:
            return True
    return False


# ════════════════════════════ /start ════════════════════════════


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not authorized(update):
        return await deny(update)
    context.user_data.clear()
    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("🚄 SRT", callback_data="train:srt"),
        InlineKeyboardButton("🚅 KTX", callback_data="train:ktx"),
    ]])
    await update.message.reply_text("🚆 열차를 선택하세요.", reply_markup=kb)


# ════════════════════════════ Step 1 → 열차 ════════════════════════════


async def cb_train(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if not authorized(update):
        return await deny(update)
    val = q.data.split(":")[1]
    context.user_data["train"] = val
    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("편도", callback_data="trip:oneway"),
        InlineKeyboardButton("왕복", callback_data="trip:round"),
    ]])
    label = "SRT" if val == "srt" else "KTX"
    await q.edit_message_text(f"🚄 {label} — 편도/왕복을 선택하세요.", reply_markup=kb)


# ════════════════════════════ Step 2 → 편도/왕복 ════════════════════════════


async def cb_trip(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if not authorized(update):
        return await deny(update)
    val = q.data.split(":")[1]
    context.user_data["trip"] = val
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton(f"{i}명", callback_data=f"pax:{i}") for i in range(1, 5)],
        [InlineKeyboardButton("5명+", callback_data="pax:5+")],
    ])
    await q.edit_message_text("👤 인원 수를 선택하세요.", reply_markup=kb)


# ════════════════════════════ Step 3 → 인원 ════════════════════════════


async def cb_pax(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if not authorized(update):
        return await deny(update)
    val = q.data.split(":")[1]
    if val == "5+":
        context.user_data["awaiting_pax"] = True
        await q.edit_message_text("🔢 몇 명인지 숫자를 입력해주세요.")
        return
    context.user_data["pax"] = int(val)
    await show_seat_selection(q, context)


async def msg_pax_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get("awaiting_pax"):
        return
    if not authorized(update):
        return await deny(update)
    text = update.message.text.strip()
    if not text.isdigit() or int(text) < 1 or int(text) > 9:
        await update.message.reply_text("1~9 사이 숫자를 입력해주세요.")
        return
    context.user_data["pax"] = int(text)
    context.user_data["awaiting_pax"] = False
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton(k, callback_data=f"seat:{v}") for k, v in SEAT_OPTIONS],
    ])
    await update.message.reply_text("💺 좌석 등급을 선택하세요.", reply_markup=kb)


async def show_seat_selection(q, context):
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton(k, callback_data=f"seat:{v}") for k, v in SEAT_OPTIONS],
    ])
    await q.edit_message_text("💺 좌석 등급을 선택하세요.", reply_markup=kb)


# ════════════════════════════ Step 4 → 좌석등급 ════════════════════════════


async def cb_seat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if not authorized(update):
        return await deny(update)
    val = q.data.split(":")[1]
    context.user_data["seat"] = val
    train = context.user_data["train"]
    stations = SRT_STATIONS if train == "srt" else KTX_STATIONS
    label = "SRT" if train == "srt" else "KTX"
    kb = grid_kb(stations, 3, "dep")
    await q.edit_message_text(f"🚉 {label} — 출발역을 선택하세요.", reply_markup=kb)


# ════════════════════════════ Step 5 → 출발역 ════════════════════════════


async def cb_dep(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if not authorized(update):
        return await deny(update)
    val = q.data.split(":")[1]
    context.user_data["dep"] = val
    train = context.user_data["train"]
    stations = SRT_STATIONS if train == "srt" else KTX_STATIONS
    filtered = [s for s in stations if s != val]
    kb = grid_kb(filtered, 3, "arr")
    await q.edit_message_text(f"출발역: {val}\n\n🏁 도착역을 선택하세요.", reply_markup=kb)


# ════════════════════════════ Step 6 → 도착역 ════════════════════════════


async def cb_arr(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if not authorized(update):
        return await deny(update)
    val = q.data.split(":")[1]
    context.user_data["arr"] = val
    trip = context.user_data["trip"]
    today = datetime.now()
    dates = [today + timedelta(days=i) for i in range(14)]
    btns = [InlineKeyboardButton(fmt_date(d), callback_data=f"date:{d2s(d)}") for d in dates]
    rows = [btns[i : i + 4] for i in range(0, len(btns), 4)]
    kb = InlineKeyboardMarkup(rows)
    header = "가는날을 선택하세요." if trip == "round" else "날짜를 선택하세요."
    dep = context.user_data["dep"]
    await q.edit_message_text(f"{dep} → {val}\n\n📅 {header}", reply_markup=kb)


# ════════════════════════════ Step 7 → 날짜 (가는날) ════════════════════════════


async def cb_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if not authorized(update):
        return await deny(update)
    val = q.data.split(":")[1]
    context.user_data["date_go"] = val
    trip = context.user_data["trip"]
    if trip == "round":
        go_date = datetime.strptime(val, "%Y%m%d")
        dates = [go_date + timedelta(days=i) for i in range(14)]
        btns = [InlineKeyboardButton(fmt_date(d), callback_data=f"rdate:{d2s(d)}") for d in dates]
        rows = [btns[i : i + 4] for i in range(0, len(btns), 4)]
        kb = InlineKeyboardMarkup(rows)
        d = datetime.strptime(val, "%Y%m%d")
        await q.edit_message_text(
            f"가는날: {d.strftime('%Y.%m.%d')} ({WEEKDAYS[d.weekday()]})\n\n📅 오는날을 선택하세요.",
            reply_markup=kb,
        )
    else:
        context.user_data["sel_tg"] = set()
        await show_time_go_kb(q, context)


# ════════════════════════════ Step 7-2 → 날짜 (오는날) ════════════════════════════


async def cb_rdate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if not authorized(update):
        return await deny(update)
    val = q.data.split(":")[1]
    context.user_data["date_ret"] = val
    context.user_data["sel_tg"] = set()
    await show_time_go_kb(q, context)


# ════════════════════════════ Step 8 → 시간 (가는편) 복수 선택 ════════════════════════════


async def show_time_go_kb(q, context):
    trip = context.user_data["trip"]
    selected = context.user_data.get("sel_tg", set())
    kb = time_toggle_kb(selected, "tg")
    header = "가는편 시간대" if trip == "round" else "시간대"
    cnt = len(selected)
    msg = f"🕐 {header}를 선택하세요. (복수 선택 가능)\n선택: {cnt}개"
    await q.edit_message_text(msg, reply_markup=kb)


async def cb_tgs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """가는편 개별 시간대 토글"""
    q = update.callback_query
    await q.answer()
    if not authorized(update):
        return await deny(update)
    code = q.data.split(":")[1]
    sel = context.user_data.setdefault("sel_tg", set())
    if code in sel:
        sel.discard(code)
    else:
        sel.add(code)
    await show_time_go_kb(q, context)


async def cb_tgall(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """가는편 전체 시간대 토글"""
    q = update.callback_query
    await q.answer()
    if not authorized(update):
        return await deny(update)
    sel = context.user_data.setdefault("sel_tg", set())
    if sel == set(ALL_TIME_CODES):
        sel.clear()
    else:
        sel.update(ALL_TIME_CODES)
    await show_time_go_kb(q, context)


async def cb_tgdone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """가는편 시간대 선택 완료"""
    q = update.callback_query
    if not authorized(update):
        await q.answer("⛔ 권한 없음", show_alert=True)
        return
    sel = context.user_data.get("sel_tg", set())
    if not sel:
        await q.answer("⚠️ 시간대를 1개 이상 선택하세요.", show_alert=True)
        return
    await q.answer()
    context.user_data["times_go"] = sorted(sel)
    trip = context.user_data["trip"]
    if trip == "round":
        context.user_data["sel_tr"] = set()
        await show_time_ret_kb(q, context)
    else:
        await show_confirm(q, context)


# ════════════════════════════ Step 8-2 → 시간 (오는편) 복수 선택 ════════════════════════════


async def show_time_ret_kb(q, context):
    selected = context.user_data.get("sel_tr", set())
    kb = time_toggle_kb(selected, "tr")
    cnt = len(selected)
    await q.edit_message_text(f"🕐 오는편 시간대를 선택하세요. (복수 선택 가능)\n선택: {cnt}개", reply_markup=kb)


async def cb_trs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if not authorized(update):
        return await deny(update)
    code = q.data.split(":")[1]
    sel = context.user_data.setdefault("sel_tr", set())
    if code in sel:
        sel.discard(code)
    else:
        sel.add(code)
    await show_time_ret_kb(q, context)


async def cb_trall(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if not authorized(update):
        return await deny(update)
    sel = context.user_data.setdefault("sel_tr", set())
    if sel == set(ALL_TIME_CODES):
        sel.clear()
    else:
        sel.update(ALL_TIME_CODES)
    await show_time_ret_kb(q, context)


async def cb_trdone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not authorized(update):
        await q.answer("⛔ 권한 없음", show_alert=True)
        return
    sel = context.user_data.get("sel_tr", set())
    if not sel:
        await q.answer("⚠️ 시간대를 1개 이상 선택하세요.", show_alert=True)
        return
    await q.answer()
    context.user_data["times_ret"] = sorted(sel)
    await show_confirm(q, context)


# ════════════════════════════ Step 9 → 확인 ════════════════════════════


async def show_confirm(q, context):
    ud = context.user_data
    train = ud["train"]
    trip = ud["trip"]
    pax = ud["pax"]
    seat = ud["seat"]
    dep = ud["dep"]
    arr = ud["arr"]
    date_go = ud["date_go"]
    times_go = ud["times_go"]

    label = "SRT" if train == "srt" else "KTX"
    emoji = "🚄" if train == "srt" else "🚅"
    trip_kr = "편도" if trip == "oneway" else "왕복"
    d_go = datetime.strptime(date_go, "%Y%m%d")

    card_info = ""
    if train == "srt" and has_card():
        card_info = "\n💳 자동결제: ON"
    elif train == "srt":
        card_info = "\n💳 자동결제: OFF (카드 미설정)"
    else:
        card_info = "\n💳 결제: 앱에서 수동결제"

    lines = [
        f"{emoji} <b>{label} 매크로 설정</b>",
        "━━━━━━━━━━━━━",
        f"🔹 {trip_kr} | {pax}명 | {seat_label_kr(seat)}",
        f"🔹 {dep} → {arr}",
        f"🔹 {d_go.strftime('%Y.%m.%d')} ({WEEKDAYS[d_go.weekday()]})",
        f"🔹 시간: {times_summary(set(times_go))}",
    ]

    if trip == "round":
        date_ret = ud["date_ret"]
        times_ret = ud["times_ret"]
        d_ret = datetime.strptime(date_ret, "%Y%m%d")
        lines.append(f"🔹 오는편: {d_ret.strftime('%Y.%m.%d')} ({WEEKDAYS[d_ret.weekday()]})")
        lines.append(f"🔹 오는편 시간: {times_summary(set(times_ret))}")

    lines.append(card_info)
    lines.append("\n시작할까요?")

    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ 시작", callback_data="cfm:yes"),
        InlineKeyboardButton("🔄 다시 선택", callback_data="cfm:restart"),
        InlineKeyboardButton("❌ 취소", callback_data="cfm:cancel"),
    ]])
    await q.edit_message_text("\n".join(lines), reply_markup=kb, parse_mode="HTML")


# ════════════════════════════ 확인 처리 ════════════════════════════


async def cb_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if not authorized(update):
        return await deny(update)

    action = q.data.split(":")[1]

    if action == "cancel":
        await q.edit_message_text("❌ 취소되었습니다.")
        return

    if action == "restart":
        context.user_data.clear()
        kb = InlineKeyboardMarkup([[
            InlineKeyboardButton("🚄 SRT", callback_data="train:srt"),
            InlineKeyboardButton("🚅 KTX", callback_data="train:ktx"),
        ]])
        await q.edit_message_text("🚆 열차를 선택하세요.", reply_markup=kb)
        return

    # yes → 매크로 시작
    ud = context.user_data
    train = ud["train"]
    trip = ud["trip"]
    label = train.upper()
    go_key = f"{train}_go"

    if go_key in macros and macros[go_key].get("running"):
        await q.edit_message_text(f"⚠️ {label} 가는편 매크로가 이미 실행 중입니다.")
        return

    chat_id = update.effective_chat.id
    app = context.application

    go_state = _build_state(ud, "go")
    macros[go_key] = go_state
    threading.Thread(target=run_macro, args=(app, chat_id, go_state), daemon=True).start()

    msg = f"🚀 {label} 가는편 매크로 시작!\n{ud['dep']} → {ud['arr']}"

    if trip == "round":
        ret_key = f"{train}_ret"
        ret_state = _build_state(ud, "ret")
        macros[ret_key] = ret_state
        threading.Thread(target=run_macro, args=(app, chat_id, ret_state), daemon=True).start()
        msg += f"\n🚀 {label} 오는편 매크로 시작!\n{ud['arr']} → {ud['dep']}"

    kb = control_kb(go_key)
    await q.edit_message_text(msg, reply_markup=kb)


def _build_state(ud: dict, direction: str) -> dict:
    train = ud["train"]
    if direction == "go":
        dep, arr = ud["dep"], ud["arr"]
        date_str = ud["date_go"]
        time_codes = ud["times_go"]
    else:
        dep, arr = ud["arr"], ud["dep"]
        date_str = ud["date_ret"]
        time_codes = ud["times_ret"]

    return {
        "running": True,
        "train": train,
        "direction": direction,
        "dep": dep,
        "arr": arr,
        "date": date_str,
        "time_codes": time_codes,       # 복수 시간대
        "search_time": min(time_codes),  # API 조회용 (가장 이른 시간)
        "pax": ud["pax"],
        "seat": ud["seat"],
        "attempt": 0,
        "key": f"{train}_{direction}",
    }


# ════════════════════════════ 매크로 실행 (스레드) ════════════════════════════


def run_macro(app: Application, chat_id: int, state: dict):
    train = state["train"]
    dep = state["dep"]
    arr = state["arr"]
    date_str = state["date"]
    search_time = state["search_time"]
    time_codes = state["time_codes"]
    pax = state["pax"]
    seat_code = state["seat"]
    direction = state["direction"]
    key = state["key"]
    label = train.upper()
    dir_kr = "가는편" if direction == "go" else "오는편"
    tag = f"[{label} {dir_kr}]"

    # ── 로그인 헬퍼 ──
    def do_login():
        if train == "srt":
            from SRT import SRT
            return SRT(SRT_ID, SRT_PW)
        else:
            from korail2 import Korail
            return Korail(KORAIL_ID, KORAIL_PW)

    # ── 초기 로그인 ──
    try:
        client = do_login()
    except Exception as e:
        _send(app, chat_id, f"❌ {tag} 로그인 실패: {e}")
        state["running"] = False
        return

    # 좌석 타입 설정
    if train == "srt":
        from SRT.seat_type import SeatType
        from SRT.passenger import Adult
        seat_map = {"all": SeatType.GENERAL_FIRST, "general_only": SeatType.GENERAL_ONLY, "special_only": SeatType.SPECIAL_ONLY}
        seat_type = seat_map.get(seat_code, SeatType.GENERAL_FIRST)
    else:
        from korail2 import AdultPassenger, ReserveOption
        seat_map = {"all": ReserveOption.GENERAL_FIRST, "general_only": ReserveOption.GENERAL_ONLY, "special_only": ReserveOption.SPECIAL_ONLY}
        seat_type = seat_map.get(seat_code, ReserveOption.GENERAL_FIRST)

    time_desc = times_summary(set(time_codes))
    _send(app, chat_id, f"✅ {tag} 로그인 성공\n{dep}→{arr} | {time_desc}\n조회 시작!", reply_markup=control_kb(key))

    last_login = time.time()
    LOGIN_REFRESH = 1800  # 30분마다 세션 갱신

    # ── 반복 조회 ──
    for attempt in range(1, MAX_ATTEMPTS + 1):
        if not state["running"]:
            _send(app, chat_id, f"⏹ {tag} 매크로 중지됨 (#{attempt})")
            return

        state["attempt"] = attempt

        # ── 세션 갱신 (30분마다) ──
        if time.time() - last_login > LOGIN_REFRESH:
            try:
                client = do_login()
                last_login = time.time()
                logger.info(f"{tag} 세션 갱신 완료")
            except Exception as e:
                logger.warning(f"{tag} 세션 갱신 실패: {e}")

        # ── 열차 조회 ──
        try:
            if train == "srt":
                trains = client.search_train(dep, arr, date_str, search_time)
            else:
                trains = client.search_train(dep, arr, date_str, search_time, passengers=[AdultPassenger(pax)])
        except Exception as e:
            err_name = type(e).__name__

            # 세션 만료 → 즉시 재로그인
            if "NeedToLogin" in err_name:
                logger.info(f"{tag} 세션 만료 → 재로그인")
                try:
                    client = do_login()
                    last_login = time.time()
                except Exception as le:
                    _send(app, chat_id, f"❌ {tag} 재로그인 실패: {le}")
                    state["running"] = False
                    return
                continue

            # 매진 (정상) → 빠르게 재시도
            if "NoResult" in err_name or "SoldOut" in err_name:
                if attempt % 50 == 0:
                    _send(app, chat_id, f"🔄 {tag} [{attempt}/{MAX_ATTEMPTS}] 매진 — 취소표 대기 중...", reply_markup=control_kb(key))
                if not _sleep(state, random.uniform(REFRESH_MIN, REFRESH_MAX)):
                    _send(app, chat_id, f"⏹ {tag} 매크로 중지됨 (#{attempt})")
                    return
                continue

            # 기타 에러
            logger.warning(f"{tag} 조회 에러 #{attempt}: {e}")
            if not _sleep(state, REFRESH_MAX):
                _send(app, chat_id, f"⏹ {tag} 매크로 중지됨 (#{attempt})")
                return
            continue

        # ── 열차별 좌석 확인 ──
        for t in trains:
            dep_time_str = t.dep_time
            if not train_in_time_ranges(dep_time_str, time_codes):
                continue

            # 좌석 체크
            if train == "srt":
                if seat_code == "general_only":
                    available = t.general_seat_available()
                elif seat_code == "special_only":
                    available = t.special_seat_available()
                else:
                    available = t.general_seat_available() or t.special_seat_available()
            else:
                if seat_code == "general_only":
                    available = t.has_general_seat()
                elif seat_code == "special_only":
                    available = t.has_special_seat()
                else:
                    available = t.has_general_seat() or t.has_special_seat()

            if not available:
                continue

            # ── 예약 시도 ──
            try:
                if train == "srt":
                    reservation = client.reserve(t, passengers=[Adult(pax)], special_seat=seat_type)
                    res_num = reservation.reservation_number
                    hh_dep = f"{t.dep_time[:2]}:{t.dep_time[2:4]}"
                    hh_arr = f"{t.arr_time[:2]}:{t.arr_time[2:4]}"

                    if has_card():
                        try:
                            client.pay_with_card(
                                reservation,
                                number=CARD_NUMBER, password=CARD_PASSWORD,
                                validation_number=CARD_BIRTH, expire_date=CARD_EXPIRE,
                                installment=CARD_INSTALLMENT, card_type="J",
                            )
                            _send(app, chat_id,
                                f"🎉 예약+결제 성공!\n\n{tag} {dep} → {arr}\n"
                                f"출발: {hh_dep} → 도착: {hh_arr}\n예약번호: {res_num}\n💳 카드결제 완료!")
                        except Exception as pe:
                            _send(app, chat_id,
                                f"✅ 예약 성공! ⚠️ 자동결제 실패\n\n{tag} {dep} → {arr}\n"
                                f"출발: {hh_dep}\n예약번호: {res_num}\n결제오류: {pe}\n\n"
                                f"⚠️ <b>앱에서 수동 결제하세요!</b>", parse_mode="HTML")
                            for i in range(10):
                                if not _sleep(state, 30):
                                    break
                                _send(app, chat_id, f"🔔 [{i+1}/10] 미결제 알림! 예약번호 {res_num} — 앱에서 결제하세요!")
                    else:
                        _send(app, chat_id,
                            f"✅ 예약 성공!\n\n{tag} {dep} → {arr}\n"
                            f"출발: {hh_dep}\n예약번호: {res_num}\n\n"
                            f"⚠️ <b>SRT 앱에서 결제하세요!</b>", parse_mode="HTML")
                else:
                    reservation = client.reserve(t, passengers=[AdultPassenger(pax)], option=seat_type)
                    res_num = reservation.reservation_number
                    hh_dep = f"{t.dep_time[:2]}:{t.dep_time[2:4]}"
                    _send(app, chat_id,
                        f"✅ 예약 성공!\n\n{tag} {dep} → {arr}\n"
                        f"출발: {hh_dep}\n예약번호: {res_num}\n\n"
                        f"⚠️ <b>코레일 앱에서 결제하세요!</b>", parse_mode="HTML")

                state["running"] = False
                return

            except Exception as e:
                logger.warning(f"{tag} 예매 실패: {e}")

        # 진행 상태 알림
        if attempt % 50 == 0:
            elapsed = int(time.time() - last_login) // 60
            _send(app, chat_id, f"🔄 {tag} [{attempt}/{MAX_ATTEMPTS}] 조회 중... ({elapsed}분 경과)", reply_markup=control_kb(key))

        if not _sleep(state, random.uniform(REFRESH_MIN, REFRESH_MAX)):
            _send(app, chat_id, f"⏹ {tag} 매크로 중지됨 (#{attempt})")
            return

    _send(app, chat_id, f"😞 {tag} {MAX_ATTEMPTS}회 조회 완료 — 예매 실패")
    state["running"] = False


def _send(app, chat_id, text, parse_mode=None, reply_markup=None):
    """논블로킹 메시지 전송 — 스레드를 멈추지 않음"""
    try:
        asyncio.run_coroutine_threadsafe(
            app.bot.send_message(
                chat_id=chat_id, text=text,
                parse_mode=parse_mode, reply_markup=reply_markup,
            ),
            app.loop,
        )
    except Exception as e:
        logger.warning(f"메시지 전송 실패: {e}")


def _sleep(state: dict, seconds: float) -> bool:
    """중지 가능한 슬립 — 0.3초마다 running 플래그 체크. 중지 시 False 반환."""
    elapsed = 0.0
    while elapsed < seconds:
        if not state["running"]:
            return False
        time.sleep(0.3)
        elapsed += 0.3
    return True


# ════════════════════════════ 실행 중 제어 ════════════════════════════


async def cb_ctrl(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not authorized(update):
        await q.answer("⛔ 권한 없음", show_alert=True)
        return

    parts = q.data.split(":")
    action, key = parts[1], parts[2]

    if action == "stop":
        await q.answer()
        stopped = []
        train = key.split("_")[0]
        for k in [f"{train}_go", f"{train}_ret"]:
            if k in macros and macros[k].get("running"):
                macros[k]["running"] = False
                stopped.append(k)
        if stopped:
            kb = InlineKeyboardMarkup([[
                InlineKeyboardButton("🚄 SRT 새로 시작", callback_data="train:srt"),
                InlineKeyboardButton("🚅 KTX 새로 시작", callback_data="train:ktx"),
            ]])
            await q.edit_message_text(f"⏹ 중지됨: {', '.join(stopped)}", reply_markup=kb)
        else:
            await q.edit_message_text("ℹ️ 실행 중인 매크로가 없습니다.")

    elif action == "status":
        lines = []
        for k, s in macros.items():
            if s.get("running"):
                dir_kr = "가는편" if s["direction"] == "go" else "오는편"
                lines.append(f"🟢 {s['train'].upper()} {dir_kr}: {s['dep']}→{s['arr']} #{s['attempt']}/{MAX_ATTEMPTS}")
        if not lines:
            lines.append("ℹ️ 실행 중인 매크로 없음")
        await q.answer("\n".join(lines), show_alert=True)


# ════════════════════════════ /stop ════════════════════════════


async def cmd_stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not authorized(update):
        return await deny(update)
    stopped = []
    for k in list(macros.keys()):
        if macros[k].get("running"):
            macros[k]["running"] = False
            stopped.append(k)
    if stopped:
        await update.message.reply_text(f"⏹ 중지됨: {', '.join(stopped)}")
    else:
        await update.message.reply_text("ℹ️ 실행 중인 매크로가 없습니다.")


# ════════════════════════════ /status ════════════════════════════


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not authorized(update):
        return await deny(update)
    lines = []
    for k, s in macros.items():
        if s.get("running"):
            dir_kr = "가는편" if s["direction"] == "go" else "오는편"
            lines.append(f"🟢 {s['train'].upper()} {dir_kr}: {s['dep']}→{s['arr']} | #{s['attempt']}/{MAX_ATTEMPTS}")
        else:
            lines.append(f"⚪ {k}: 종료")
    if not lines:
        lines.append("ℹ️ 매크로 없음")
    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("🚄 SRT 새로 시작", callback_data="train:srt"),
        InlineKeyboardButton("🚅 KTX 새로 시작", callback_data="train:ktx"),
    ]])
    await update.message.reply_text("\n".join(lines), reply_markup=kb)


# ════════════════════════════ 메인 ════════════════════════════


async def post_init(application: Application):
    """run_polling 내부의 실제 이벤트 루프를 저장 (백그라운드 스레드용)"""
    application.loop = asyncio.get_running_loop()


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    """핸들러 예외를 로그로 출력"""
    logger.error("핸들러 예외 발생:", exc_info=context.error)


def main():
    if not TELEGRAM_BOT_TOKEN:
        print("[오류] .env에 TELEGRAM_BOT_TOKEN을 입력하세요.")
        return

    app = (
        Application.builder()
        .token(TELEGRAM_BOT_TOKEN)
        .post_init(post_init)
        .build()
    )

    # 에러 핸들러
    app.add_error_handler(error_handler)

    # 명령어
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("stop", cmd_stop))
    app.add_handler(CommandHandler("status", cmd_status))

    # 인원 수 텍스트 입력 (5명+)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, msg_pax_input))

    # 콜백 라우팅
    app.add_handler(CallbackQueryHandler(cb_train, pattern=r"^train:"))
    app.add_handler(CallbackQueryHandler(cb_trip, pattern=r"^trip:"))
    app.add_handler(CallbackQueryHandler(cb_pax, pattern=r"^pax:"))
    app.add_handler(CallbackQueryHandler(cb_seat, pattern=r"^seat:"))
    app.add_handler(CallbackQueryHandler(cb_dep, pattern=r"^dep:"))
    app.add_handler(CallbackQueryHandler(cb_arr, pattern=r"^arr:"))
    app.add_handler(CallbackQueryHandler(cb_date, pattern=r"^date:"))
    app.add_handler(CallbackQueryHandler(cb_rdate, pattern=r"^rdate:"))
    # 시간대 토글 — 가는편
    app.add_handler(CallbackQueryHandler(cb_tgs, pattern=r"^tgs:"))
    app.add_handler(CallbackQueryHandler(cb_tgall, pattern=r"^tgall$"))
    app.add_handler(CallbackQueryHandler(cb_tgdone, pattern=r"^tgdone$"))
    # 시간대 토글 — 오는편
    app.add_handler(CallbackQueryHandler(cb_trs, pattern=r"^trs:"))
    app.add_handler(CallbackQueryHandler(cb_trall, pattern=r"^trall$"))
    app.add_handler(CallbackQueryHandler(cb_trdone, pattern=r"^trdone$"))
    # 확인/제어
    app.add_handler(CallbackQueryHandler(cb_confirm, pattern=r"^cfm:"))
    app.add_handler(CallbackQueryHandler(cb_ctrl, pattern=r"^ctrl:"))

    print("🤖 텔레그램 봇 시작...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
