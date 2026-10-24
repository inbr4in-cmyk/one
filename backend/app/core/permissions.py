"""Role builder catalog: module × action × data scope (ТЗ 2.1).

Scopes, from narrow to wide: own (only my records) < branch (my branches) < network (all).
"""

from dataclasses import dataclass, field

OWN, BRANCH, NETWORK = "own", "branch", "network"
SCOPES = (OWN, BRANCH, NETWORK)
_RANK = {OWN: 0, BRANCH: 1, NETWORK: 2}

# module -> (title, {action: title})
CATALOG: dict[str, tuple[str, dict[str, str]]] = {
    "dashboard": ("Дашборд", {"view": "Просмотр"}),
    "branches": ("Филиалы и кабинеты", {"view": "Просмотр", "create": "Создание", "edit": "Редактирование", "archive": "Архивирование"}),
    "roles": ("Роли и доступы", {"view": "Просмотр", "manage": "Управление"}),
    "staff": ("Сотрудники", {"view": "Просмотр", "create": "Создание", "edit": "Редактирование", "archive": "Архивирование"}),
    "settings": ("Настройки", {"view": "Просмотр", "edit": "Изменение"}),
    "schedule": ("Расписание", {"view": "Просмотр", "create": "Создание", "edit": "Перенос и отмена"}),
    "students": ("Ученики и группы", {
        "view": "Просмотр", "create": "Создание", "edit": "Редактирование", "archive": "Архивирование",
        "export": "Экспорт", "transfer": "Переводы и заморозки", "view_contacts": "Видеть телефоны",
    }),
    "attendance": ("Посещаемость", {"view": "Просмотр", "mark": "Отметка", "edit_past": "Исправление задним числом"}),
    "homework": ("Домашние задания и оценки", {"view": "Просмотр", "manage": "Выдача и проверка"}),
    "crm": ("CRM и лиды", {"view": "Просмотр", "create": "Создание", "edit": "Редактирование", "archive": "Архивирование", "export": "Экспорт"}),
    "inbox": ("Входящие Instagram / WhatsApp", {"view": "Просмотр", "reply": "Ответ"}),
    "payments": ("Продажа курса и оплаты", {"view": "Просмотр", "create": "Приём оплаты", "discount": "Скидки и промокоды", "refund": "Возвраты"}),
    "finance": ("Финансы и отчёты", {"view": "Просмотр", "edit": "Расходы", "export": "Экспорт"}),
    "payroll": ("Зарплата и KPI", {"view": "Просмотр", "adjust": "Премии и удержания", "approve": "Утверждение ведомости"}),
    "tasks": ("Задачи", {"view": "Просмотр", "create": "Постановка"}),
    "books": ("Книги", {"view": "Просмотр", "sell": "Продажа", "stock": "Приход, перемещение, списание", "edit": "Каталог"}),
    "coins": ("Коины", {"view": "Просмотр", "award": "Начисление", "writeoff": "Списание"}),
    "shop": ("Магазин коинов", {"view": "Просмотр", "edit": "Каталог", "issue": "Выдача заказов"}),
    "chats": ("Чаты", {
        "use": "Пользоваться чатами", "message_students": "Писать ученикам", "message_parents": "Писать родителям",
        "message_staff": "Писать сотрудникам", "pin": "Закреплять сообщения", "monitor": "Просмотр чатов (контроль качества)",
    }),
    "tests": ("Тесты", {"view": "Просмотр", "edit": "Конструктор", "review": "Ручная проверка"}),
    "training": ("База обучения", {"view": "Просмотр", "edit": "Материалы", "progress": "Прогресс сотрудников"}),
    "complaints": ("Жалобы", {"view": "Просмотр", "answer": "Ответ"}),
    "audit": ("Журнал действий", {"view": "Просмотр"}),
    "security": ("Безопасность", {"view": "Сессии сотрудников", "manage": "Завершать сессии"}),
}

# Modules where staff must have 2FA confirmed in this session.
SENSITIVE_MODULES = {"roles", "finance", "payroll", "security", "audit", "settings", "staff"}


