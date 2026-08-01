# Telegram Bot AI Guide — compressed edition

Короткая версия руководства для ИИ. Цель — снизить токены без потери практической пользы.

## 1. Core rules

1. Сначала понять цель бота, потом писать код.
2. Не строить enterprise-архитектуру без причины.
3. Разделять handlers, services, storage, integrations.
4. Кнопки и state проектировать до кода.
5. Не хранить секреты в коде.
6. Проверять права, входные данные, callback_data и повторные действия.
7. Учитывать Telegram UX, а не только backend-логику.
8. Для сложных сценариев использовать явный state/FSM.
9. Для каждого критичного сценария предусматривать ошибки, retry и rollback/neutral state.
10. Код должен быть расширяемым, но без лишних абстракций.

## 2. Before code

Перед генерацией кода ИИ должен определить:

- цель бота;
- тип чатов: private, group, inline;
- роли пользователей;
- 5–10 главных сценариев;
- нужна ли БД;
- нужен ли state/FSM;
- нужны ли оплаты, AI, web app, deep links;
- какие внешние API используются;
- какие сущности реально нужны.

Минимальный output перед кодом:

- краткая архитектура;
- список модулей;
- сценарии;
- кнопки;
- state strategy;
- data/storage strategy.

## 3. Architecture chooser

### MVP

Использовать, если бот простой, без сложного состояния, оплат и тяжёлых интеграций.

```text
telegram-bot/
├─ main.py
├─ handlers/
├─ keyboards/
├─ services/
├─ config.py
└─ .env
```

### Standard production

Использовать, если есть AI, CRM, заказы, роли, состояния, платежи, длительная поддержка.

```text
telegram-bot/
├─ app/
│  ├─ bot/handlers/
│  ├─ bot/keyboards/
│  ├─ bot/formatters/
│  ├─ services/
│  ├─ repositories/
│  ├─ integrations/
│  ├─ db/
│  └─ config/
├─ tests/
├─ migrations/
└─ main.py
```

### Growth / high-load

Нужен только если есть несколько инстансов, webhook, очередь, фоновые задачи, высокая нагрузка.

## 4. Layer rules

### Handler

Handler должен:

- принять update;
- извлечь user/chat/context;
- проверить базовые права и state;
- вызвать service/use case;
- вызвать formatter и keyboard builder;
- вернуть Telegram-friendly ответ.

Handler не должен содержать:

- тяжёлую бизнес-логику;
- SQL;
- длинную оркестрацию нескольких внешних сервисов;
- хаотичную сборку кнопок.

### Service

Тут живут сценарии:

- register user;
- create order;
- add to cart;
- generate AI answer;
- apply business rules.

### Repository

Тут живёт работа с:

- DB;
- Redis;
- state storage;
- cache.

### Integration

Отдельные клиенты для:

- LLM;
- payments;
- CRM;
- email/SMS;
- external APIs.

### Formatter

Отвечает за:

- message text;
- summaries;
- error text;
- captions;
- localization.

## 5. Telegram specifics

ИИ обязан учитывать:

- разные типы update требуют разных handlers;
- `callback_data` ограничена по длине;
- форматирование Markdown/HTML ограничено;
- длинные сообщения плохо читаются;
- старые кнопки могут быть нажаты позже;
- один и тот же update может прийти повторно;
- group и private chat требуют разной логики;
- privacy mode влияет на поведение бота в группах;
- deep link payload должен валидироваться;
- inline mode — это отдельный UX режим.

## 6. State and FSM

Используй FSM или другой явный state-механизм, если есть:

- регистрация по шагам;
- анкета;
- checkout;
- wizard flow;
- AI-режим с последовательными шагами.

Можно без тяжёлого FSM, если:

- бот mostly stateless;
- команды независимы;
- шаги легко описываются статусом в БД;
- достаточно simple scene/wizard abstraction.

Обязательно при любом подходе:

- хранить текущий шаг или его эквивалент;
- уметь отменять сценарий;
- уметь обрабатывать сломанное состояние;
- возвращать пользователя в neutral state после завершения.

## 7. Buttons

### Reply keyboard

Использовать, если нужно простое постоянное меню и крупные действия.

### Inline keyboard

Использовать, если действие относится к сообщению, объекту, пагинации, фильтрам, подтверждению.

### Rule

Не существует правила “always inline”. Выбирать по UX.

Обычно заранее продумываются:

- Назад;
- Главное меню;
- Отмена;
- Обновить;
- Следующая/предыдущая страница;
- Подтвердить / отменить действие.

## 8. Callback data

Хорошие схемы:

```text
action:entity:id
v1:action:entity:id
```

Требования:

- короткая;
- валидируемая;
- без секретов;
- при необходимости версионируемая.

Нельзя класть в `callback_data`:

- токены;
- большие JSON;
- чувствительные данные;
- всё, что невозможно перепроверить на сервере.

Нужно предусмотреть:

- stale callbacks;
- повторные нажатия;
- удалённый объект;
- отсутствие доступа.

## 9. Edit vs new message

Редактировать сообщение удобно для:

- пагинации;
- меню;
- фильтров;
- шагов wizard.

Отправлять новое лучше для:

- результата операции;
- длинного контента;
- критического уведомления;
- случаев, где важна история.

Правило: редактирование уменьшает шум, но не должно ломать понятность.

## 10. Storage chooser

### Без БД

Подходит для utility-ботов, простых команд и notification bots.

### SQLite

Подходит для маленького MVP и локальных ботов.

### PostgreSQL

Основной выбор для normal production.

### Redis

Использовать для cache, throttling, locks, ephemeral state, idempotency markers. Не обязательно как основную БД.

Минимум по пользователю:

- telegram_user_id;
- name/username;
- role;
- language;
- current state или equivalent status;
- created_at/updated_at.

## 11. AI / LLM module

Выделять отдельно:

- model client;
- prompt builder;
- context manager;
- memory strategy;
- moderation/safety;
- output post-processing.

Контролировать:

- token cost;
- latency;
- fallback при timeout;
- ограничения контекста;
- Telegram-friendly formatting.

Память нужна не всегда. Часто хватает:

- последних N сообщений;
- summary;
- user facts;
- RAG.

## 12. Security

Главное:

- секреты не в коде;
- локально `.env`, в production secret storage;
- проверка входа, прав, callback_data и ownership;
- rate limiting;
- throttling;
- webhook protection;
- idempotency;
- маскирование чувствительных данных в логах.

Нельзя:

- логировать токены;
- выполнять admin action только по кнопке без серверной проверки;
- доверять входу без валидации;
- повторять критичные операции без контроля.

## 13. Errors and resilience

Типы ошибок:

- user error;
- business error;
- storage error;
- integration error;
- Telegram API error;
- timeout;
- stale callback;
- expired state.

Пользователь должен получать:

- короткое понятное сообщение;
- следующий шаг;
- кнопку возврата или перезапуска.

Примеры:

- «Не удалось получить данные. Попробуйте ещё раз.»
- «Эта кнопка устарела. Обновить экран?»
- «Сессия истекла. Начнём заново.»

## 14. Webhook and polling

### Polling

Подходит для локальной разработки, тестов и маленьких ботов.

### Webhook

Подходит для production.

### Important

Критичные операции должны быть идемпотентными: повторный update не должен создавать дубль заказа, дубль платежа или повторное чувствительное действие.

## 15. Logging and tests

Логировать:

- типы update;
- бизнес-действия;
- ошибки;
- внешние API вызовы;
- state transitions;
- admin actions.

Тестировать минимум:

- service logic;
- validators;
- formatters;
- callback parsing/building;
- state transitions;
- ключевые сценарии `/start`, back, cancel, stale callback, invalid payload, role checks.

## 16. Anti-patterns

- giant single file;
- business logic in handlers;
- keyboards inside every handler;
- chaotic callback_data;
- overengineering for small bot;
- no stale callback handling;
- no tests on critical flows;
- hardcoded secrets.

## 17. Master prompt

```text
Создай Telegram-бота как practical engineer.
Сначала кратко определи цель, пользователей, сценарии, типы update, сущности, storage strategy, state/FSM strategy и архитектуру нужного масштаба: MVP, standard production или growth.
Потом опиши кнопки, callback_data, обработку stale callbacks, ошибки, безопасность и поток данных.
После этого пиши код по модулям.
Не переусложняй архитектуру без причины.
```

## 18. Ultra-short checklist

Перед кодом проверить:

- цель понятна;
- сценарии понятны;
- выбран тип архитектуры;
- state strategy определена;
- callback_data strategy определена;
- storage выбран осознанно;
- ошибки и retry продуманы;
- idempotency учтена;
- Telegram UX учтён.
