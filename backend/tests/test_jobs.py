from datetime import timedelta

from sqlalchemy import select

from app import jobs
from app.models import AuditLog, Lead, LeadStage, Notification, Student
from app.services.clock import now
from tests.conftest import branch_id, make_staff
from tests.test_core_learning import _lesson_now, _setup, _student


async def test_attendance_reminder_once_then_admin_alert(db, client, owner_h):
    bid, teacher, room, g = await _setup(db, client, owner_h)
    admin = await make_staff(db, "branch_admin", ["Янги шахар"], "+77020000099", "Админ")
    lesson = await _lesson_now(db, g, teacher, room)
    lesson.starts_at, lesson.ends_at = now() - timedelta(minutes=100), now() - timedelta(minutes=15)
    await db.flush()
    await jobs.minutely(db)
    await jobs.minutely(db)
    t = (await db.scalars(select(Notification).where(Notification.user_id == teacher.id, Notification.kind == "attendance"))).all()
    assert len(t) == 1
    assert not (await db.scalars(select(Notification).where(Notification.user_id == admin.id, Notification.kind == "attendance"))).all()
    lesson.ends_at = now() - timedelta(minutes=40)
    await db.flush()
    await jobs.minutely(db)
    assert len((await db.scalars(select(Notification).where(Notification.user_id == admin.id, Notification.kind == "attendance"))).all()) == 1


async def test_stale_lead_alert(db, client, owner_h):
    sales = await make_staff(db, "sales", ["Янги шахар"], "+77020000098", "Продажник")
    r = await client.post("/api/crm/leads", headers=owner_h, json={
        "full_name": "Ержан", "phone": "+77017770000", "branch_id": await branch_id(db, "Янги шахар"), "source": "instagram",
        "assignee_id": sales.id})
    assert r.status_code == 201, r.text
    lead = await db.get(Lead, r.json()["id"])
    lead.stage_changed_at = lead.last_activity_at = now() - timedelta(hours=2)
    await db.flush()
    await jobs.minutely(db)
    await jobs.minutely(db)
    n = (await db.scalars(select(Notification).where(Notification.user_id == sales.id, Notification.kind == "lead_stale"))).all()
    assert len(n) == 1


async def test_left_after_90_days_goes_to_return_funnel_and_block(db, client, owner_h):
    bid = await branch_id(db, "Янги шахар")
    s = await _student(db, client, owner_h, bid)
    st = await db.get(Student, s["id"])
    st.last_visit_at = now() - timedelta(days=91)
    await db.flush()
    out = await jobs.nightly(db)
    assert out["left"] == 1
    assert st.status == "left"
    lead = await db.scalar(select(Lead).where(Lead.student_id == st.id))
    stage = await db.get(LeadStage, lead.stage_id)
    assert stage.code == "left" and lead.source == "return"
    assert (await jobs.nightly(db))["left"] == 0
    assert await db.scalar(select(AuditLog).where(AuditLog.action == "student.left", AuditLog.entity_id == st.id))
