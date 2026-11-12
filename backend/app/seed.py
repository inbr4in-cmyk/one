"""Reference data every installation needs (roles, funnels, templates, settings) + optional demo data."""

import asyncio
import sys
from datetime import UTC, date, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.permissions import DEFAULT_ROLES
from app.core.security import hash_password
from app.models import (
    Branch,
    ExpenseCategory,
    LeadStage,
    Level,
    MessageTemplate,
    Pipeline,
    RateSetting,
    Role,
    RolePermission,
    Room,
    Setting,
    User,
    UserBranch,
    UserRole,
)
from app.models.identity import UserKind

MAIN_STAGES = [
    ("new", "Новая заявка", "#1A6FD1", False, False, 1),
    ("contacted", "Связались", "#7B52C7", False, False, 24),
    ("trial_booked", "Записан на пробный", "#C98A06", False, False, None),
    ("trial_done", "Пришёл на пробный", "#0E8FA8", False, False, 24),
    ("paid", "Оплатил", "#1E8E5A", True, False, None),
    ("lost", "Отказ", "#5B6782", False, True, None),
]
RETURN_STAGES = [
    ("left", "Ушёл", "#5B6782", False, False, 72),
    ("contacted", "Связались", "#7B52C7", False, False, 72),
    ("agreed", "Договорились", "#C98A06", False, False, None),
    ("paid", "Оплатил", "#1E8E5A", True, False, None),
    ("lost", "Отказ", "#5B6782", False, True, None),
]

# ТЗ 7.2 templates. Variables: {name} {date} {time} {group} {amount} {lessons} {left} {reason} {book}
TEMPLATES = {
    "absence": (
        "Здравствуйте! {name} не пришёл(а) на занятие сегодня в {time}, группа {group}. One English",
        "Сәлеметсіз бе! {name} бүгін {time} сабаққа келмеді, топ {group}. One English",
    ),
    "present": ("{name} пришёл(а) на занятие в {time}, группа {group}. One English",
                "{name} {time} сабаққа келді, топ {group}. One English"),
    "late": ("{name} опоздал(а) на занятие в {time}, группа {group}. One English",
             "{name} {time} сабаққа кешікті, топ {group}. One English"),
    "payment": (
        "Оплата принята: {amount} тг за {what}. Оплачено уроков: {lessons}. Осталось уроков: {left}. Спасибо! One English",
        "Төлем қабылданды: {amount} тг, {what}. Төленген сабақтар: {lessons}. Қалған сабақтар: {left}. Рақмет! One English",
    ),
    "pay_reminder": (
        "Здравствуйте! У {name} осталось {left} урок(а). Пожалуйста, внесите оплату до следующего занятия. One English",
        "Сәлеметсіз бе! {name} үшін {left} сабақ қалды. Келесі сабаққа дейін төлем жасауыңызды сұраймыз. One English",
    ),
    "lesson_cancel": ("Занятие группы {group} {date} в {time} отменено. Причина: {reason}. One English",
                      "{group} тобының {date} {time} сабағы болмайды. Себебі: {reason}. One English"),
    "lesson_move": ("Занятие группы {group} перенесено на {date} в {time}. Причина: {reason}. One English",
                    "{group} тобының сабағы {date} {time} уақытына ауыстырылды. Себебі: {reason}. One English"),
    "followup": ("Здравствуйте, {name}! Это One English. Вы интересовались курсами английского — вопрос ещё актуален? "
                 "Ответим на вопросы и запишем на бесплатный пробный урок.",
                 "Сәлеметсіз бе, {name}! Бұл One English. Сіз ағылшын тілі курстарына қызығушылық танытқан едіңіз — "
                 "сұрақтарыңызға жауап беріп, тегін сынақ сабағына жазамыз."),
    "book_sale": ("{name}: покупка книги «{book}» на {amount} тг подтверждена. One English",
                  "{name}: «{book}» кітабын {amount} тг сатып алу расталды. One English"),
}

DEFAULT_SETTINGS = {
    "charge_unexcused_absence": True,
    "charge_late": True,
    "low_balance_lessons": 2,
    "left_after_days": 90,
    "attendance_teacher_window": "same_day",
    "attendance_reminder_min": 10,
    "attendance_admin_alert_min": 30,
    "notify_present": False,
    "notify_late": False,
    "lead_first_reply_warn_min": 30,
    "lead_stale_hours": 1,
    "trial_counts_in_n": True,
    "nonpayment_block_days": 5,
    "freeze_max_days": 31,
    "freeze_max_per_course": 1,
    # Rules p.362: freezing needs a month prepaid. 12 = 3 lessons a week × 4 weeks (all default levels have 3–4).
    "freeze_prepaid_lessons": 12,
    "absence_notice_hours": 3,
    "coins": {"attendance": 5, "homework": 5, "perfect_month": 50, "final_test": 100, "birthday": 50, "referral": 200},
}

RATES = {
    "teacher_lesson_base": 2500,
    "teacher_extra_per_student": 100,
    "teacher_extra_threshold": 5,
    "teacher_individual_lesson": 2000,
    "teacher_duo_lesson": 2500,
    "teacher_support_lesson": 1000,
    "teacher_club_lesson": 8000,
    "teacher_trial_retention": 500,
    "teacher_final_test_bonus": 1000,
    "final_test_bonus_threshold": 100,
    "sales_trial_visit": 2000,
    "sales_return": 2000,
    "office_sale": 2000,
}

