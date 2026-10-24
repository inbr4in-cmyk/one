# One English — план разработки платформы (веб → мобильное)

> Источник истины: ТЗ v3 (финальное, 16.10.2026) + «Правила платформы One English» (21.10.2026) + `docs/DECISIONS.md` (решения заказчика, имеют приоритет над ТЗ) + утверждённый прототип `docs/design/web.html`.
> Школа английского языка, Шымкент, 2 филиала: **«Янги шахар»** и **«Север»**. Часовой пояс — `Asia/Almaty` (UTC+5). Валюта — тенге, **все денежные суммы хранятся целыми числами в тенге (`BIGINT`, суффикс `_kzt`)**, без копеек и без float.
> Документ составлен 24.10.2026.

---

## 1. Цели и границы

### 1.1. Цель
Единая платформа для школы: учебный процесс, расписание, посещаемость, баланс уроков, CRM с единым инбоксом Instagram + WhatsApp, внутренние чаты (включая родителей), уведомления в WhatsApp, финансы и P&L, зарплата/KPI, задачи, книги, коины и магазин, база обучения, а также требования «Правил платформы» (согласия, жалобы, блокировки, отметка прихода сотрудников). Принципы: ничего не удаляется физически (только архив), неизменяемый журнал действий, строгая безопасность.

### 1.2. Что входит в веб-версию (этапы 0–6)
| Блок | Состав |
|---|---|
| Кабинет сотрудника (все роли персонала) | Дашборд, расписание, ученики, группы, посещаемость, CRM, инбокс IG/WA, чаты, финансы, зарплата/KPI, задачи, книги, коины/магазин, тесты, база обучения, жалобы, роли и доступы, безопасность, журнал, настройки |
| Публичная часть | QR-тест уровня (мобильная веб-страница без входа), страница принятия правил/согласия при первом входе |
| Кабинет ученика (веб, адаптивный) | Расписание, ДЗ, оценки, тесты, баланс «оплачено — проведено — осталось», чаты, коины, магазин, рейтинги, книги, оценка урока, жалобы, заявки (смена группы/филиала, заморозка) |
| Кабинет родителя (веб, адаптивный) | Несколько детей, посещаемость, оценки, звёздочки, ежемесячные отзывы, ДЗ, оплаты/чеки, долг, книги, коины, **чаты с учителем/администратором** (решение заказчика №2), согласия, жалобы |
| Интеграции | WhatsApp Business Cloud API (уведомления + инбокс), Instagram Messaging API (инбокс), SMS-провайдер (резерв OTP), S3-хранилище, Excel-импорт/экспорт, PDF-чеки и отчёты |
| Языки | Русский и казахский (интерфейс и шаблоны WhatsApp) |

### 1.3. Что входит в мобильную версию (этап 7, Flutter, iOS + Android)
Только ученик и родитель (персонал работает в адаптивном вебе): вход по телефону + OTP, расписание, баланс, ДЗ с прикреплением файла, оценки, тесты, чаты (текст, фото, файлы, голосовые), push (FCM/APNs), коины/магазин, книги, жалобы, согласия, переключение между детьми, онлайн-оплата (если подключён провайдер). Мобильное приложение использует **тот же API v1**, новых бизнес-правил на этапе 7 не появляется.

### 1.4. Что позже (вне текущего объёма, после запуска)
- Онлайн-оплата Kaspi Pay / эквайринг — интерфейс заложен (`payment_providers`), подключение после договора с банком (см. вопросы).
- Фискальные чеки (онлайн-ККМ: Webkassa/ReKassa) — пока PDF-квитанция платформы.
- IP-телефония (пропущенные звонки, правило «перезвонить за 15 мин») — пока звонки фиксируются вручную как события лида.
- TikTok, сайт-конструктор (лиды с сайта принимаем через простой webhook/форму уже в этапе 2).
- Интеграция с камерами видеонаблюдения (платформа хранит только согласия и ссылки на фрагменты по жалобам).
- Приложение для персонала на Flutter, офлайн-режим, BI-выгрузки.

---

## 2. Архитектура

### 2.1. Компоненты
```
[Vue 3 SPA (Vite, TS, Pinia)]   [Flutter app (этап 7)]   [QR-тест (часть SPA, публичный маршрут)]
            │  HTTPS (REST /api/v1, WS /ws)                   │
            ▼                                                  ▼
       [Nginx / reverse proxy: TLS, заголовки безопасности, лимиты тела, статика SPA]
            │
            ▼
  [FastAPI API (uvicorn, N воркеров)] ──► [PostgreSQL 16]  (основные данные, audit_log append-only)
            │  ▲                     ──► [Redis 7]  (rate limit, OTP, WS pub/sub, очереди задач, кэш прав)
            │  │                     ──► [S3 / MinIO]  (файлы, приватные бакеты, presigned URL)
            ▼  │
  [Worker (arq, async) + Scheduler (arq cron)]  ── outbox → WhatsApp Cloud API / SMS / FCM / APNs
            ▲
  [Webhook-приёмник /api/v1/webhooks/meta] ← Meta Graph (WhatsApp + Instagram)
```
- **Один бэкенд-репозиторий (монолит с модулями)**, деплой: контейнеры `api`, `worker`, `scheduler`, `nginx`, `postgres`, `redis`, `minio` (dev) — docker compose; прод — те же образы на VPS/облаке в Казахстане (см. вопросы: локализация персональных данных).
- **Transactional outbox**: любое внешнее действие (WhatsApp, SMS, push, e-mail) пишется в `outbox_events` в той же транзакции, что и бизнес-факт; воркер доставляет с повторами (экспоненциальная задержка, до 5 попыток), результат — в `notification_deliveries`. Нет «потерянных» уведомлений при сбое.
- **Идемпотентность**: заголовок `Idempotency-Key` для оплат, возвратов, переводов, заказов магазина; вебхуки Meta дедуплицируются по `message.id`.

### 2.2. Структура бэкенда
```
backend/
  app/
    core/        config, db (async engine, session), security (jwt, argon2, crypto), errors, i18n, pagination, clock
    common/      base models (id, created_at, created_by, archived_at), mixins, money(int тенге), phone (E.164)
    modules/
      auth/          вход, OTP, TOTP 2FA, refresh-ротация, сессии/устройства
      users/         пользователи, профили, сотрудники (оклад, филиалы)
      rbac/          роли, права, назначения с областью, проверка доступа, жёсткие запреты
      audit/         запись журнала, просмотр, экспорт, проверка цепочки хэшей
      org/           филиалы, кабинеты, рабочие часы
      academics/     уровни (цены с датами действия), группы, состав, регулярное расписание, уроки, конфликты
      students/      ученики, родители/опекуны, доверенные лица для забора ребёнка, статусы, история
      attendance/    отметки, окна редактирования, напоминания
      billing/       баланс (пакеты уроков), ledger, оплаты, скидки/промокоды, возвраты, переводы, заморозки, долги, блокировка
      progress/      оценки, ДЗ и сдачи, комментарии, звёздочки, ежемесячные отзывы, оценка урока учеником
      tests/         конструктор тестов, QR-тест уровня, финальный тест (150), ручная проверка
      crm/           воронки, этапы, лиды, события, задачи по лиду, пробные, отказы, «Возврат», аналитика
      inbox/         каналы (WA/IG), контакты, диалоги, сообщения, вебхуки Meta, окно 24 ч, шаблоны ответа
      chats/         внутренние чаты: групповые, личные, участники, сообщения, закрепы, прочтения, модерация-просмотр
      notifications/ шаблоны (ru/kk), outbox, доставки, push-токены, настройки событий
      finance/       кассы/счета, доходы, расходы, категории, регулярные расходы, распределение общих расходов, P&L
      payroll/       ставки с датой действия, периоды, начисления, ручные премии/удержания, утверждение, сторно
      tasks/         задачи, повторяющиеся задачи, комментарии, вложения, отчёты
      books/         каталог, склады филиалов, приход, перемещения, списания, продажи
      coins/         ledger коинов, правила начисления, лимиты учителей, магазин, заказы, бейджи, рейтинги
      training/      курсы, материалы, назначение по ролям, прогресс
      compliance/    версии правил и согласий, принятия, жалобы (SLA), заявки учеников (смена группы/филиала)
      staff_time/    отметка прихода/ухода сотрудников, ежедневные отчёты
      files/         загрузка (presigned), проверка, метаданные, выдача ссылок
      reports/       сводные отчёты, дашборды, экспорт Excel/PDF
      imports/       импорт из Excel (ученики, родители, балансы, группы) с предпросмотром
      settings/      настройки системы (сроки, флаги, лимиты) с историей
    workers/         задачи arq + cron
  migrations/        Alembic
  tests/             pytest + httpx + testcontainers (Postgres, Redis)
```
Каждый модуль: `models.py` (SQLAlchemy 2, `Mapped[...]`), `schemas.py` (Pydantic v2), `repository.py` (все запросы с фильтром области доступа), `service.py` (бизнес-правила, транзакции, запись в audit/outbox), `router.py` (FastAPI, зависимости `require("module.action")`), `events.py` (доменные события для других модулей). Модули общаются через сервисы и доменные события, не через чужие таблицы напрямую.

Фронтенд (`web/`): Vue 3 + Vite + TS + Pinia + Vue Router, vue-i18n (ru/kk), API-клиент генерируется из OpenAPI (`openapi-typescript`), дизайн-токены из прототипа (navy `#01225F`, red `#BB1027`), компоненты прототипа: боковое меню по правам, глобальный поиск (Ctrl K), колокольчик уведомлений, канбан, сетка расписания, таблицы с фильтрами, карточка ученика, переключатель филиала.

