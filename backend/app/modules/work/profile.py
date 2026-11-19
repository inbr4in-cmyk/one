"""Staff profile (анкета): the person fills it in; any signed-in user of the school can open it by link."""

from fastapi import APIRouter
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.core.audit import write_audit
from app.core.deps import DB, CurrentActor, ensure_staff_mfa
from app.core.errors import bad_request, forbidden, not_found
from app.core.schemas import In
from app.models import Branch, Role, StaffProfile, User, UserBranch, UserRole
from app.models.identity import UserKind
from app.services import files
from app.services.access import ensure_user_access

router = APIRouter(tags=["profiles"])
URL_TTL = 3600
IMAGE_EXT = (".jpg", ".jpeg", ".png", ".webp")


class PlaceIn(In):
    """A place of study or work with the years."""
    place: str = Field(min_length=1, max_length=200)
    role: str | None = Field(default=None, max_length=200)  # speciality / position
    year_from: int | None = Field(default=None, ge=1950, le=2100)
    year_to: int | None = Field(default=None, ge=1950, le=2100)


class AwardIn(In):
    title: str = Field(min_length=1, max_length=200)
    year: int | None = Field(default=None, ge=1950, le=2100)
    file_key: str | None = Field(default=None, max_length=80)
    file_name: str | None = Field(default=None, max_length=200)


class ProfileIn(In):
    photo_key: str | None = Field(default=None, max_length=80)
    email: str | None = Field(default=None, max_length=120)
    about: str | None = Field(default=None, max_length=3000)
    education: list[PlaceIn] = Field(default_factory=list, max_length=10)
    experience: list[PlaceIn] = Field(default_factory=list, max_length=20)
    awards: list[AwardIn] = Field(default_factory=list, max_length=30)
    show_contacts: bool = False


class ProfileOut(BaseModel):
    user_id: int
    full_name: str
    position: str | None
    roles: list[str]
    branches: list[str]
    photo_key: str | None
    photo_url: str | None
    phone: str | None
    email: str | None
    about: str | None
    education: list[dict]
    experience: list[dict]
    awards: list[dict]
    show_contacts: bool
    can_edit: bool


def _can_edit(actor, user_id: int) -> bool:
    return actor.user.kind == UserKind.STAFF and (actor.id == user_id or actor.can("staff", "edit"))


async def _staff(db: DB, user_id: int) -> User:
    u = await db.get(User, user_id)
    if u is None or u.kind != UserKind.STAFF or u.archived_at is not None or not u.is_active:
        raise not_found("Сотрудник")
    return u


async def _out(db: DB, actor, u: User) -> ProfileOut:
    p = await db.scalar(select(StaffProfile).where(StaffProfile.user_id == u.id))
    roles = list(await db.scalars(select(Role.name).join(UserRole, UserRole.role_id == Role.id).where(UserRole.user_id == u.id)))
    branches = list(await db.scalars(select(Branch.name).join(UserBranch, UserBranch.branch_id == Branch.id)
                                     .where(UserBranch.user_id == u.id).order_by(Branch.name)))
    can_edit = _can_edit(actor, u.id)
    # Staff see each other's contacts; students and parents only when the person allowed it.
    contacts = actor.user.kind == UserKind.STAFF or bool(p and p.show_contacts)
    awards = [{**a, "file_url": files.signed_url(a.get("file_key"), ttl=URL_TTL, name=a.get("file_name")) if a.get("file_key") else None}
              for a in (p.awards if p else [])]
    return ProfileOut(
        user_id=u.id, full_name=u.full_name, position=u.position, roles=roles, branches=branches,
        photo_key=p.photo_key if p and can_edit else None,
        photo_url=files.signed_url(p.photo_key, ttl=URL_TTL) if p and p.photo_key else None,
        phone=u.phone if contacts else None, email=u.email if contacts else None,
        about=p.about if p else None, education=p.education if p else [], experience=p.experience if p else [],
        awards=awards, show_contacts=bool(p and p.show_contacts), can_edit=can_edit)


@router.get("/profiles/{user_id}", response_model=ProfileOut)
async def get_profile(user_id: int, db: DB, actor: CurrentActor) -> ProfileOut:
    """Open to every signed-in user of the school (staff, students, parents), never to the public."""
    ensure_staff_mfa(actor)
    await ensure_user_access(db, actor.user)
    return await _out(db, actor, await _staff(db, user_id))


@router.put("/profiles/{user_id}", response_model=ProfileOut)
async def save_profile(user_id: int, body: ProfileIn, db: DB, actor: CurrentActor) -> ProfileOut:
    ensure_staff_mfa(actor)
    if not _can_edit(actor, user_id):
        raise forbidden("Анкету заполняет сам сотрудник")
    u = await _staff(db, user_id)
    for x in [*body.education, *body.experience]:
        if x.year_from and x.year_to and x.year_to < x.year_from:
            raise bad_request("Год окончания раньше года начала")
    if body.photo_key:
        path = files.path_of(body.photo_key)
        if path is None or not path.lower().endswith(IMAGE_EXT):
            raise bad_request("Фото: файл JPG, PNG или WEBP")
    for a in body.awards:
        if a.file_key and files.path_of(a.file_key) is None:
            raise bad_request("Файл сертификата не найден, загрузите его ещё раз")
    email = (body.email or "").strip() or None
    if email and ("@" not in email or " " in email):
        raise bad_request("Проверьте адрес почты")
    p = await db.scalar(select(StaffProfile).where(StaffProfile.user_id == u.id))
    if p is None:
        p = StaffProfile(user_id=u.id)
        db.add(p)
    p.photo_key = body.photo_key
    p.about = (body.about or "").strip() or None
    p.education = [x.model_dump() for x in body.education]
    p.experience = [x.model_dump() for x in body.experience]
    p.awards = [x.model_dump() for x in body.awards]
    p.show_contacts = body.show_contacts
    u.email = email
    # the photo is also the avatar across the program
    u.avatar_url = files.signed_url(body.photo_key, ttl=10 * 365 * 86400) if body.photo_key else None
    await write_audit(db, actor_id=actor.id, action="staff.profile", entity="user", entity_id=u.id, branch_id=None, ip=actor.ip)
    await db.commit()
    return await _out(db, actor, u)