EXPENSE_CATEGORIES = [
    ("rent", "Аренда"), ("salary", "Зарплата"), ("ads", "Реклама"), ("utilities", "Коммунальные"),
    ("materials", "Учебные материалы"), ("books", "Закупка книг"), ("shop", "Товары для магазина коинов"),
    ("taxes", "Налоги"), ("other", "Прочее"),
]

# Roadmaps from the project files: kids Family & Friends 1–4, adults Beginner → Upper-Intermediate, IELTS.
LEVELS = [
    ("FF1", "Family & Friends 1", "kids", 2500, "#0E8FA8", 3), ("FF2", "Family & Friends 2", "kids", 2500, "#0E8FA8", 3),
    ("FF3", "Family & Friends 3", "kids", 2800, "#0E8FA8", 3), ("FF4", "Family & Friends 4", "kids", 2800, "#0E8FA8", 3),
    ("BEG", "Beginner", "adults", 3000, "#2E9A6E", 3), ("ELE", "Elementary", "adults", 3000, "#1A6FD1", 3),
    ("PRE", "Pre-Intermediate", "adults", 3500, "#C9631A", 4), ("INT", "Intermediate", "adults", 4000, "#7B52C7", 4),
    ("UPP", "Upper-Intermediate", "adults", 4000, "#B08900", 4), ("IELTS", "IELTS", "exam", 5000, "#C2417F", 3),
]


async def seed_base(db: AsyncSession) -> None:
    if await db.scalar(select(Role).limit(1)):
        return
    for code, spec in DEFAULT_ROLES.items():
        role = Role(code=code, name=spec["name"], is_system=spec.get("system", False), coin_limit=spec.get("coin_limit", 0))
        role.permissions = [RolePermission(module=m, action=a, scope=s) for m, a, s in spec["perms"]]
        db.add(role)
    for code, name, stages in (("main", "Основная воронка", MAIN_STAGES), ("return", "Возврат", RETURN_STAGES)):
        p = Pipeline(code=code, name=name)
        db.add(p)
        await db.flush()
        for i, (sc, sn, color, won, lost, stale) in enumerate(stages):
            db.add(LeadStage(pipeline_id=p.id, code=sc, name=sn, color=color, order=i, is_won=won, is_lost=lost,
                             stale_after_hours=stale))
    for code, (ru, kk) in TEMPLATES.items():
        db.add(MessageTemplate(code=code, locale="ru", body=ru, enabled=code not in ("present", "late")))
        db.add(MessageTemplate(code=code, locale="kk", body=kk, enabled=code not in ("present", "late")))
    for k, v in DEFAULT_SETTINGS.items():
        db.add(Setting(key=k, value={"v": v}))
    for k, v in RATES.items():
        db.add(RateSetting(key=k, value=v, effective_from=date(2026, 1, 1)))
    for code, name in EXPENSE_CATEGORIES:
        db.add(ExpenseCategory(code=code, name=name))
    prev: Level | None = None
    for i, (code, name, track, price, color, months) in enumerate(LEVELS):
        lvl = Level(code=code, name=name, track=track, lesson_price=price, color=color, order=i,
                    duration_months=months, is_kids=track == "kids")
        db.add(lvl)
        await db.flush()
        if prev is not None and prev.track == track:
            prev.next_level_id = lvl.id
        prev = lvl
    await db.flush()


async def create_owner(db: AsyncSession, phone: str, name: str, password: str) -> User:
    owner_role = await db.scalar(select(Role).where(Role.code == "owner"))
    u = User(kind=UserKind.STAFF, full_name=name, phone=phone, password_hash=hash_password(password), position="Владелец")
    db.add(u)
    await db.flush()
    db.add(UserRole(user_id=u.id, role_id=owner_role.id))
    for b in await db.scalars(select(Branch)):
        db.add(UserBranch(user_id=u.id, branch_id=b.id))
    return u


async def seed_branches(db: AsyncSession) -> list[Branch]:
    existing = list(await db.scalars(select(Branch)))
    if existing:
        return existing
    out = []
    for name, addr, rooms in (
        ("Янги шахар", "Тамерлановское шоссе 3/4", ["Каб. 1", "Каб. 2", "Каб. 3", "Каб. 4"]),
        ("Север", "ул. Рыскулова 72/8", ["Каб. 1", "Каб. 2", "Каб. 3"]),
    ):
        b = Branch(name=name, address=addr, phone="+77000000000", hours="09:00–21:00")
        db.add(b)
        await db.flush()
        for i, r in enumerate(rooms):
            db.add(Room(branch_id=b.id, name=r, capacity=12 if i < 2 else 8))
        out.append(b)
    return out


async def main() -> None:
    from app.core.db import SessionLocal

    async with SessionLocal() as db:
        await seed_base(db)
        await seed_branches(db)
        if "--owner" in sys.argv:
            # python -m app.seed --owner +77010000001 "Имя Фамилия" — the password is typed, never passed in argv.
            import getpass

            i = sys.argv.index("--owner")
            phone, name = sys.argv[i + 1], sys.argv[i + 2]
            if await db.scalar(select(User).where(User.phone == phone)):
                sys.exit(f"user {phone} already exists")
            pw = getpass.getpass("Пароль владельца (от 10 символов): ")
            if len(pw) < 10 or pw != getpass.getpass("Ещё раз: "):
                sys.exit("пароли не совпадают или короче 10 символов")
            await create_owner(db, phone, name, pw)
        if "--demo" in sys.argv:
            from app.demo import seed_demo

            await seed_demo(db)
        await db.commit()
    print("seeded at", datetime.now(UTC).isoformat())


if __name__ == "__main__":
    asyncio.run(main())