### 2.3. Фоновые задачи (arq worker + cron)
| Задача | Расписание | Что делает |
|---|---|---|
| `generate_lessons` | ежедневно 02:00 + при изменении шаблона | Разворачивает `recurring_schedules` в `lessons` на 8 недель вперёд (настраивается), пропуская праздники/исключения; конфликт → урок не создаётся, задача админу |
| `mark_students_left` | ежедневно 03:00 | Ученик без оплат **и** без посещений 90 дней (3 мес., настраивается) → статус «Ушёл», запись в историю, лид в воронку «Возврат» |
| `attendance_reminders` | каждые 5 мин | Урок начался > 10 мин назад (правила: отметка в течение 10 мин) и не отмечен → напоминание учителю; через 30 мин → уведомление админу филиала |
| `lesson_finalize` | каждые 15 мин + 23:59 | Закрывает окно учителя в конце дня, проводит списания уроков и начисления учителю по отмеченным урокам |
| `low_balance_reminders` | ежедневно 10:00 | Осталось ≤ 2 урока (настраивается) → WhatsApp родителю; долг → напоминание |
| `nonpayment_block` | ежедневно 00:30 | Неоплата > 5 дней после начала оплачиваемого месяца → блокировка доступа к урокам и кабинету (см. §8) |
| `stale_leads` | каждые 5 мин | Лид без первого ответа > 30 мин (настраивается), без движения по этапу > N дней → уведомление ответственному и руководителю |
| `inbox_sla` | каждые 5 мин | Неотвеченный входящий IG/WA > SLA (2 ч по правилам SMM, см. вопросы) → эскалация; окно 24 ч заканчивается через 1 ч → предупреждение |
| `task_reminders` / `recurring_tasks` | каждые 15 мин / ежедневно 00:10 | Приближение срока, просрочка; создание повторяющихся задач |
| `payroll_month_close` | 1-го числа 01:00 | Бонус удержания (500 × учеников), формирование черновика ведомости за прошлый месяц |
| `coins_auto` | ежедневно 04:00 + события | Месяц без пропусков, дни рождения; остальные начисления — по событиям |
| `recurring_expenses` | ежедневно 01:30 | Создание регулярных расходов |
| `low_stock_books` | ежедневно 09:00 | Остаток книги ниже порога → уведомление |
| `complaints_sla` | каждый час | 24 ч на подтверждение, 3 раб. дня на ответ (7 при проверке) → эскалация операционному директору |
| `consent_watch` | ежедневно 08:00 | Ученики с уроком завтра без согласия на запись/принятых правил → список админу |
| `monthly_feedback_due` | 25-го числа | Напоминание учителям написать ежемесячный отзыв по каждому ученику |
| `outbox_dispatch` | постоянно | Доставка WA/SMS/push, повторы, уведомление админу при окончательной ошибке |
| `audit_chain_verify` / `audit_export` | ежедневно | Проверка цепочки хэшей журнала; экспорт дня в S3 с Object Lock (WORM) |
| `sessions_cleanup`, `files_orphans`, `rules_update_notice` | ежедневно | Очистка просроченных сессий, неподтверждённых загрузок; уведомления о новой версии правил за 7 дней |

Все cron-задачи идемпотентны (повторный запуск не создаёт дублей: уникальные ключи / `ON CONFLICT DO NOTHING`), с распределённой блокировкой в Redis.

### 2.4. Веб-сокеты (чаты и инбокс)
- Эндпоинт `GET /ws` — клиент получает одноразовый `ws_ticket` (TTL 30 с) через REST с access-токеном, затем подключается `wss://.../ws?ticket=...` (токен не попадает в URL-логи надолго).
- Сервер подписывает соединение на каналы Redis pub/sub: `user:{id}`, `chat:{id}` (только где пользователь участник), `inbox:branch:{id}` (для операторов с правом `inbox.view`). Публикация из любого API-воркера/воркера Meta → все инстансы.
- События: `chat.message.new`, `chat.message.read`, `chat.typing`, `chat.pinned`, `inbox.message.new`, `inbox.conversation.assigned`, `notification.new`, `lead.updated`, `unread.counters`.
- Сообщения сохраняются через REST (`POST /chats/{id}/messages`), WS — только доставка событий; при переподключении клиент догружает по `after_id`. Heartbeat 30 с, лимит соединений на пользователя (5).
- При переводе ученика/увольнении/блокировке — немедленный разрыв подписок на чужие каналы.

### 2.5. Хранение файлов
- S3-совместимое хранилище (MinIO в dev), приватные бакеты: `chat-files`, `inbox-media`, `homework`, `training-media`, `receipts`, `avatars`, `complaints`, `imports`, `audit-archive` (Object Lock).
- Загрузка: `POST /files/upload-intent` → presigned PUT (TTL 5 мин, ограничение размера и MIME) → `POST /files/{id}/complete` → воркер проверяет сигнатуру файла (magic), антивирус ClamAV, удаляет EXIF у изображений, делает превью. До проверки файл недоступен другим.
- Выдача: только presigned GET на 5 мин после проверки прав на родительскую сущность (сообщение, ДЗ, материал).
- Лимиты: изображения 10 МБ, документы 20 МБ, голосовые 10 МБ / 5 мин, видео базы обучения 2 ГБ (multipart). Медиа из WhatsApp/Instagram скачиваются воркером сразу (ссылки Meta временные) и сохраняются в `inbox-media`.

---

## 3. Модель данных

Общие правила: PK `id BIGINT identity` (наружу — `public_id UUID`), `created_at/updated_at timestamptz`, `created_by`, `archived_at` (мягкое архивирование вместо удаления; `DELETE` для бизнес-таблиц запрещён правами БД роли приложения). Деньги — `BIGINT` тенге. Финансовые и бонусные данные — **журналы только на добавление** (исправление = сторно-запись). Телефоны — E.164 (`+77011234567`).

### 3.1. Пользователи, доступ, безопасность
| Таблица | Ключевые поля |
|---|---|
| `users` | id, phone (unique), email, full_name, birth_date, photo_file_id, locale (ru/kk), kind (staff/student/parent), password_hash (argon2id, nullable для OTP-only), status (active/blocked/archived), failed_logins, locked_until, totp_secret_enc, totp_enabled, last_login_at |
| `staff_profiles` | user_id, position, hired_at, fired_at, salary_kzt (оклад), branch_ids, is_teacher |
| `roles` | id, code, name_ru, name_kk, is_system (super_admin/student/parent нельзя удалить), description |
| `permissions` | code (`module.action`, напр. `payments.create`), module, action (view/create/edit/archive/export/approve/special), description |
| `role_permissions` | role_id, permission_code, data_scope (`own` / `branch` / `network`), records_scope (`own_records` / `all`) |
| `role_assignments` | user_id, role_id, scope_type (`branches`/`network`), branch_ids[], valid_from, valid_to, assigned_by |
| `chat_policies` | from_role_id, to_role_id, allowed, condition (`same_group`/`own_students`/`own_children_teacher`/`any`) — настраиваемая матрица переписки |
| `sessions` | id, user_id, device_id, refresh_family_id, ip, user_agent, created_at, last_seen_at, revoked_at, revoke_reason |
| `refresh_tokens` | id, family_id, token_hash, parent_id, issued_at, expires_at, used_at, revoked_at |
| `devices` | id, user_id, platform (web/ios/android), name, push_token, trusted_until |
| `otp_challenges` | (Redis) phone_hash → code_hash, attempts, ttl; в БД — только `otp_log` (phone_hash, channel, status, ip) |
| `totp_recovery_codes` | user_id, code_hash, used_at |
| `security_settings` | ip_allowlist для финансов (из прототипа), требования к паролям, длительность сессий |
| `audit_log` | id, occurred_at, actor_user_id, actor_role_ids, session_id, ip, action, entity_type, entity_id, branch_id, before jsonb, after jsonb, reason, request_id, prev_hash, hash — **append-only** (§9) |

### 3.2. Организация
| Таблица | Ключевые поля |
|---|---|
| `branches` | id, name («Янги шахар», «Север»), address, phone, work_hours jsonb, responsible_admin_id, timezone, is_active |
| `rooms` | id, branch_id, name/number, capacity, equipment, status (active/repair) |
| `holidays` | date, branch_id (null = сеть), name — исключения для генерации уроков |
| `settings` | key, value jsonb, branch_id (null = сеть), effective_from, changed_by — все настраиваемые числа (3 ч, 15 мин, 5 дней, 2 урока, 3 мес., SLA) |

### 3.3. Учебный модуль
| Таблица | Ключевые поля |
|---|---|
| `levels` | id, code, name, order_index, final_test_id, next_level_id, recommended_book_id, is_active |
| `level_prices` | level_id, price_per_lesson_kzt, effective_from (цена на момент оплаты берётся отсюда) |
| `groups` | id, branch_id, level_id, name (PI-3, FF3-1), teacher_id, room_id, capacity, status (forming/active/finished/archived), start_date, end_date, chat_id |
| `group_members` | id, group_id, student_id, joined_at, left_at, reason (transfer/finish/left), transfer_id |
| `recurring_schedules` | id, group_id, weekdays int[], start_time, end_time, room_id, teacher_id, valid_from, valid_to |
| `lessons` | id, group_id (или student_id для индивидуальных), branch_id, room_id, planned_teacher_id, actual_teacher_id, starts_at, ends_at, level_id, status (planned/held/cancelled/moved), cancel_reason, moved_from_id, generated_from_schedule_id, attendance_marked_at. **Exclusion-constraint** `EXCLUDE USING gist (room_id WITH =, tstzrange(starts_at, ends_at) WITH &&) WHERE status <> 'cancelled'` и такой же по `actual_teacher_id` |
| `attendance` | id, lesson_id, student_id, status (present/absent/late/excused/trial_present/trial_absent), marked_by, marked_at, comment, is_trial, lead_id; unique (lesson_id, student_id); изменения — новая версия + audit |
| `grades` | lesson_id, student_id, value (шкала настраивается), comment, teacher_id |
| `homeworks` | id, lesson_id/group_id, title, body, files, due_at, published_by |
| `homework_submissions` | homework_id, student_id, status (done/submitted/checked), file_ids, submitted_at, checked_by, checked_at, grade, comment |
| `teacher_comments` | student_id, lesson_id, text, visible_to_parent |
| `stars` | student_id, lesson_id, teacher_id, count, reason (правила для детей) |
| `monthly_feedback` | student_id, teacher_id, month, text, published_at |
| `lesson_ratings` | lesson_id, student_id, score 1–5, comment (KPI учителя) |
| `lesson_reviews` | lesson_id, reviewer_id (методист), criteria jsonb (пунктуальность, качество, вовлечённость, знание, поведение), comment — 2 записи/мес. на учителя |

### 3.4. Ученики и родители
| Таблица | Ключевые поля |
|---|---|
| `students` | id, user_id, branch_id, current_level_id, status (lead/trial/active/frozen/finished/left), source, lead_id, sales_user_id (кто привёл), office_manager_id (кто оформил), last_payment_at, last_attendance_at, is_minor, access_blocked_at, block_reason |
| `student_status_history` | student_id, from_status, to_status, reason, at, by |
| `guardians` | id, user_id, full_name, phone, whatsapp_phone, locale |
| `student_guardians` | student_id, guardian_id, relation (мать/отец/опекун), is_primary, is_payer, receives_whatsapp |
| `pickup_persons` | student_id, full_name, phone, document_note, valid_to (правила для родителей: кто забирает ребёнка) |
| `contracts` | student_id, number, signed_at, file_id, signed_by_guardian_id |