def is_valid(module: str, action: str) -> bool:
    return module in CATALOG and action in CATALOG[module][1]


def wider(a: str | None, b: str | None) -> str | None:
    if a is None:
        return b
    if b is None:
        return a
    return a if _RANK[a] >= _RANK[b] else b


@dataclass
class Grants:
    scopes: dict[tuple[str, str], str] = field(default_factory=dict)

    def add(self, module: str, action: str, scope: str) -> None:
        key = (module, action)
        self.scopes[key] = wider(self.scopes.get(key), scope)  # type: ignore[assignment]

    def scope(self, module: str, action: str) -> str | None:
        return self.scopes.get((module, action))

    def as_list(self) -> list[str]:
        return sorted(f"{m}.{a}:{s}" for (m, a), s in self.scopes.items())


def _all(scope: str) -> list[tuple[str, str, str]]:
    return [(m, a, scope) for m, (_, acts) in CATALOG.items() for a in acts]


def _p(spec: str, scope: str) -> list[tuple[str, str, str]]:
    """'students.view,edit attendance.mark' -> [(students, view, scope), ...]"""
    out = []
    for part in spec.split():
        module, actions = part.split(".")
        for a in actions.split(","):
            assert is_valid(module, a), (module, a)
            out.append((module, a, scope))
    return out


# Default role templates from the ТЗ access table (section 2.2 and the matrix).
# Sales cannot sell a course: payments.create is deliberately absent (ТЗ 2.2).
DEFAULT_ROLES: dict[str, dict] = {
    "owner": {"name": "Супер-админ", "system": True, "perms": _all(NETWORK), "coin_limit": 100000},
    "branch_admin": {
        "name": "Админ филиала",
        "perms": _p(
            "dashboard.view schedule.view,create,edit students.view,create,edit,archive,export,transfer,view_contacts "
            "attendance.view,mark,edit_past homework.view crm.view,create,edit,archive,export inbox.view,reply "
            "payments.view,create,discount,refund finance.view,edit,export payroll.view,adjust,approve "
            "tasks.view,create books.view,sell,stock coins.view,award,writeoff shop.view,edit,issue "
            "chats.use,message_students,message_parents,message_staff,monitor tests.view,review "
            "training.view,progress complaints.view,answer staff.view branches.view",
            BRANCH,
        ),
        "coin_limit": 1000,
    },
    "office_manager": {
        "name": "Офис-менеджер",
        "perms": _p(
            "dashboard.view schedule.view students.view,create,edit,view_contacts attendance.view "
            "crm.view,create,edit inbox.view,reply payments.view,create books.view,sell shop.view,issue coins.view "
            "chats.use,message_parents,message_students,message_staff training.view branches.view",
            BRANCH,
        )
        + _p("tasks.view payroll.view", OWN),
    },
    "sales": {
        "name": "Отдел продаж",
        "perms": _p("schedule.view crm.view,create,edit inbox.view,reply training.view branches.view chats.use,message_staff", BRANCH)
        + _p("tasks.view payroll.view", OWN),
    },
    "teacher": {
        "name": "Учитель",
        "perms": _p(
            "schedule.view students.view attendance.view,mark homework.view,manage coins.view,award "
            "chats.use,message_students,message_parents,message_staff,pin tests.view,review tasks.view payroll.view",
            OWN,
        )
        + _p("training.view", BRANCH),
        "coin_limit": 200,
    },
    "smm": {
        "name": "SMM",
        "perms": _p("inbox.view,reply crm.view,create chats.use,message_staff training.view", BRANCH) + _p("tasks.view", OWN),
    },
    # Portal roles: their data access is fixed in the portal endpoints (own child / own record only).
    "student": {"name": "Ученик", "system": True, "perms": _p("chats.use,message_staff", OWN)},
    "parent": {"name": "Родитель", "system": True, "perms": _p("chats.use,message_staff", OWN)},
}
SYSTEM_ROLE_CODES = {c for c, r in DEFAULT_ROLES.items() if r.get("system")}
