import os

os.environ["OE_ENV"] = "test"
os.environ["OE_DATABASE_URL"] = "postgresql+asyncpg://oe:oe@localhost:5432/one_english_test"
os.environ.setdefault("OE_REQUIRE_STAFF_2FA", "false")

import subprocess  # noqa: E402
from collections.abc import AsyncIterator  # noqa: E402

import pytest  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine  # noqa: E402
from sqlalchemy.pool import NullPool  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.core.db import get_db  # noqa: E402
from app.core.kv import get_kv  # noqa: E402
from app.main import app  # noqa: E402
from app.seed import create_owner, seed_base, seed_branches  # noqa: E402

PASSWORD = "Secret-pass-123"


@pytest.fixture(scope="session", autouse=True)
def migrated_db():
    env = {**os.environ}
    root = os.path.dirname(os.path.dirname(__file__))
    psql = env["OE_DATABASE_URL"].replace("+asyncpg", "")
    subprocess.run(["psql", "-q", "-o", "/dev/null", psql, "-c", "DROP SCHEMA public CASCADE; CREATE SCHEMA public;"],
                   check=True, capture_output=True)
    subprocess.run(["alembic", "upgrade", "head"], cwd=root, env=env, check=True, capture_output=True)
    yield


@pytest.fixture
async def db() -> AsyncIterator[AsyncSession]:
    """Each test runs inside a transaction that is rolled back, so append-only tables stay usable."""
    engine = create_async_engine(get_settings().database_url, poolclass=NullPool)
    async with engine.connect() as conn:
        trans = await conn.begin()
        session = AsyncSession(bind=conn, expire_on_commit=False, join_transaction_mode="create_savepoint")
        await seed_base(session)
        await seed_branches(session)
        await session.flush()

        async def override():
            yield session

        app.dependency_overrides[get_db] = override
        get_kv().clear()  # type: ignore[union-attr]
        try:
            yield session
        finally:
            app.dependency_overrides.pop(get_db, None)
            await session.close()
            await trans.rollback()
    await engine.dispose()


@pytest.fixture
async def client(db) -> AsyncIterator[AsyncClient]:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


@pytest.fixture
async def owner(db):
    u = await create_owner(db, "+77010000001", "Айгерим Владелец", PASSWORD)
    await db.flush()
    return u


async def login(client: AsyncClient, phone: str, password: str = PASSWORD) -> dict:
    r = await client.post("/api/auth/login", json={"phone": phone, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture
async def owner_h(client, owner) -> dict:
    return await login(client, owner.phone)


async def make_staff(db, role_code: str, branch_names: list[str], phone: str, name: str = "Сотрудник"):
    from sqlalchemy import select

    from app.core.security import hash_password
    from app.models import Branch, Role, User, UserBranch, UserRole

    role = await db.scalar(select(Role).where(Role.code == role_code))
    u = User(kind="staff", full_name=name, phone=phone, password_hash=hash_password(PASSWORD))
    db.add(u)
    await db.flush()
    db.add(UserRole(user_id=u.id, role_id=role.id))
    for b in await db.scalars(select(Branch).where(Branch.name.in_(branch_names))):
        db.add(UserBranch(user_id=u.id, branch_id=b.id))
    await db.flush()
    return u


async def branch_id(db, name: str) -> int:
    from sqlalchemy import select

    from app.models import Branch

    return await db.scalar(select(Branch.id).where(Branch.name == name))


async def level_id(db, code: str) -> int:
    from sqlalchemy import select

    from app.models import Level

    return await db.scalar(select(Level.id).where(Level.code == code))