### 3.5. Баланс и деньги
| Таблица | Ключевые поля |
|---|---|
| `balance_lots` | id, student_id, payment_id/transfer_id, level_id, lessons_total, lessons_remaining, unit_price_kzt — «пакеты» уроков по цене на момент оплаты, списание FIFO |
| `balance_ledger` | id, student_id, lot_id, entry_type (payment_credit/lesson_debit/transfer_out/transfer_in/refund/freeze_note/correction/money_credit/money_debit), lessons_delta, money_delta_kzt, lesson_id, ref_type, ref_id, created_by, reason — **append-only**; текущий баланс = агрегат (кэш в `student_balances`) |
| `student_balances` | student_id, lessons_paid, lessons_held, lessons_remaining, money_remaining_kzt, debt_kzt, updated_at (материализованный кэш, пересчитывается в той же транзакции) |
| `payments` | id, student_id, branch_id, level_id, lessons_count, unit_price_kzt, gross_kzt, discount_kzt, money_balance_used_kzt, amount_kzt, method (cash/card/kaspi/transfer/online), cashbox_id, accepted_by, promo_code_id, is_first_payment, lead_id, receipt_no, receipt_file_id, idempotency_key, status (posted/reversed) |
| `discounts` / `promo_codes` | type (percent/fixed/family), value, valid_from/to, max_uses, branch_id, requires_permission |
| `refunds` | id, payment_id, student_id, lessons_count, amount_kzt, reason, requested_by, approved_by, status (requested/approved/rejected/paid) |
| `transfers` | id, student_id, from_group_id, to_group_id, from_level_id, to_level_id, from_branch_id, to_branch_id, lessons_before, money_before_kzt, money_value_kzt, lessons_after, money_after_kzt, calc jsonb, reason, is_free_change, created_by |
| `freezes` | id, student_id, starts_on, ends_on, reason, prepayment_payment_id, status (requested/active/finished/cancelled), approved_by |
| `cashboxes` | id, branch_id, name, type (cash/bank/kaspi) |

### 3.6. CRM
| Таблица | Ключевые поля |
|---|---|
| `pipelines` | id, code (main/return), name, branch_id (null = сеть) |
| `lead_stages` | id, pipeline_id, code (new/contacted/trial_booked/trial_attended/paid/lost), name, order_index, is_final, sla_hours |
| `contacts` | id, phone (E.164, unique nullable), wa_id, ig_scoped_id, ig_username, name, locale, merged_into_id |
| `leads` | id, contact_id, pipeline_id, stage_id, branch_id, source (sales/qr_test/site/instagram/whatsapp/referral/return), owner_user_id (привлёк — основа KPI), assignee_user_id, office_manager_id, student_id, referrer_student_id, age, guardian_name/phone, placement_result_id, recommended_level_id, trial_lesson_id, lost_reason_id, lost_comment, first_response_at, last_activity_at, status (open/won/lost) |
| `lead_events` | id, lead_id, type (created/stage_changed/call/message/note/trial_booked/trial_attended/payment/lost/assigned/merged), payload jsonb, by, at |
| `lost_reasons` | id, name, is_active |
| `lead_tasks` | связь `tasks` ↔ лид (используется общий модуль задач) |

### 3.7. Внешний инбокс (Instagram + WhatsApp)
| Таблица | Ключевые поля |
|---|---|
| `channels` | id, type (whatsapp/instagram), branch_id, external_id (phone_number_id / ig_user_id), display_name, access_token_enc, status |
| `conversations` | id, channel_id, contact_id, lead_id, assignee_user_id, status (open/pending/closed), last_inbound_at (для окна 24 ч), last_outbound_at, unread_count, first_response_at |
| `messages` | id, conversation_id, direction (in/out), external_message_id (unique), type (text/image/audio/video/document/template/story_reply), body, media_file_id, template_id, status (queued/sent/delivered/read/failed), error_code, sent_by_user_id, created_at |
| `quick_replies` | id, title, body_ru, body_kk, branch_id |
| `webhook_events` | id, provider, external_id (unique), signature_ok, payload jsonb, received_at, processed_at, error |

### 3.8. Внутренние чаты
| Таблица | Ключевые поля |
|---|---|
| `chats` | id, type (group/direct/staff), group_id, branch_id, title, created_at, archived_at |
| `chat_members` | chat_id, user_id, role (owner/member), joined_at, left_at, last_read_message_id, muted |
| `chat_messages` | id, chat_id, sender_id, type (text/image/file/voice/system), body, file_ids, reply_to_id, edited_at, hidden_at, hidden_by (скрытие модератором, без физического удаления), created_at |
| `chat_pins` | chat_id, message_id, pinned_by, pinned_at, unpinned_at |
| `chat_access_log` | chat_id, viewer_id (просмотр для контроля качества), at — также в audit |

### 3.9. Уведомления
| Таблица | Ключевые поля |
|---|---|
| `notification_templates` | id, event_code (absence/payment/low_balance/debt/lesson_cancelled/lesson_moved/book_purchase/arrived/late/otp/complaint_reply…), channel (whatsapp/push/sms/inapp), locale (ru/kk), body с переменными `{{name}}`, `{{date}}`, `{{time}}`, `{{group}}`, `{{amount}}`, `{{lessons_left}}`, wa_template_name, wa_status (approved/pending/rejected), is_enabled |
| `notification_settings` | event_code, branch_id, enabled (напр. «Пришёл»/«Опоздал» опционально) |
| `outbox_events` | id, event_code, recipient_user_id/phone, payload, dedupe_key (unique), status, attempts, next_attempt_at |
| `notification_deliveries` | id, outbox_id, channel, provider_message_id, status (sent/delivered/read/failed), error, at |
| `inapp_notifications` | user_id, type, title, body, link, read_at |

### 3.10. Финансы, зарплата
| Таблица | Ключевые поля |
|---|---|
| `income_entries` | id, branch_id, category (course/books/shop/other), amount_kzt, source_type/source_id (payment, book_sale), cashbox_id, at |
| `expense_categories` | id, code, name (аренда, зарплата, реклама, коммунальные, материалы, закупка книг, товары магазина, налоги, прочее) |
| `expenses` | id, branch_id (null = общий для сети), category_id, amount_kzt, date, comment, receipt_file_id, recurring_id, source_type/source_id (payroll_period, book_receipt, shop_purchase), status (posted/reversed) |
| `recurring_expenses` | шаблон, периодичность, следующая дата |
| `expense_allocations` | expense_id, branch_id, share_pct, amount_kzt (распределение общих расходов: по выручке/ученикам/поровну — настраивается) |
| `rate_settings` | id, code (teacher_base_lesson, teacher_extra_per_student, teacher_extra_threshold, teacher_retention_bonus, teacher_final_test_bonus, final_test_threshold, sales_trial_bonus, sales_return_bonus, om_sale_bonus), value_kzt, branch_id, effective_from, set_by — **история без перезаписи** |
| `payroll_periods` | id, month, branch_id, status (open/calculated/approved/paid/closed), approved_by, approved_at, expense_id |
| `payroll_accruals` | id, period_id, user_id, type (lesson/group_size/retention/final_test/trial/return/sale/salary/manual_bonus/manual_deduction/reversal), amount_kzt, source_type, source_id, rate_setting_id, details jsonb, comment, reverses_id. **unique (type, source_type, source_id, user_id) WHERE type NOT IN (manual_*, reversal)** — защита от двойного бонуса |
| `kpi_snapshots` | user_id, month, metrics jsonb (посещаемость, удержание, своевременность отметки, задачи в срок, оценки уроков, рейтинг методиста) |

### 3.11. Задачи, книги, коины, магазин
| Таблица | Ключевые поля |
|---|---|
| `tasks` | id, title, description, priority, status (new/in_progress/review/done/cancelled), due_at, created_by, branch_id, link_type/link_id (student/lead/group), recurring_rule_id, completed_at, is_overdue |
| `task_assignees` | task_id, user_id, status, completed_at |
| `task_comments`, `task_attachments`, `recurring_task_rules` | комментарии, файлы, правило (daily/weekly, дни) |
| `books` | id, title, level_id, sale_price_kzt, purchase_price_kzt, photo_file_id, is_active |
| `book_stock` | branch_id, book_id, quantity, min_quantity (кэш, источник — движения) |
| `book_movements` | id, book_id, type (receipt/sale/transfer_out/transfer_in/write_off/correction), branch_id, quantity, unit_cost_kzt, supplier, student_id, reason, transfer_id, status (для перемещения: sent/received), by — **append-only** |
| `book_sales` | id, student_id, book_id, branch_id, price_kzt, payment_method, cashbox_id, sold_by, movement_id |
| `coin_rules` | code (attendance/month_no_absence/homework/final_test/birthday/referral), amount, is_enabled, effective_from |
| `coin_ledger` | id, student_id, delta, type (award_auto/award_manual/spend/reserve/release/write_off), source_type, source_id (unique для авто), comment, by — **append-only**; баланс = сумма, резерв отдельно |
| `teacher_coin_limits` | teacher_id, month, limit, used |
| `shop_items` | id, name, photo, price_coins, stock, branch_id (филиал выдачи), cost_kzt |
| `shop_orders` | id, student_id, item_id, branch_id, price_coins, status (placed/ready/issued/cancelled), reserved_ledger_id, issued_by, issued_at |
| `badges`, `student_badges` | бейджи и достижения |

### 3.12. Тесты и база обучения
| Таблица | Ключевые поля |
|---|---|
| `tests` | id, kind (placement/final/training), level_id, title, max_score (final = 150), time_limit, version, is_active |
| `test_questions` | id, test_id, type (single/multi/text/manual), body, options jsonb, correct jsonb, score, order |
| `placement_scales` | test_id, min_score, max_score, level_id |
| `qr_codes` | id, branch_id, test_id, token, is_active |
| `test_attempts` | id, test_id, student_id/lead_id/user_id, started_at, finished_at, auto_score, manual_score, total_score, checked_by, status, answers jsonb, ip_hash |
| `training_courses` | id, title, role_ids[], order |
| `training_materials` | id, course_id, type (video/document/test), file_id, test_id, order |
| `training_progress` | user_id, material_id, viewed_at, completed_at, test_attempt_id |

### 3.13. Соответствие правилам, жалобы, сотрудники
| Таблица | Ключевые поля |
|---|---|
| `policy_documents` | id, kind (platform_rules/rules_students/rules_kids/rules_parents/rules_teachers/rules_staff/recording_consent), version, text_ru, text_kk, published_at, effective_from (не раньше +7 дней для изменений), hash |
| `policy_acceptances` | id, document_id, version, subject_user_id (за кого), signed_by_user_id (кто: сам/родитель), at, ip, user_agent, method (checkbox/paper), paper_file_id, revoked_at, revoke_reason |
| `complaints` | id, author_id, branch_id, subject_type (teacher/staff/other), subject_user_id, text, file_ids, status (new/acknowledged/investigating/answered/appealed/closed), acknowledged_at, due_at, extended_at, answer, decided_by, appeal_text, is_flagged_false |
| `complaint_events` | complaint_id, type, by, at, payload |
| `student_requests` | id, student_id, type (change_group_free/change_branch/freeze/early_final), payload, status, handled_by, due_at |
| `staff_shifts` | id, user_id, branch_id, check_in_at, check_out_at, method (web_ip/qr), ip, comment |
| `daily_reports` | user_id, date, text, metrics jsonb, submitted_at (до 20:00) |
| `files` | id, bucket, key, mime, size, sha256, owner_id, status (pending/clean/infected), scanned_at |
| `import_jobs` | id, file_id, type, status, preview jsonb, errors jsonb, applied_at, by |

