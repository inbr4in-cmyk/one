"""Demo data for local runs and showing the platform: `python -m app.seed --demo`. Refuses to run in production."""

import random
from datetime import time, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.security import hash_password
from app.models import (
    Attendance, Book, BookStock, Branch, Chat, ChatMessage, DocumentVersion, Group, GroupMember, Homework, Lesson, Level,
    Payment, Role, Room, ScheduleRule, ShopItem, Student, StudentGuardian, Task, TaskAssignee, User, UserBranch, UserRole,
)
from app.models.identity import UserKind
from app.models.learning import AttendanceStatus, LessonStatus
from app.modules.academics.schedule import generate
from app.modules.crm.service import create_lead
from app.modules.inbox.service import receive
from app.modules.students.router import upsert_portal_user
from app.seed import create_owner
from app.services import balance as bal
from app.services import chats
from app.services.clock import at_local, local, now, today
from app.services.payroll import accrue_lesson

DEMO_PASSWORD = "Demo-pass-2026"
FEMALE = ["Алия", "Мадина", "Дана", "Айша", "Жанель", "Камила", "Амина", "Томирис", "Аружан", "Сабина"]
MALE = ["Тимур", "Арман", "Ерлан", "Нурсултан", "Санжар", "Алихан", "Данияр", "Ислам", "Бекзат", "Әли"]
FIRST = FEMALE + MALE
LAST = ["Нурлан", "Ахмет", "Сеит", "Жумабек", "Касым", "Оспан", "Ермек", "Абдрахман", "Мусин", "Тулеген"]


def _name(rnd: random.Random) -> str:
    first = rnd.choice(FIRST)
    return f"{first} {rnd.choice(LAST)}{'ова' if first in FEMALE else 'ов'}"
PARENTS = ["Сауле", "Гульнара", "Айгуль", "Бауыржан", "Асель", "Мурат", "Жанар", "Ербол"]
MALE_PARENTS = {"Бауыржан", "Мурат", "Ербол"}
STAFF = [
    ("branch_admin", "Янги шахар", "Асем Кенжебаева", "Админ филиала"),
    ("branch_admin", "Север", "Ринат Алиев", "Админ филиала"),
    ("office_manager", "Янги шахар", "Динара Сапарова", "Офис-менеджер"),
    ("office_manager", "Север", "Мадина Исаева", "Офис-менеджер"),
    ("sales", "Янги шахар", "Ержан Болатов", "Менеджер по продажам"),
    ("smm", "Янги шахар", "Акмарал Нурамбаева", "SMM-специалист"),
    ("teacher", "Янги шахар", "Дана Темирова", "Учитель"),
    ("teacher", "Янги шахар", "Айдос Каримов", "Учитель"),
    ("teacher", "Север", "Лаура Смагулова", "Учитель"),
    ("teacher", "Север", "Марат Есенов", "Учитель"),
]
GROUPS = [  # name, branch, level, teacher index in STAFF, weekdays, start
    ("FF2-1", "Янги шахар", "FF2", 6, [0, 2, 4], time(15, 0)),
    ("EL-5", "Янги шахар", "ELE", 6, [0, 2, 4], time(17, 0)),
    ("PI-3", "Янги шахар", "PRE", 7, [1, 3, 5], time(16, 0)),
    ("IELTS-1", "Янги шахар", "IELTS", 7, [1, 3], time(19, 0)),
    ("BEG-2", "Север", "BEG", 8, [0, 2, 4], time(16, 0)),
    ("FF1-2", "Север", "FF1", 9, [1, 3, 5], time(15, 0)),
]


def _phone(n: int) -> str:
    return f"+7705{n:07d}"


async def _staff(db: AsyncSession, role: str, branch: Branch, name: str, position: str, n: int) -> User:
    u = User(kind=UserKind.STAFF, full_name=name, phone=_phone(9000000 + n), password_hash=hash_password(DEMO_PASSWORD),
             position=position)
    db.add(u)
    await db.flush()
    db.add(UserRole(user_id=u.id, role_id=(await db.scalar(select(Role.id).where(Role.code == role)))))
    db.add(UserBranch(user_id=u.id, branch_id=branch.id))
    return u


