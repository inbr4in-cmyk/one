# Подключение WhatsApp и Instagram (Meta)

Все сообщения клиентов приходят в «Входящие» платформы и автоматически становятся лидами.
Секреты вводятся только на сервере скриптом `deploy/meta-setup.sh`, в чат их не присылать.

## 1. Что взять в панели Meta (приложение OneEnglish)

| Значение | Где найти |
|---|---|
| App Secret | Настройки приложения → Основное → «Секрет приложения» → Показать |
| Постоянный токен | business.facebook.com → Настройки компании → Пользователи → Системные пользователи → Добавить (роль Администратор) → Назначить активы: приложение OneEnglish, аккаунт WhatsApp, страница Facebook → «Создать маркер», срок «Никогда», разрешения: `whatsapp_business_messaging`, `whatsapp_business_management`, `instagram_basic`, `instagram_manage_messages`, `pages_messaging`, `pages_manage_metadata`, `pages_show_list`, `business_management` |
| Phone number ID | WhatsApp → Настройка API (API Setup) → под номером «Идентификатор номера телефона» |
| WhatsApp Business Account ID | там же, «Идентификатор аккаунта WhatsApp Business» |
| ID страницы Facebook | страница школы, к которой привязан Instagram школы → «Информация» → «Прозрачность страницы» (или Meta Business Suite → Настройки) |

Instagram школы должен быть профессиональным (бизнес) и привязан к этой странице Facebook.
ID Instagram-аккаунта и токен страницы скрипт получит сам.

## 2. Запустить скрипт на сервере

В PowerShell на своём компьютере:

```powershell
ssh -t root@89.126.198.159 "curl -fsSLo /root/meta-setup.sh https://raw.githubusercontent.com/inbr4in-cmyk/one/main/deploy/meta-setup.sh && bash /root/meta-setup.sh english.inbrain.kz"
```

Скрипт:
1. покажет **Callback URL** (`https://english.inbrain.kz/api/webhooks/meta`) и **Verify token**;
2. спросит значения из таблицы (секреты при вводе не видны);
3. проверит токен, подпишет приложение на WhatsApp-аккаунт и страницу;
4. сохранит всё в `/etc/one-english/env` (с резервной копией), перезапустит платформу.

Переменные: `OE_META_APP_SECRET`, `OE_WA_ACCESS_TOKEN`, `OE_WA_PHONE_NUMBER_ID`, `OE_WA_WABA_ID`,
`OE_IG_PAGE_ID`, `OE_IG_ACCESS_TOKEN`. `OE_META_VERIFY_TOKEN` уже создан при установке.

## 3. Вебхуки в панели Meta

- **WhatsApp → Конфигурация → Веб-хук → Изменить**: Callback URL и Verify token из шага 2 → «Подтвердить и сохранить» → поле `messages` → Подписаться.
- **Instagram** (сценарий «Управление сообщениями в Instagram», вариант «через вход Facebook», или продукт «Веб-хуки» → объект Instagram): тот же URL и токен → поле `messages` → Подписаться.

## 4. Проверка и ограничения

- Пока приложение в режиме разработки, сообщения приходят только от людей с ролью в приложении и от тестовых номеров WhatsApp.
- Для реальных клиентов: подтвердить компанию (верификация бизнеса), перевести приложение в режим Live, для Instagram получить расширенный доступ `instagram_manage_messages` через App Review.
- Настоящий номер школы: добавить в WhatsApp Manager. Если номер сейчас работает в приложении WhatsApp Business, при добавлении выбрать подключение с сохранением приложения (coexistence), иначе приложение на телефоне перестанет работать.
- Ответ клиенту в WhatsApp обычным текстом возможен 24 часа после его сообщения; позже только шаблоном (раздел «Шаблоны сообщений»).