---

## 4. Роли и права

### 4.1. Модель «модуль × действие × область данных»
- Право = `module.action` (≈ 25 модулей × view/create/edit/archive/export + спец. действия: `payments.refund`, `attendance.edit_past`, `payroll.approve`, `chats.supervise`, `contacts.reveal_phone`, `discounts.apply`, `coins.write_off`, `audit.view`, `rbac.manage`).
- Для каждого права в роли задаётся **область**: `network` / `branch` (филиалы из назначения) и **круг записей**: `all` / `own_records` (свои ученики, свои лиды, свои уроки, свои начисления).
- Пользователь может иметь несколько ролей (`role_assignments`), итоговые права — объединение; область назначения ограничивает филиалы.
- Проверка в два слоя: зависимость роутера `require("payments.create")` + фильтр в репозитории (`scope.apply(query)`) — нельзя получить чужую запись по id (IDOR-тесты на каждый эндпоинт).
- Права кэшируются в Redis на 60 с, сбрасываются при изменении ролей; изменения ролей — в audit.
- Системные роли: **Супер-админ, Ученик, Родитель** — нельзя удалить; последний супер-админ не может быть снят.

### 4.2. Роли по умолчанию (шаблоны из таблицы ТЗ + роли из Правил)
| Модуль | Супер-админ | Админ филиала | Офис-менеджер | Отдел продаж | Учитель | Ученик | Родитель |
|---|---|---|---|---|---|---|---|
| Филиалы, роли, настройки | Да | Нет | Нет | Нет | Нет | Нет | Нет |
| Расписание | Все | Свой филиал | Свой филиал | Просмотр | Своё | Своё | Ребёнка |
| Посещаемость | Да (+задним числом) | Да (+задним числом) | Просмотр | Нет | Свои уроки (окно дня) | Своя | Ребёнка |
| CRM / лиды / инбокс | Да | Да | Да | Да (свои лиды) | Нет | Нет | Нет |
| Продажа курса, приём оплат | Да | Да | Да | **Нет** | Нет | Нет | Просмотр |
| Финансы, прибыль | Все | Свой филиал | Нет | Нет | Нет | Нет | Нет |
| Книги (склад, продажа) | Да | Да | Да | Нет | Нет | Свои | Ребёнка |
| Задачи | Ставит всем | Ставит своему филиалу | Свои | Свои | Свои | Нет | Нет |
| KPI и зарплата | Все | Свой филиал (утверждает) | Своя | Своя | Своя | Нет | Нет |
| Чаты | Просмотр всех | Просмотр своего филиала | С родителями (настр.) | Нет | Свои группы, ученики, их родители | Свои | С учителем/админом ребёнка |
| Коины | Да | Да | Выдача заказов | Нет | Начисление (лимит) | Покупка | Просмотр |
| Журнал действий | Просмотр | Просмотр филиала | Нет | Нет | Нет | Нет | Нет |
| Жалобы | Все | Своего филиала | Подать | Подать | Подать | Подать | Подать |

Дополнительные шаблоны из Правил (не удаляемые, но редактируемые): **Операционный директор** (жалобы, апелляции, отчёты сети, просмотр чатов, без настроек ролей), **Методист** (оценка уроков по записям, просмотр расписания/учителей, база обучения), **SMM** (инбокс Instagram/WhatsApp: ответы и передача лида продажникам, без оплат и финансов), **Бухгалтер** (финансы и ведомости сети, без CRM).

### 4.3. Матрица переписки (внутренние чаты)
Настраивается в «Роли и доступы → Кто с кем может переписываться» (`chat_policies`), **кроме жёстких запретов**.
| Кто → кому | Учитель | Ученик | Родитель | Админ/офис | Другой ученик | Чужой родитель |
|---|---|---|---|---|---|---|
| Учитель | да (рабочие) | да, свои ученики | да, родители своих учеников (настр.) | да | — | — |
| Ученик | да, свой учитель | **нет (только общий групповой чат)** | **нет** | да, админ филиала (настр.) | **нет** | **нет** |
| Родитель | да, учитель своего ребёнка (настр.) | **только свой ребёнок (настр.)** | **нет** | да, админ/офис филиала | **нет** | **нет** |
| Админ/офис | да | да | да (настр.) | да | — | — |
- Групповой чат группы: учитель + ученики группы (ТЗ п.8), создаётся автоматически; при переводе — исключение из старого и добавление в новый в одной транзакции с переводом. Родители **не** добавляются в групповой чат учеников (иначе родитель получал бы доступ к чужим детям).
- Супер-админ / админ филиала / операционный директор — только просмотр (`chats.supervise`), каждый просмотр пишется в audit.
- Сообщения родителей учителю принимаются всегда, но push учителю — с 9:00 до 20:00 (правила); SLA ответа 24 ч отображается в чате.

### 4.4. Жёсткие запреты (в коде, не настраиваются)
1. Ученик ↔ другой ученик (личные), ученик ↔ чужой родитель, родитель ↔ другой родитель — запрещены всегда (решение №3). Проверка в `chats.service` при создании чата и при каждой отправке; попытка — 403 + запись в audit.
2. Журнал действий неизменяем для всех, включая владельца (решение №4): нет API на изменение/удаление, триггер БД.
3. Оплаты, начисления, движения книг и коинов не редактируются — только сторно с причиной.
4. Отметка посещаемости после окна — только с правом `attendance.edit_past` и обязательной причиной.
5. Нельзя утвердить ведомость, в которой есть собственные ручные начисления утверждающего; нельзя менять свои права.
6. 2FA обязательна для всех сотрудников; отключить для отдельного сотрудника нельзя.
7. Последний супер-админ не может быть заблокирован/снят; системные роли не удаляются.
8. Жалобу не видит тот, на кого она подана (даже при наличии прав на модуль).
9. Продажник не может оформлять продажу курса и принимать оплату (по умолчанию; изменяется только супер-админом с записью в журнал).

---

## 5. CRM и лиды

### 5.1. Воронки
| Воронка | Этапы (настраиваются) | Особенности |
|---|---|---|
| Основная | Новая заявка → Связались → Записан на пробный → Пришёл на пробный → Оплатил / Отказ | Канбан (прототип «Воронка продаж»), SLA на этап, задачи и напоминания по лиду |
| «Возврат» | Ушёл → Связались → Договорились → Оплатил / Отказ | Ученики со статусом «Ушёл» попадают автоматически (cron), `owner_user_id` — продажник, взявший лид |

### 5.2. Автозахват из Instagram и WhatsApp (решение №5)
1. Meta присылает webhook → `POST /webhooks/meta`: проверка `X-Hub-Signature-256` (HMAC-SHA256 по сырому телу, app secret), запись в `webhook_events` (unique по external id), ответ 200 за < 1 с, обработка в воркере.
2. Поиск контакта: WhatsApp — по `wa_id` / телефону (E.164); Instagram — по `ig_scoped_id` (телефона нет; появляется, если клиент его написал — парсер номера предлагает менеджеру связать).
3. Нет контакта → создаётся `contact` + `lead` (pipeline main, этап «Новая заявка», source instagram/whatsapp, филиал по каналу или «не определён» → распределяет старший менеджер) + `conversation`.
4. Контакт есть: есть открытый лид → сообщение в его диалог; есть ученик/родитель → диалог привязывается к карточке, лид **не** создаётся (помечается «клиент»); есть закрытый (lost) лид старше 30 дней → новый лид с ссылкой на прежний.
5. Дубли: уникальность телефона в `contacts`; при совпадении IG-контакта с WA-контактом по телефону — слияние (`merged_into_id`), с сохранением истории, действие в audit.
6. Назначение: round-robin среди операторов филиала в рабочее время, иначе — в очередь утра; уведомление ответственному (in-app + WS).
7. Фиксируется `first_response_at`; KPI «время первого ответа».

### 5.3. Окно 24 часа и шаблоны
- WhatsApp: свободные сообщения — только в течение 24 ч после последнего входящего от клиента (`last_inbound_at`); вне окна — только утверждённые Meta шаблоны (категории marketing/utility), UI блокирует поле ввода и предлагает шаблон.
- Instagram: ответ в течение 24 ч; после — только с тегом `HUMAN_AGENT` (до 7 дней), далее ответить нельзя — UI показывает таймер окна.
- Быстрые ответы (`quick_replies`) ru/kk для операторов; медиа (фото/голос) входящие сохраняются в S3.
- Статусы доставки (sent/delivered/read/failed) из webhooks обновляют сообщения.

### 5.4. QR-тест уровня → лид
1. В каждом филиале — свой QR (`qr_codes.token`) → публичная страница `/t/{token}`.
2. Форма: имя, телефон (обязательно, проверка формата +7), возраст, опционально имя и телефон родителя; согласие на обработку ПД (версия фиксируется); капча-«невидимка» + rate limit по IP/телефону.
3. Тест с автопроверкой → шкала `placement_scales` → рекомендуемый уровень; результат показывается клиенту без баллов по вопросам.
4. Телефон уже есть у лида → результат прикрепляется к существующему лиду (ТЗ п.6); иначе — новый лид (source `qr_test`, филиал из QR). Уведомление ответственному менеджеру.

### 5.5. Пробный урок → KPI → продажа
1. Продажник записывает лида на пробный прямо в урок группы (проверка вместимости кабинета и группы) → этап «Записан на пробный», WA-подтверждение клиенту.
2. Учитель в посещаемости видит пробного (бейдж «пробный»), отмечает «Пришёл» → лид автоматически «Пришёл на пробный» → начисление **2 000 тг продажнику** (`owner_user_id`) с уникальным ключом (lead_id, trial) — один пробный = один бонус, даже при повторном пробном.
3. Обязательный контакт после пробного в тот же день (правила отдела продаж) → задача офис-менеджеру/продажнику автоматически.
4. **Продажу оформляет только офис-менеджер** (или админ): мастер «Оформить продажу» — группа, уровень, количество уроков, скидка (по праву), способ оплаты → при первой оплате: лид → «Оплатил», создаётся `student` (если не было), `office_manager_id`, бонус **2 000 тг офис-менеджеру** (продажа после пробного), фиксация учителя пробного для бонуса удержания (500 тг в конце месяца).
5. Отказ — только с причиной из справочника (+ комментарий).

### 5.6. Зависшие лиды и аналитика
- «Зависший» = нет первого ответа > 30 мин (новые входящие), новая заявка не обработана > 1 ч (правила продаж), нет действия на этапе > `sla_hours`. Отображение на дашборде (прототип «Зависшие лиды»), уведомления ответственному и руководителю.
- Аналитика: конверсия по этапам, продажникам, офис-менеджерам, источникам, филиалам; время первого ответа; причины отказов; число возвратов; стоимость привлечения = расходы категории «Реклама» за период / новые ученики (по источнику, если расход помечен источником).