async def seed_demo(db: AsyncSession) -> None:
    if get_settings().is_prod:
        raise SystemExit("Demo data is never loaded into production")
    if await db.scalar(select(User.id).where(User.phone == _phone(9000000))):
        print("demo already loaded")
        return
    rnd = random.Random(2018)
    branches = {b.name: b for b in await db.scalars(select(Branch))}
    levels = {lv.code: lv for lv in await db.scalars(select(Level))}
    owner = await db.scalar(select(User).where(User.phone == "+77010000001"))
    if owner is None:
        owner = await create_owner(db, "+77010000001", "Владелец One English", DEMO_PASSWORD)
    staff = [await _staff(db, r, branches[b], n, p, i + 1) for i, (r, b, n, p) in enumerate(STAFF)]
    db.add(User(kind=UserKind.STAFF, full_name="—", phone=_phone(9000000), is_active=False))  # marker: demo loaded
    await db.flush()

    # Groups with schedule from two weeks ago, so there's history to look at.
    start = today() - timedelta(days=14)
    groups = []
    for name, bname, code, ti, days, t in GROUPS:
        b = branches[bname]
        room = (await db.scalars(select(Room).where(Room.branch_id == b.id).order_by(Room.id))).all()[len(groups) % 3]
        g = Group(name=name, branch_id=b.id, level_id=levels[code].id, teacher_id=staff[ti].id, room_id=room.id, capacity=12,
                  starts_on=start)
        db.add(g)
        await db.flush()
        await chats.ensure_group_chat(db, g)
        rule = ScheduleRule(group_id=g.id, weekdays=days, start_time=t, end_time=time(t.hour + 1, 30), room_id=room.id,
                            teacher_id=g.teacher_id, valid_from=start)
        db.add(rule)
        await db.flush()
        for i in range(14):  # history: generate() only creates future lessons
            d = start + timedelta(days=i)
            if d.weekday() in days:
                db.add(Lesson(branch_id=b.id, group_id=g.id, level_id=g.level_id, teacher_id=g.teacher_id, room_id=room.id,
                              rule_id=rule.id, starts_at=at_local(d, t), ends_at=at_local(d, rule.end_time)))
        await db.flush()
        await generate(db, rule, g)
        groups.append(g)

    # Students with parents, payments and attendance for the past lessons.
    k = 0
    prev_parent = None
    for g in groups:
        for _ in range(rnd.randint(6, 10)):
            k += 1
            full = _name(rnd)
            last = full.split(" ")[1]
            kid = (await db.get(Level, g.level_id)).is_kids
            s = Student(full_name=full, phone=None if kid else _phone(1000000 + k), branch_id=g.branch_id,
                        level_id=g.level_id, status="active", source=rnd.choice(["instagram", "whatsapp", "referral", "walk_in"]),
                        balance_lesson_price=(await db.get(Level, g.level_id)).lesson_price)
            db.add(s)
            await db.flush()
            pname = rnd.choice(PARENTS)
            base = last.removesuffix("а").removesuffix("ов")
            if k % 6 == 0 and prev_parent is not None:  # siblings: some parents have two children
                pu = prev_parent
            else:
                pu = await upsert_portal_user(db, _phone(2000000 + k), f"{pname} {base}{'ов' if pname in MALE_PARENTS else 'ова'}",
                                              UserKind.PARENT)
            prev_parent = pu
            db.add(StudentGuardian(student_id=s.id, user_id=pu.id, relation=rnd.choice(["мама", "папа"])))
            if s.phone:
                s.user_id = (await upsert_portal_user(db, s.phone, s.full_name, UserKind.STUDENT)).id
            db.add(GroupMember(group_id=g.id, student_id=s.id, joined_on=start))
            await chats.sync_student_in_group_chat(db, g, s, True)
            lessons = rnd.choice([8, 12, 12, 24])
            p = Payment(student_id=s.id, branch_id=s.branch_id, level_id=s.level_id, category="course",
                        amount=lessons * s.balance_lesson_price, lessons=lessons, lesson_price=s.balance_lesson_price,
                        method=rnd.choice(["kaspi", "kaspi", "cash", "card"]), received_by=staff[2 if s.branch_id == groups[0].branch_id else 3].id,
                        paid_at=now() - timedelta(days=rnd.randint(10, 15)), is_first=True)
            db.add(p)
            await db.flush()
            await bal.apply(db, s, "payment", lessons=lessons, price=s.balance_lesson_price, ref=("payment", p.id))
            s.last_payment_at = p.paid_at
    await db.flush()

    for lesson in await db.scalars(select(Lesson).where(Lesson.ends_at < now() - timedelta(hours=1))):
        members = await db.scalars(select(GroupMember.student_id).where(GroupMember.group_id == lesson.group_id))
        for sid in members:
            st = rnd.choices([AttendanceStatus.PRESENT, AttendanceStatus.LATE, AttendanceStatus.ABSENT, AttendanceStatus.EXCUSED],
                             [80, 8, 7, 5])[0]
            charged = st != AttendanceStatus.EXCUSED
            db.add(Attendance(lesson_id=lesson.id, student_id=sid, status=st, charged=charged, marked_by=lesson.teacher_id,
                              grade=rnd.choice([None, 4, 5, 5]) if st != AttendanceStatus.ABSENT else None))
            s = await db.get(Student, sid)
            if charged:
                await bal.apply(db, s, "lesson", lessons=-1, ref=("lesson", lesson.id), counts_as_done=True)
            if st in (AttendanceStatus.PRESENT, AttendanceStatus.LATE):
                s.last_visit_at = lesson.starts_at
        lesson.status, lesson.attendance_marked_at = LessonStatus.DONE, lesson.ends_at
        n = await db.scalar(select(func.count()).select_from(Attendance).where(
            Attendance.lesson_id == lesson.id, Attendance.status.in_((AttendanceStatus.PRESENT, AttendanceStatus.LATE))))
        g = await db.get(Group, lesson.group_id)
        await accrue_lesson(db, teacher_id=lesson.teacher_id, lesson_id=lesson.id, n=n, on=local(lesson.starts_at).date(),
                            branch_id=lesson.branch_id, group_name=g.name, actor_id=None)

    # CRM: leads across the funnel, and real-looking inbound DMs.
    stages = ["new", "new", "contacted", "contacted", "trial_booked", "trial_done", "lost"]
    for i in range(18):
        b = branches["Янги шахар" if i % 3 else "Север"]
        await create_lead(db, full_name=_name(rnd), phone=_phone(3000000 + i), branch_id=b.id,
                          source=rnd.choice(["instagram", "whatsapp", "qr", "referral", "site"]), owner_id=staff[4].id,
                          assignee_id=staff[4].id, stage=stages[i % len(stages)], notify=False)
    for i, (ch, text) in enumerate([("instagram", "Здравствуйте! Сколько стоит курс для ребёнка 8 лет?"),
                                    ("whatsapp", "Добрый день, есть ли группа IELTS по вечерам?"),
                                    ("instagram", "Сәлеметсіз бе! Пробный урок тегін бе?"),
                                    ("whatsapp", "Можно записаться на пробный в субботу?")]):
        await receive(db, channel=ch, external_id=f"demo-{i}", message_id=f"demo-msg-{i}", text=text,
                      name=_name(rnd), username=f"user_{i}" if ch == "instagram" else None,
                      phone=_phone(4000000 + i) if ch == "whatsapp" else None, at=now() - timedelta(minutes=20 * (i + 1)))

    # Group chat chatter.
    for g in groups[:3]:
        chat = await db.get(Chat, g.chat_id)
        db.add(ChatMessage(chat_id=chat.id, sender_id=g.teacher_id, at=now() - timedelta(hours=3), kind="text",
                           text="Домашнее задание: Workbook стр. 24–25. Не забудьте выучить новые слова!", pinned=True))
        chat.last_message_at = now() - timedelta(hours=3)

    # Homework for the groups, and the platform rules + recording consent so the cabinet shows the acceptance flow.
    for g in groups:
        db.add(Homework(group_id=g.id, title="Workbook стр. 24–25 и новые слова", body="Выучить слова урока 5, упр. 1–4.",
                        due_at=at_local(today() + timedelta(days=2), time(15, 0)), created_by=g.teacher_id))
    from pathlib import Path

    rules = Path(__file__).resolve().parents[2] / "docs" / "source-tz-and-rules.txt"
    text = rules.read_text(encoding="utf-8") if rules.exists() else "Правила платформы One English."
    start_of_rules = text.find("Правила платформы")
    db.add(DocumentVersion(kind="rules", version="1.0", title="Правила платформы One English",
                           body=text[start_of_rules:][:90_000] if start_of_rules >= 0 else text[:90_000],
                           effective_from=now() - timedelta(days=30)))
    db.add(DocumentVersion(kind="recording", version="1.0", title="Согласие на видео- и аудиозапись",
                           body="Я уведомлён(а), что в классах школы One English ведётся видео- и аудиозапись. Даю согласие на запись "
                                "с моим участием (участием моего ребёнка) для контроля качества обучения и безопасности. Записи "
                                "хранятся 30 дней, доступны только администрации школы и не передаются третьим лицам. Согласие "
                                "можно отозвать.", effective_from=now() - timedelta(days=30)))

    # Books, shop, a couple of tasks.
    for code, title, price in (("FF2", "Family & Friends 2 — Class Book", 9500), ("ELE", "Solutions Elementary SB", 9000),
                               ("PRE", "Solutions Pre-Intermediate SB", 9500)):
        book = Book(title=title, level_id=levels[code].id, sale_price=price, purchase_price=int(price * 0.65))
        db.add(book)
        await db.flush()
        for b in branches.values():
            db.add(BookStock(branch_id=b.id, book_id=book.id, qty=rnd.randint(2, 15)))
    for name, icon, price, stock in (("Ручка One English", "pen", 50, 40), ("Кружка с логотипом", "cup", 300, 12),
                                     ("Блокнот", "book", 120, 25), ("Худи One English", "shirt", 1500, 5)):
        db.add(ShopItem(name=name, icon=icon, price_coins=price, stock=stock, cost=price * 4))
    for title, who, due in (("Обзвонить должников Янги шахар", staff[2], 1), ("Подготовить пост про IELTS-группу", staff[5], 2)):
        t = Task(title=title, creator_id=owner.id, branch_id=branches["Янги шахар"].id, priority="high",
                 due_at=at_local(today() + timedelta(days=due), time(18, 0)), status="new")
        db.add(t)
        await db.flush()
        db.add(TaskAssignee(task_id=t.id, user_id=who.id))
    await db.flush()
    print(f"demo: {len(staff)} staff, {k} students, {len(groups)} groups; staff password «{DEMO_PASSWORD}»")
    for (role, bname, name, _), u in zip(STAFF, staff):
        print(f"  {u.phone}  {name} — {role}, {bname}")
