# Запуск Telegram-бота в России без VPN через Cloudflare Workers

## Что это и зачем

Telegram заблокирован в РФ на уровне провайдеров. Cloudflare не заблокирован, поэтому мы создаём бесплатный прокси-воркер: твой бот → Cloudflare → api.telegram.org.

**Бесплатный лимит:** 100 000 запросов/день — для большинства ботов хватает с запасом.

---

## Шаг 1 — Получи токен бота

1. Открой Telegram, найди **@BotFather**
2. Отправь `/newbot`, следуй инструкциям
3. Скопируй токен вида `1234567890:AABBccDDeeFFggHH...`

---

## Шаг 2 — Зарегистрируйся в Cloudflare

Перейди на [cloudflare.com](https://cloudflare.com) → **Sign Up** → регистрируйся (только email + пароль, домен не нужен).

<img width="1519" height="727" alt="image" src="https://github.com/user-attachments/assets/3e74a9e5-4e1a-4db8-b070-abf611ce9b59" />


---

## Шаг 3 — Создай Worker

1. В левом меню нажми **Compute → Workers & Pages**
2. Нажми **Create application**

<!-- 📸 СКРИНШОТ: страница Workers & Pages с кнопкой Create application -->

3. Выбери **Start with Hello World!**

<img width="321" height="102" alt="image" src="https://github.com/user-attachments/assets/f902d0aa-da1c-442d-b9a0-94ba8fcebc34" />
<img width="1587" height="685" alt="image" src="https://github.com/user-attachments/assets/9ccecf94-2af9-42c6-9f2e-da31a7364d65" />


4. Название воркера оставь как есть (или придумай своё)
5. Нажми **Deploy** — не трогай код на этом этапе

<img width="1419" height="691" alt="image" src="https://github.com/user-attachments/assets/47b83bc3-f960-4dc0-9636-8099328e23e4" />
<img width="642" height="665" alt="image" src="https://github.com/user-attachments/assets/d7a40f6b-41b2-46b1-b3e1-e89b1b0d7b95" />


---

## Шаг 4 — Замени код воркера

1. После деплоя нажми **Edit code** (правый верхний угол)

<img width="1539" height="748" alt="image" src="https://github.com/user-attachments/assets/2d2fd5d8-c790-4c12-b4a0-030f65333ad6" />


2. Выдели весь код в редакторе (**Ctrl+A**) и удали его
3. Вставь следующий код:

```js
export default {
  async fetch(request) {
    const url = new URL(request.url);
    url.hostname = "api.telegram.org";
    const newRequest = new Request(url, request);
    return fetch(newRequest);
  }
};
```

<img width="1596" height="761" alt="image" src="https://github.com/user-attachments/assets/32ed8dd6-4bfe-465c-bc8b-bc38045ee2f1" />
<img width="1601" height="762" alt="image" src="https://github.com/user-attachments/assets/8f3752f2-f1d9-455a-b90b-d88b9a0e229a" />



4. Нажми **Deploy**

---

## Шаг 5 — Запомни адрес своего воркера

После деплоя на странице Overview в правом нижнем углу (**Domains & Routes**) будет адрес вида:

```
your-worker-name.your-account.workers.dev
```

Скопируй его — он понадобится в коде бота.

<!-- 📸 СКРИНШОТ: Overview с адресом воркера в разделе Domains & Routes -->

---

## Шаг 6 — Настрой бота

Установи зависимости:

```bash
pip install aiogram>=3.0
```

Код бота (`bot.py`):

```python
import asyncio
import logging
import sys
from aiogram import Bot, Dispatcher, html
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.telegram import TelegramAPIServer
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart, Command
from aiogram.types import Message

TOKEN = "ВАШ_ТОКЕН_ОТ_BOTFATHER"
WORKER_URL = "https://your-worker-name.your-account.workers.dev"

dp = Dispatcher()

@dp.message(CommandStart())
async def command_start_handler(message: Message) -> None:
    await message.answer(f"Привет, {html.bold(message.from_user.full_name)}!")

@dp.message(Command("help"))
async def command_help_handler(message: Message) -> None:
    await message.answer("Я умею отвечать на /start и /help, а также повторять сообщения.")

@dp.message()
async def echo_handler(message: Message) -> None:
    try:
        await message.send_copy(chat_id=message.chat.id)
    except TypeError:
        await message.answer("Упс! Я умею повторять только текст.")

async def main() -> None:
    session = AiohttpSession(
        api=TelegramAPIServer.from_base(WORKER_URL)
    )
    bot = Bot(token=TOKEN, session=session, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, stream=sys.stdout)
    asyncio.run(main())
```

Замени:
- `ВАШ_ТОКЕН_ОТ_BOTFATHER` → твой токен
- `your-worker-name.your-account.workers.dev` → адрес твоего воркера

---

## Шаг 7 — Запуск

```bash
python bot.py
```

В логах должно появиться:
```
INFO:aiogram.dispatcher:Start polling
INFO:aiogram.dispatcher:Run polling for bot @имя_бота ...
```

Без ошибок — бот работает через Cloudflare без VPN.

---

## Возможные проблемы

| Ошибка | Причина | Решение |
|--------|---------|---------|
| `Conflict: terminated by other getUpdates` | Запущено два экземпляра бота | Закрой все терминалы с ботом, запусти один |
| `Conflict: can't use getUpdates while webhook is active` | Был установлен webhook | Уже решено в коде через `delete_webhook()` |
| `ImportError: cannot import name 'html'` | Старая версия aiogram (2.x) | `pip install aiogram>=3.0 --upgrade` |