---

## 6. Учебный модуль

### 6.1. Расписание
- Виды: по кабинетам (сетка «дни × время»), по учителям (день/неделя/месяц), по группам, личное ученика/родителя.
- Регулярное расписание (напр. Пн/Ср/Пт 16:00–17:30) → генерация уроков на 8 недель (cron + сразу при сохранении).
- Конфликты на уровне БД (exclusion constraints по кабинету и учителю) + проверка в сервисе с понятной ошибкой «Каб. 2 занят группой EL-5 16:00–17:30». Вместимость: число участников + пробные ≤ `rooms.capacity` и `groups.capacity`.
- Перенос/отмена — с причиной; уведомление ученикам и родителям (WhatsApp + push); перенесённый урок связан с исходным.
- Замена учителя: `actual_teacher_id` ≠ `planned_teacher_id`; оплата начисляется фактическому; уведомление группе не позднее чем за 2 ч (правила админов) — система предупреждает, если позже.
- Загрузка кабинетов % = занятые часы / рабочие часы филиала.

### 6.2. Баланс уроков
- Оплата = N уроков × цена уровня на дату оплаты (`level_prices`) → `balance_lot`. Пример: 12 × 3 000 = 36 000 тг.
- Проведённый урок (статус held) списывает 1 урок с ученика (FIFO по пакетам) для статусов: present, late; для absent — по настройке «пропуск без уважительной причины» (**по умолчанию списывать** — правила: «Пропущенный урок без предупреждения … считается проведённым»); excused — не списывать. Пропуск с предупреждением за ≥ 3 ч через платформу → статус excused автоматически (настраивается).
- Ученик и родитель всегда видят «оплачено — проведено — осталось» и денежный остаток.
- Осталось 2 урока (настраивается) → WhatsApp родителю.
- Если уроков 0, а ученик пришёл → урок списывается в минус (долг `debt_kzt`), учитель видит пометку «нет оплаты».

### 6.3. Перевод с пересчётом
| Случай | Правило |
|---|---|
| Другая группа того же уровня (или другой филиал, та же цена) | Баланс переносится без изменений |
| Другой уровень с другой ценой | Денежная стоимость = Σ (оставшиеся уроки пакета × цена пакета) **+ денежный остаток**; Новые уроки = ⌊стоимость ÷ цена урока нового уровня⌋; остаток = стоимость − новые уроки × новая цена → на денежный баланс, засчитывается при следующей оплате |

Пример из ТЗ: осталось 4 урока × 3 000 = 12 000 тг; новый уровень 4 000 → ⌊12 000 / 4 000⌋ = **3 урока**, остаток 0. Пример 2: 13 000 тг / 4 000 = **3 урока + 1 000 тг** на денежном балансе.
- Перед подтверждением — экран расчёта (до/после); после — запись `transfers` с `calc`, сторно старых пакетов, новый пакет, `balance_ledger`, смена `group_members`, перенос в чаты, подсказка «нужна книга уровня X», audit.
- Бесплатная смена группы/учителя один раз после первых 3 занятий (правила) — заявка ученика, флаг `is_free_change`, админ предлагает варианты за 3 раб. дня.
- Досрочный финальный тест: успешная сдача → предложение перевода на следующий уровень в ближайшую группу.

### 6.4. Заморозка
- По заявлению; уроки не списываются, ученик не отображается в посещаемости на период.
- Правила: не дольше 1 месяца за курс, при предоплате за месяц; предоплата засчитывается в первый месяц после выхода — реализуется как обычная оплата, пакет активен после окончания заморозки. Лимиты (срок, количество раз) — настройки.
- Статус ученика «заморожен» ↔ «активен» автоматически по датам.

### 6.5. Посещаемость
| Кто | Когда может отмечать/менять |
|---|---|
| Учитель (фактический) | С начала урока до 23:59 того же дня (окно настраивается) |
| Админ филиала / супер-админ | В любое время, только с причиной → audit + пересчёт списаний/начислений (сторно и новая запись) |
- Статусы: Пришёл / Не пришёл / Опоздал / Уважительная причина. Правило «опоздание > 15 мин = пропуск» — подсказка учителю и настройка (по умолчанию: «Опоздал» списывает урок и учитывается в N).
- Напоминание учителю через 10 мин после начала, админу — через 30 мин (настройки).
- Отметка запускает: WA «не пришёл» родителю (и опционально «пришёл»/«опоздал»), KPI пробного, коины за посещение, списание уроков, начисление учителю.
- Заблокированный за неоплату ученик отображается с красной меткой (§8).

### 6.6. ДЗ, оценки, прогресс
- ДЗ публикует учитель до 22:00 дня урока (контроль своевременности для KPI); ученик отмечает выполнение / прикрепляет файл; проверка учителем — 48 ч (просрочка видна методисту).
- Оценки за урок, комментарии учителя (видят ученик и родитель), звёздочки детям, ежемесячный отзыв родителям.
- Ученик оценивает урок (1–5) → KPI учителя.

### 6.7. Финальный тест (150 баллов)
- Конструктор: вопросы с вариантами (автопроверка) + вопросы с ручной проверкой учителем; максимум 150.
- Результат в карточке ученика; ≥ проходного порога (настраивается) → предложение перевода на следующий уровень; не сдан → повтор уровня.
- **> 100 баллов → бонус учителю 1 000 тг** (уникально на попытку/ученика/уровень — повторная сдача того же уровня бонус не даёт) + коины ученику.

---

## 7. Финансы, зарплата/KPI, книги, коины, задачи, база обучения

### 7.1. Финансы
- Доходы: оплаты курсов (наличные, карта, Kaspi, перевод; онлайн — позже), книги (категория «Книги»), прочее. Каждая оплата привязана к ученику, уровню, филиалу, кассе и принявшему сотруднику; квитанция PDF; WA-сообщение родителю (сумма, за что, уроков оплачено, итоговый остаток).
- Скидки, семейная скидка, промокоды — только по праву `discounts.apply`.
- Возвраты: заявка с причиной → утверждение (супер-админ/админ филиала по праву `payments.refund`) → сторно пакета уроков, расход/возврат денег, **отмена связанных бонусов** (продажа офис-менеджера, удержание учителя) в текущем открытом периоде (если период утверждён — сторно в следующем) с отражением в ведомости. См. вопрос о противоречии с Правилами.
- Расходы: категории, филиал или «общий для сети» с распределением, чек, регулярные расходы; закупка книг, выплата зарплаты, себестоимость товаров магазина → расходы автоматически.
- Отчёты: P&L по месяцам/филиалам/сети, движение денег по кассам, выручка по уровням/группам/учителям, средний чек, рентабельность групп (выручка уроков − начисления учителю − доля аренды), ФОТ и KPI, отток/возврат, долги; дашборд владельца (прототип); экспорт Excel/PDF. Доступ к финансам — дополнительно по IP-списку (настройка из прототипа «Вход по IP для финансов»).

### 7.2. Зарплата и KPI
| Сотрудник | Начисление | Условие | Сумма (по умолчанию) |
|---|---|---|---|
| Учитель | Ставка за урок | Урок проведён и посещаемость отмечена | 2 500 тг |
| Учитель | Доплата за размер | N > 5 присутствовавших | +100 × (N − 5) |
| Учитель | Удержание после пробного | Ученик был на пробном у этого учителя и оплатил курс; в конце месяца | 500 × число учеников |
| Учитель | Финальный тест | > 100 из 150 | 1 000 за ученика |
| Продажник | Приход на пробный | Его лид пришёл на пробный (отметил учитель) | 2 000 |
| Продажник | Возврат ушедшего | Ученик «Ушёл» повторно оплатил благодаря продажнику | 2 000 |
| Офис-менеджер | Продажа после пробного | Оформил продажу, первая оплата поступила | 2 000 |
| Все | Оклад | Из карточки сотрудника | индивидуально |
| Все | Ручная премия / удержание | Только админ, комментарий обязателен | — |

- Формула урока: `pay = base + extra × max(0, N − threshold)`; base=2 500, extra=100, threshold=5. Пример: 8 учеников → 2 500 + 300 = **2 800 тг**. N = present + late (+ пришедшие пробные — см. вопрос). Начисляется фактическому учителю.
- Ставки — `rate_settings` с `effective_from`: расчёт берёт ставку, действующую на дату факта; прошлые начисления не пересчитываются.
- **Защита от двойных бонусов**: уникальный индекс (type, source_type, source_id, user_id); все начисления создаются только сервисом payroll из доменных событий (идемпотентно), ручное создание бонусов этих типов запрещено.
- **Отмена при возврате/исправлении**: событие `payment.refunded` или `attendance.changed` → запись `reversal` (ссылка `reverses_id`) в открытом периоде; если период утверждён — в следующем периоде, с пометкой в расшифровке.
- Период: open (начисления в реальном времени, сотрудник видит свои с расшифровкой) → calculated (1-го числа: удержание, оклады) → approved (админ филиала/супер-админ) → paid (создаётся расход «Зарплата») → closed. Изменения после approve — только корректировками следующего периода.
- KPI учителя (рейтинг, влияет на премию по решению админа): средняя посещаемость групп, удержание (продления), своевременность отметки посещаемости (≤ 10 мин), ДЗ/оценки до 22:00, проверка ДЗ ≤ 48 ч, задачи в срок, оценки уроков учениками, оценка методиста по записям. Рейтинг по филиалу и сети.

### 7.3. Книги
- Каталог, отдельный склад на филиал (движения — append-only, остаток — кэш), приход (поставщик, кол-во, закупочная цена → расход «Закупка книг»), перемещение между филиалами (отправлено → получено, подтверждение принимающим), списание с причиной, порог низкого остатка.
- Продажа только ученику (привязка к карточке), оплата отдельно, доход «Книги», WA-подтверждение родителю, история книг в карточке, подсказка при переводе на уровень.
- Отчёты: остатки, приход, продажи, перемещения, списания, выручка и прибыль (продажа − закупка, себестоимость по средней цене), ученики уровня без книги.

### 7.4. Коины и магазин
- Авто-начисления (уникальный `source_id`): посещение урока, месяц без пропусков, выполненное ДЗ, финальный тест, день рождения, приведённый друг (после его первой оплаты). Суммы — `coin_rules`.
- Ручное начисление учителем — в пределах месячного лимита, с комментарием; списание — только админ с причиной.
- Заказ: Оформлен (резерв коинов) → Готов к выдаче → Выдан (списание, выдаёт офис-менеджер филиала) / Отменён (возврат резерва). Себестоимость → расходы.
- Рейтинги в группе/филиале/сети, бейджи. Звёздочки (правила для детей) — отдельная сущность, не коины (опционально конвертация — настройка).

### 7.5. Задачи
- Название, описание, исполнители (один/несколько), срок, приоритет, вложения, связь с учеником/лидом/группой; статусы Новая → В работе → На проверке → Выполнена / Отменена; комментарии, история (audit), повторяющиеся (ежедневно/еженедельно), уведомления (новая, срок близко, просрочка).
- Автозадачи системы: контакт после пробного, конфликт расписания, замена учителя, «Пройти обучение до даты», ответ на жалобу.
- Отчёты: по сотрудникам, филиалам, просрочкам → KPI.

### 7.6. База обучения
- Курсы по ролям (учитель, офис-менеджер, продажи, SMM), материалы: видео (S3, потоковое воспроизведение через presigned URL), документы, тесты из конструктора.
- Прогресс: просмотрено, результаты тестов; админ видит прогресс каждого. Обучение не блокирует рабочий доступ. Задача «Пройти обучение до …» через модуль задач.

---

## 8. Требования из «Правил платформы», которых нет в ТЗ

| Требование | Реализация на платформе |
|---|---|
| Принятие правил обязательно; без него доступ не открывается | При первом входе и при новой версии — экран правил своей группы (студент 18+, родитель за ребёнка < 18, дети < 12 — короткая версия показывается, принимает родитель, преподаватель, сотрудник). Middleware: без актуального `policy_acceptance` доступны только экран правил и выход. Хранится версия, хэш текста, дата, IP |
| Обновление правил — уведомление не позднее чем за 7 дней | Новая версия публикуется с `effective_from ≥ now + 7 дней`; уведомление in-app + push; после даты вступления — повторное принятие |
| Согласие на видео- и аудиозапись с версией | `policy_documents.kind = recording_consent`; галочка (студент 18+ сам, до 18 — родитель) + отметка о бумажной подписи в договоре (скан). Без согласия: ученик не может быть отмечен «Пришёл» (учитель видит предупреждение, админ — список), сотрудник/учитель не допускается к урокам в расписании. Отзыв — по письменному заявлению: админ фиксирует, система создаёт задачу «предложить другой формат или расторгнуть договор». Отчёт «кто не подписал» до запуска |
| Жалобы и предложения со сроками | Раздел в кабинете всех ролей, вложения; видят только администрация и операционный директор (исключён фигурант); подтверждение ≤ 24 ч, ответ ≤ 3 раб. дня, продление до 7 раб. дней при проверке (уведомление автору), апелляция операционному директору, пометка «заведомо ложная». SLA-таймеры и эскалация |
| Блокировка при неоплате более 5 дней | Оплата за месяц — до первого урока месяца; через 5 дней (настройка) при `debt > 0` или нулевом балансе после начала месяца → `access_blocked_at`: кабинет ученика/родителя показывает только баланс, оплату, чат с администратором и жалобы; в посещаемости — метка «доступ приостановлен», учитель не может отметить «Пришёл» без подтверждения админа. Разблокировка — автоматически при оплате. Уведомления за 2 дня и в день блокировки |
| Отметка прихода/ухода сотрудников | `staff_shifts`: кнопка «Пришёл/Ушёл» в вебе, разрешена только из сети филиала (IP-список) или по QR на ресепшене (динамический код); опоздания относительно графика → отчёт; учитель должен быть в филиале за 15 мин до первого урока |
| Ежедневный отчёт сотрудника до 20:00 | Форма отчёта по участку (метрики подставляются автоматически: звонки, оплаты, лиды), напоминание в 19:00, просрочка — в KPI |
| Звёздочки детям | Учитель ставит звёздочку за соблюдение правил на уроке; видят родители и ученик |
| Ежемесячный отзыв родителям | Учитель раз в месяц пишет отзыв по каждому ученику; напоминание 25-го; публикуется в кабинете родителя (+ push); выполнение — в KPI |
| Предупреждение о пропуске за 3 ч | Кнопка «Не приду» у ученика/родителя; ≥ 3 ч до урока → уважительная причина (не списывается, если включено), < 3 ч → обычный пропуск |
| Опоздание > 15 мин = пропуск | Подсказка учителю и настройка правила списания |
| Отработка по болезни со справкой | Заявка с файлом справки → админ назначает отработку (урок в другой группе без списания) |
| Бесплатная смена группы/учителя 1 раз после 3 занятий | Заявка `student_requests.change_group_free`, срок ответа 3 раб. дня |
| Перевод в другой филиал по заявлению | Заявка → перевод с переносом баланса без изменений |
| Заморозка ≤ 1 мес. за курс с предоплатой | §6.4 |
| Доверенные лица для забора ребёнка | `pickup_persons` в карточке, видны админу филиала |
| Договор и согласие до первого урока (в т.ч. пробного) | Чек-лист в карточке лида/ученика; предупреждение при записи на пробный |
| Методист: 2 записи уроков/мес. на учителя | Форма оценки урока по 5 критериям, план-контроль методиста, влияние на KPI |
| Сообщения преподавателю 9:00–20:00, ответ 24 ч | Тихие часы для push учителю, индикатор SLA |
| Данные клиентов не копировать | Маскирование телефонов, запрет экспорта без права, водяной знак с именем сотрудника в экспортах Excel/PDF, audit экспорта |
| Один аккаунт — один студент | Вход по телефону; привязка устройства; уведомление о входе с нового устройства |
| Записи камер хранятся 30 дней, доступ — опер. директор, методист, админ | Платформа не хранит видео камер; хранит согласия и ссылки/фрагменты по жалобам (`complaints.file_ids`) до решения |

---

## 9. Безопасность

| Область | Решение |
|---|---|
| Пароли | argon2id (argon2-cffi: m=64 МБ, t=3, p=4), минимум 10 символов, проверка по списку утёкших (локальный top-100k), блокировка 15 мин после 5 неудач, уведомление о входе с нового устройства |
| Токены | JWT access 15 мин (EdDSA/ES256, `kid`, ротация ключей), claims: sub, sid, roles-hash; refresh — непрозрачный случайный токен 256 бит, хранится хэш, срок 30 дней (сотрудники — 7 дней), **ротация при каждом использовании**; повторное использование старого refresh → отзыв всей семьи (`family_id`) и сессии + уведомление пользователю и в audit |
| Хранение токенов | Веб: access в памяти, refresh — cookie `HttpOnly; Secure; SameSite=Strict; Path=/api/v1/auth`; Flutter: secure storage (Keychain/Keystore) |
| 2FA | TOTP (RFC 6238, pyotp) обязательно для всех сотрудников, 10 одноразовых кодов восстановления (хэши), секрет зашифрован; сброс 2FA — только супер-админ, с записью в audit; повторный ввод TOTP для критичных действий (изменение ролей, утверждение ведомости, возврат, экспорт) — step-up |
| OTP для учеников/родителей | 6 цифр, TTL 5 мин, хэш в Redis, 5 попыток, повторная отправка через 60 с, ≤ 5/час на телефон, ≤ 20/час на IP; канал — WhatsApp authentication template, резерв — SMS; одинаковый ответ для существующих и несуществующих номеров |
| Rate limiting | Redis (скользящее окно): логин/OTP — строго; API — 300 запросов/мин на пользователя; публичный QR-тест и вебхуки — отдельные лимиты; 429 с `Retry-After` |
| Сессии и устройства | Список активных сессий (прототип «Активные сессии»): устройство, IP, город, последняя активность; завершить одну/все; автоматическое завершение при смене пароля/2FA/блокировке; неактивность сотрудника > 12 ч → повторный вход |
| CSRF / CORS | Access-токен в заголовке `Authorization` (CSRF не применим); для cookie-эндпоинтов refresh/logout — double-submit CSRF-токен + проверка `Origin`; CORS — только точные домены веб-приложения, без `*`, `allow_credentials` только для них |
| Вебхуки Meta | GET-верификация `hub.verify_token`; POST — проверка `X-Hub-Signature-256` (HMAC-SHA256 сырого тела app secret, `hmac.compare_digest`), отклонение без подписи, дедупликация по id, лимит тела 1 МБ, обработка асинхронно |
| Маскирование ПД | Телефоны в списках: `+7 701 *** ** 45`; полный номер — по праву `contacts.reveal_phone`, каждый показ — в audit; оператор отвечает в инбоксе, не видя номера полностью (если нет права); в логах приложения ПД не пишутся (фильтр), в Sentry — scrubbing |
| Журнал (append-only) | Отдельная схема `audit`; роль приложения имеет только `INSERT, SELECT`; триггер `BEFORE UPDATE OR DELETE OR TRUNCATE ON audit_log → RAISE EXCEPTION 'audit_log is append-only'`; цепочка хэшей (`hash = sha256(prev_hash ‖ row)`), ежедневная проверка и экспорт в S3 с Object Lock (WORM); миграции не могут менять таблицу без отдельной роли владельца БД. Пишутся: входы, изменения карточек, права, оплаты, переводы, посещаемость задним числом, начисления, коины, книги, просмотры чатов, показ телефонов, экспорт |
| Прочие журналы-только-добавление | `balance_ledger`, `coin_ledger`, `book_movements`, `payroll_accruals`, `policy_acceptances` — триггер запрета UPDATE/DELETE (кроме служебных полей статуса через отдельные функции) |
| Шифрование секретов | Токены Meta, ключ SMS-провайдера, TOTP-секреты — AES-256-GCM (envelope: ключ данных шифруется мастер-ключом из переменной окружения / KMS), ротация мастер-ключа; секреты окружения — не в репозитории (gitleaks в CI) |
| Транспорт | TLS 1.2+ (Let's Encrypt), HSTS preload, HTTP → HTTPS, TLS до Postgres/Redis в проде, Redis с паролем и без внешнего доступа |
| Заголовки | `Content-Security-Policy: default-src 'self'; script-src 'self'; img-src 'self' blob: <s3-домен>; connect-src 'self' wss://...; frame-ancestors 'none'`, `X-Content-Type-Options: nosniff`, `Referrer-Policy: strict-origin-when-cross-origin`, `Permissions-Policy` (камера/гео — выкл.), `Cross-Origin-Opener-Policy: same-origin` |
| Загрузки файлов | Presigned URL, белый список MIME + проверка сигнатуры, размер, ClamAV, удаление EXIF, случайные ключи, `Content-Disposition: attachment` для не-изображений, отдельный домен для выдачи файлов |
| Доступ к данным | Фильтр области в каждом репозитории, IDOR-тесты, Pydantic-валидация, только ORM/параметризованные запросы, ограничение размера страниц, экспорт — по праву + водяной знак |
| Бэкапы | PostgreSQL: WAL-G/pgBackRest — непрерывная архивация WAL (PITR) + ежедневный полный бэкап, хранение 30 дней ежедневных + 12 месячных, шифрование, копия вне основной площадки; S3 — версионирование; ежемесячный тест восстановления с протоколом; RPO ≤ 15 мин, RTO ≤ 4 ч |
| Разработка | CI: ruff, mypy, bandit, semgrep, pip-audit, npm audit, Trivy (образы), gitleaks; Dependabot; обязательный code review; секреты только в CI-хранилище |
| Персональные данные | Хранение на серверах в РК (закон РК «О персональных данных и их защите»), согласие на обработку ПД при регистрации/QR-тесте с версией, минимизация данных, сроки хранения, проверка юристом |
| Мониторинг | Sentry (без ПД), Prometheus + Grafana, алерты: ошибки доставки WA, рост 401/403/429, повторное использование refresh, падение вебхуков, бэкап не выполнен |

---

## 10. Этапы разработки

> Ориентировочные сроки — для команды 2 бэкенд + 2 фронтенд + 1 QA (+ 1 Flutter с этапа 7). ТЗ называет 1,5–3 месяца — для полного объёма с учётом решений заказчика (инбокс, чаты с родителями, строгая безопасность, правила платформы) это нереалистично; реальная оценка веба ≈ 5–6 месяцев, с мобильным ≈ 7–8. Каждый этап завершается демо заказчику и выкладкой на стенд.

### Этап 0. Фундамент (≈ 3 недели)
- **Что делаем:** монорепозиторий (`backend/`, `web/`, `mobile/` позже, `infra/`), docker compose (api, worker, scheduler, postgres, redis, minio, mailhog), CI (линтеры, типы, тесты, SAST, сканы зависимостей, сборка образов), стенды dev/stage; ядро FastAPI (конфиг, async-сессии, ошибки, пагинация, i18n-каркас), Alembic; модули `auth` (пароль + OTP + TOTP, JWT + ротация refresh, сессии/устройства), `users`, `rbac` (права, роли, назначения с областью, шаблоны ролей), `audit` (append-only, триггер, хэш-цепочка), `files`, `settings`; Vue: каркас SPA по прототипу (меню по правам, вход, 2FA, экран «Безопасность» и «Журнал», «Роли и доступы»), генерация API-клиента; бэкапы и мониторинг на stage.
- **Результат:** можно войти сотруднику с 2FA, ученику/родителю по OTP; супер-админ создаёт роли и назначает их с областью; все действия видны в журнале.
- **Критерии приёмки:** покрытие тестами auth/rbac/audit ≥ 85%; тест: `UPDATE/DELETE audit_log` от роли приложения и владельца приложения падает с ошибкой; повторное использование refresh отзывает семью; OTP-лимиты срабатывают; сотрудник без 2FA не может пользоваться системой; CI зелёный, Trivy/pip-audit без критичных; восстановление БД из бэкапа на stage выполнено.

### Этап 1. Ядро учёбы (≈ 5 недель)
- **Что делаем:** `org` (филиалы «Янги шахар», «Север», кабинеты, праздники), `academics` (уровни, цены с датами, группы, регулярное расписание, генерация уроков, конфликты, перенос/отмена/замена), `students` (карточка, родители, доверенные лица, статусы, история), `attendance` (окна, напоминания, задним числом), `billing` (пакеты, ledger, оплата базовая, списание, переводы с пересчётом, заморозки, долги), `progress` (оценки, ДЗ, комментарии, звёздочки), cron `generate_lessons`, `mark_students_left`, `attendance_reminders`, `lesson_finalize`. Экраны: Расписание (кабинеты/учителя/группы), Ученики, Карточка ученика, Группы, Посещаемость, Уровни и цены.
- **Результат:** школа ведёт расписание и посещаемость, баланс уроков считается автоматически.
- **Критерии приёмки:** невозможно создать пересечение кабинета/учителя (тест на уровне БД и API); перевод 4 × 3 000 → уровень 4 000 даёт 3 урока, 13 000 → 3 урока + 1 000 тг; перевод отражается в истории и аудите; учитель не может изменить отметку на следующий день, админ — может с причиной; пропуск без причины списывается согласно настройке; ученик без оплат/посещений 90 дней получает «Ушёл»; страница расписания недели филиала открывается < 2 с на тестовых данных 5 000 учеников.

### Этап 2. CRM + инбокс Instagram/WhatsApp + QR-тест (≈ 4 недели)
- **Что делаем:** `crm` (воронки основная/«Возврат», канбан, события, задачи по лиду, отказы, пробные в расписание, KPI-события), `inbox` (вебхуки Meta с подписью, каналы WA/IG, автосоздание контакта и лида, дубли/слияние, назначение, окно 24 ч, быстрые ответы, медиа), `tests` (конструктор, placement-шкалы, QR-коды филиалов, публичная страница), продажа офис-менеджером (мастер оплаты, первая оплата → ученик), зависшие лиды. Экраны: Воронка продаж, Входящие, Карточка лида, QR-тест, Конструктор тестов, Аналитика CRM.
- **Результат:** каждое новое сообщение в Instagram/WhatsApp появляется в инбоксе и создаёт лид; QR-тест создаёт лид с уровнем.
- **Критерии приёмки:** вебхук без валидной подписи → 401 и ничего не создаётся; повтор одного webhook не создаёт дубль; второй контакт с тем же телефоном не создаёт второй лид; вне окна 24 ч WA нельзя отправить свободный текст; отметка «Пришёл» на пробном переводит лид и создаёт ровно одно начисление продажнику (повторная отметка/правка не дублирует); продажник получает 403 на оформление оплаты; QR-тест работает на телефоне без входа, результат прикрепляется к существующему лиду по номеру.

### Этап 3. Чаты + уведомления/шаблоны WhatsApp (≈ 4 недели)
- **Что делаем:** `chats` (групповые автоматически, личные, родители по матрице, файлы/фото/голосовые, закрепы, прочтения, непрочитанные, просмотр для контроля с аудитом), WebSocket-шлюз с Redis pub/sub, `notifications` (шаблоны ru/kk с переменными, согласование шаблонов в Meta, outbox, повторы, журнал доставки, in-app, Web Push), события: отсутствие, оплата, мало уроков, долг, перенос/отмена, покупка книги, опционально пришёл/опоздал. Экраны: Чаты, Настройки чатов («Кто с кем»), Шаблоны уведомлений, Журнал доставки.
- **Результат:** учителя, ученики и родители переписываются по правилам; родители получают WhatsApp-уведомления автоматически.
- **Критерии приёмки:** попытка ученика создать личный чат с другим учеником / родителя с чужим родителем → 403 при любых настройках ролей; при переводе ученик исчезает из старого группового чата и появляется в новом; сообщение доставляется по WS на другой инстанс API < 1 с; «Не пришёл» → WA родителю ≤ 1 мин; при ошибке провайдера — 5 повторов и уведомление админу; просмотр чата админом виден в журнале.

### Этап 4. Финансы + зарплата/KPI + задачи (≈ 4 недели)
- **Что делаем:** `finance` (кассы, доходы, расходы, категории, регулярные, распределение общих, скидки/промокоды, возвраты с утверждением, P&L, движение денег, долги, дашборд владельца, экспорт Excel/PDF, IP-ограничение финансов), `payroll` (ставки с датами, начисления в реальном времени, удержание в конце месяца, ручные премии/удержания, утверждение, выплата → расход, сторно), `tasks` (полный модуль, повторяющиеся, отчёты), KPI-рейтинги. Экраны: Финансы, P&L, Расходы, Ведомость, Мои начисления, Рейтинг, Задачи.
- **Результат:** месяц закрывается в системе: P&L, ведомость с расшифровкой, задачи.
- **Критерии приёмки:** урок с 8 присутствующими → 2 800 тг учителю, с 5 → 2 500; смена ставки с 1-го числа не меняет прошлые начисления; возврат оплаты создаёт сторно бонусов продажи и удержания (в следующем периоде, если текущий утверждён); один факт — один бонус (тест на гонку параллельных запросов); выплата ведомости создаёт расход «Зарплата»; P&L по филиалам сходится с суммой оплат и расходов; экспорт содержит водяной знак и попадает в журнал.

### Этап 5. Книги, коины, магазин, база обучения, жалобы/согласия (≈ 4 недели)
- **Что делаем:** `books` (каталог, склады, приход → расход, перемещения с подтверждением, списания, продажи → доход + WA, отчёты), `coins` (правила, авто-начисления, лимиты учителей, списания, магазин, заказы с резервом, рейтинги, бейджи), `training` (курсы, видео, документы, тесты, прогресс), `compliance` (версии правил и согласий, обязательное принятие, отзыв, жалобы с SLA и апелляцией, заявки учеников), `staff_time` (приход/уход, ежедневный отчёт), методист (оценка уроков), ежемесячные отзывы, блокировка при неоплате. Экраны: Книги, Коины и магазин, База обучения, Жалобы, Согласия (отчёт «кто не подписал»), Табель сотрудников.
- **Результат:** покрыты все модули ТЗ и требования Правил.
- **Критерии приёмки:** продажа книги уменьшает остаток филиала и создаёт доход; перемещение не увеличивает остаток получателя до подтверждения; отмена заказа возвращает коины; учитель не может превысить лимит; без принятых правил пользователь видит только экран правил; новая версия правил вступает не раньше чем через 7 дней; фигурант жалобы не видит её через любой API; ученик с неоплатой > 5 дней блокируется и разблокируется оплатой; отметка прихода вне сети филиала отклоняется.

### Этап 6. Кабинеты ученика и родителя, i18n, импорт, нагрузка, аудит безопасности (≈ 4 недели)
- **Что делаем:** веб-кабинеты ученика и родителя (адаптив, переключение детей, баланс, ДЗ, оценки, звёздочки, отзывы, оплаты/чеки, чаты, коины, магазин, книги, жалобы, заявки), полный перевод интерфейса и шаблонов на казахский, импорт из Excel (ученики, родители, группы, остатки уроков) с предпросмотром, валидацией и откатом, нагрузочное тестирование (k6/Locust: 5 000 учеников, 300 одновременных пользователей, 50 WS-сообщений/с), внешний аудит безопасности/пентест (OWASP ASVS L2), исправления, документация API и админ-инструкции, материалы в базу обучения.
- **Результат:** веб-версия готова к пилоту в одном филиале.
- **Критерии приёмки:** p95 основных страниц < 2 с, p95 API < 300 мс при целевой нагрузке; импорт тестового Excel заказчика без ручных правок в БД, отчёт об ошибках по строкам; 100% строк интерфейса переведены на kk; пентест без критичных и высоких уязвимостей (или они закрыты); родитель видит только своих детей (автотесты IDOR по всем эндпоинтам кабинета).

### Этап 7. Flutter iOS + Android (≈ 6 недель)
- **Что делаем:** одно приложение для ученика и родителя (роль определяется после входа), вход по OTP, secure storage, расписание, баланс, ДЗ с загрузкой файлов, оценки/тесты, чаты с WS и голосовыми, push (FCM/APNs) с deep links, коины/магазин, книги, жалобы, правила/согласия, ru/kk, тёмная тема; certificate pinning (опционально), jailbreak/root-предупреждение; публикация в App Store и Google Play (аккаунты разработчика заказчика).
- **Результат:** приложения опубликованы.
- **Критерии приёмки:** все сценарии ученика/родителя веба доступны в приложении; push о «Не пришёл»/новом сообщении приходит ≤ 1 мин; приложение прошло ревью сторов; crash-free ≥ 99,5% на бете (TestFlight / internal testing, 20+ пользователей).

### Этап 8. Запуск (≈ 2–3 недели)
- **Что делаем:** перенос боевых данных (импорт), сбор согласий и принятия правил у действующих учеников и сотрудников до запуска, обучение сотрудников по ролям (база обучения + очные сессии), пилот в одном филиале (1–2 недели), затем второй филиал, дежурство разработчиков, прод-мониторинг, регламент бэкапов, передача документации.
- **Результат:** оба филиала работают в платформе.
- **Критерии приёмки:** 100% активных учеников импортированы и сверены по балансу с Excel; ≥ 95% согласий собрано (остальные — в отчёте админу); первый месяц закрыт в системе (ведомость, P&L); критичных инцидентов нет 2 недели подряд; тест восстановления из бэкапа в проде выполнен.

---

## 11. Экраны веб-приложения по ролям

**Общие (все сотрудники):** Вход (пароль + 2FA) · Мой профиль · Безопасность: 2FA, сессии и устройства · Уведомления · Мои задачи · Мои начисления и KPI · База обучения · Жалобы и предложения · Отметка прихода/ухода · Ежедневный отчёт · Принятие правил/согласия · Глобальный поиск.

**Супер-админ / Операционный директор:** Дашборд сети (выручка, прибыль, активные, лиды, должники, зависшие лиды) · Переключатель филиала · Филиалы и кабинеты · Сотрудники · Роли и доступы (конструктор, матрица чатов) · Безопасность (политики, IP-список финансов, маскирование, бэкапы, экспорт) · Журнал действий · Настройки (уровни и цены, ставки и бонусы, правила коинов, сроки/лимиты, уведомления) · Шаблоны WhatsApp · Каналы Instagram/WhatsApp · Конструктор тестов и QR-коды · Правила и согласия (версии, отчёт «кто не подписал») · Жалобы (все, апелляции) · Все отчёты · P&L · Просмотр чатов · Импорт из Excel · Задачи всем.

**Админ филиала:** Дашборд филиала · Расписание (кабинеты/учителя/группы) · Группы · Ученики и карточка · Посещаемость (включая задним числом) · Переводы и заморозки · Заявки учеников · Оплаты и возвраты · Финансы филиала, расходы · Ведомость (утверждение) · Книги (склад) · Коины и магазин · Задачи филиала · Просмотр чатов филиала · Жалобы филиала · Табель сотрудников · Согласия филиала.

**Офис-менеджер:** CRM (лиды после пробного) · Входящие · Оформление продажи / приём оплаты · Ученики (карточка, баланс, договор, согласие) · Книги (продажа) · Выдача заказов магазина · Чаты с родителями (если разрешено) · Расписание филиала.

**Отдел продаж:** Воронка продаж (свои лиды) · Воронка «Возврат» · Входящие (свои диалоги) · Карточка лида (звонки, задачи, запись на пробный) · Расписание (просмотр, свободные места) · Аналитика своих конверсий.

**SMM:** Входящие Instagram/WhatsApp · Передача лида продажнику · Быстрые ответы · SLA-отчёт.

**Методист:** Учителя и их уроки · Оценка уроков по критериям · KPI учителей · Финальные тесты · База обучения (редактирование).

**Бухгалтер:** Финансы, расходы, кассы · P&L · Ведомости · Экспорт.

**Учитель:** Моё расписание · Мои группы · Посещаемость урока (пробные, блокировки, согласия) · Оценки, ДЗ, проверка ДЗ · Звёздочки · Ежемесячные отзывы · Финальные тесты (ручная проверка) · Чаты (группы, ученики, родители) · Начисление коинов (лимит) · Мои начисления и KPI.

**Ученик (веб):** Главная · Расписание · ДЗ (сдача) · Оценки и тесты · Баланс уроков · Чаты (группа, учитель, администратор) · Коины, магазин, рейтинги, бейджи · Мои книги · Оценка урока · Заявки (смена группы, филиала, заморозка, досрочный final, «не приду») · Жалобы · Правила и согласия.

**Родитель (веб):** Выбор ребёнка · Посещаемость · Оценки, комментарии, звёздочки, ежемесячные отзывы · ДЗ · Тесты · Оплаты, чеки, остаток уроков, задолженность (онлайн-оплата — позже) · Книги и коины ребёнка · Чаты с учителем/администратором · Доверенные лица для забора · Согласия за ребёнка · Жалобы · Настройки уведомлений.

**Публичные:** QR-тест уровня · Вход по телефону (OTP) · Политика обработки персональных данных.

---

## 12. Вопросы к заказчику (с предлагаемым допущением)

| № | Вопрос | Допущение, если ответа нет |
|---|---|---|
| 1 | Есть ли верифицированный Meta Business Manager, отдельный номер для WhatsApp Business Platform (не используемый в обычном приложении WhatsApp), Instagram @1eng.kz — профессиональный аккаунт, привязанный к странице Facebook? Один номер на сеть или по номеру на филиал? | Заказчик регистрирует Meta Business и проходит верификацию на этапе 0; один WA-номер на сеть с маршрутизацией по филиалу, один Instagram-аккаунт; доступы передаются нам как администратору приложения |
| 2 | Хостинг и домен: где размещаем (закон РК требует хранить ПД граждан РК на территории РК)? Какой домен (напр. `app.1eng.kz`)? | VPS/облако в Казахстане (PS Cloud / Kazteleport или аналог), домен `1eng.kz` с поддоменами `app.` и `api.`; оплата хостинга — заказчик |
| 3 | SMS-провайдер для резервного OTP? | Mobizon или SMSC.kz; основной канал OTP — WhatsApp |
| 4 | Нужна ли онлайн-оплата Kaspi (Kaspi Pay/QR) и эквайринг на старте? Есть ли договор с банком? Нужны ли фискальные чеки (онлайн-ККМ)? | На запуске — без онлайн-оплаты, способ «Kaspi» фиксируется вручную; PDF-квитанция платформы; онлайн-оплата и фискализация — после запуска |
| 5 | Одно Flutter-приложение для ученика и родителя или два отдельных? | Одно приложение, роль определяется после входа; если у номера обе роли — переключатель |
| 6 | Подтвердить числа из Правил: предупреждение о пропуске 3 ч, опоздание 15 мин = пропуск, блокировка через 5 дней неоплаты, заморозка ≤ 1 мес. и сколько раз за курс, хранение записей 30 дней, отметка посещаемости за 10 мин, ДЗ до 22:00, проверка 48 ч | Все значения как в Правилах, вынесены в настройки; заморозка — 1 раз за курс |
| 7 | Противоречие: Правила — «возврат денег не предусмотрен», ТЗ — «возвраты с причиной и пересчётом баланса, отмена бонусов» | Функция возврата есть, но только по праву `payments.refund` (по умолчанию — супер-админ) с утверждением; бонусы отменяются по ТЗ |
| 8 | SLA ответа в инбоксе: Правила SMM — 2 ч, прототип — «зависшие > 30 мин», отдел продаж — обработка заявки за 1 ч | Предупреждение оператору через 30 мин, «зависший» и эскалация руководителю — через 1 ч, нарушение SLA SMM — через 2 ч (все настраивается) |
| 9 | Пробный урок бесплатный или платный? Если платный — засчитывается ли в курс? | Бесплатный по умолчанию; переключатель «платный» с ценой, при покупке курса стоимость засчитывается |
| 10 | Пропуск без уважительной причины — списывать урок по умолчанию? | Да, списывать (Правила: «пропущенный без предупреждения урок считается проведённым»); пропуск с предупреждением за ≥ 3 ч — не списывается |
| 11 | Входят ли «Опоздал» и пришедшие пробные ученики в N для формулы учителя (2 500 + 100 × (N − 5))? | «Опоздал» — входит; пробные — входят (стимулирует удержание) |
| 12 | Проходной балл финального теста для перехода на следующий уровень (бонус учителю — > 100 из 150)? | Проходной — 100 из 150; бонус — строго больше 100 |
| 13 | Учитывается ли денежный остаток ученика при переводе на уровень с другой ценой? | Да: стоимость = оставшиеся уроки × цена + денежный остаток |
| 14 | Должны ли родители видеть групповой чат ребёнка или иметь отдельный чат родителей группы? | Нет: родители не в групповых чатах (защита детей); только личные чаты с учителем/админом |
| 15 | Как отмечается приход сотрудников: только из Wi-Fi филиала, QR на ресепшене или геолокация? | IP-сеть филиала + резервный динамический QR на ресепшене |
| 16 | Нужна ли интеграция с камерами видеонаблюдения или достаточно согласий и ручного прикрепления фрагментов к жалобам? | Без интеграции; фрагменты прикрепляет администратор |
| 17 | Как распределять общие расходы сети между филиалами? | Пропорционально выручке филиала за месяц (переключаемо: по ученикам / поровну) |
| 18 | Формат текущей базы в Excel (какие колонки, есть ли остатки уроков и долги)? Можно получить образец? | Получаем образец на этапе 1, делаем шаблон импорта; остатки переносятся одной записью «начальный баланс» |
| 19 | Нужны ли роли «Операционный директор», «Методист», «SMM», «Бухгалтер» как шаблоны (упомянуты в Правилах, нет в ТЗ)? | Да, создаём как редактируемые шаблоны |
| 20 | Месячный лимит коинов учителя и суммы авто-начислений? | Лимит 200 коинов/мес. на учителя; посещение 5, ДЗ 5, месяц без пропусков 50, финальный тест 100, ДР 50, приведённый друг 200 |
| 21 | Сайт: есть ли форма заявки, откуда брать лиды «Сайт»? | Даём простой webhook/виджет формы, подключение к текущему сайту — силами заказчика |
| 22 | Кто проверяет тексты согласия, договора и обработки ПД юридически? | Заказчик привлекает юриста до этапа 5; мы реализуем версионирование, тексты подставляются из админки |
| 23 | Аккаунты Apple Developer и Google Play — на кого регистрируются? | На юрлицо заказчика (нужен D-U-N-S для Apple), регистрация начинается на этапе 5 |
| 24 | Срок: ТЗ — 1,5–3 месяца, реальный объём больше (инбокс, чаты с родителями, Правила). Согласовать поэтапный запуск? | Пилот веба после этапа 6 (~5–6 мес.), мобильное — ещё ~1,5 мес.; приоритетные модули могут быть выведены в работу раньше по готовности этапа |
