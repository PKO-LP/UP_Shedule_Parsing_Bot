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

# Замените этот токен на ваш собственный, полученный от @BotFather
TOKEN = "ТОКЕН"

# Инициализируем диспетчер
dp = Dispatcher()

# Обработчик команды /start
@dp.message(CommandStart())
async def command_start_handler(message: Message) -> None:
    await message.answer(f"Привет, {html.bold(message.from_user.full_name)}! Я бот на aiogram 3.14.")

# Обработчик команды /help
@dp.message(Command("help"))
async def command_help_handler(message: Message) -> None:
    await message.answer("Я умею отвечать на команды /start и /help, а также повторять твои сообщения!")

# Обработчик любого текста (эхо-бот)
@dp.message()
async def echo_handler(message: Message) -> None:
    try:
        # Отправляем копию полученного сообщения обратно пользователю
        await message.send_copy(chat_id=message.chat.id)
    except TypeError:
        # Если тип сообщения не поддерживается для копирования
        await message.answer("Упс! Я умею повторять только текст.")

async def main() -> None:
    # Используем Cloudflare Worker как прокси для работы без VPN в РФ
    session = AiohttpSession(
        api=TelegramAPIServer.from_base("https://воркер_ссылка")
    )
    # Настраиваем параметры бота, включая дефолтный режим разметки текста (HTML)
    bot = Bot(token=TOKEN, session=session, default=DefaultBotProperties(parse_mode=ParseMode.HTML))

    # Удаляем webhook если он был установлен, чтобы polling работал корректно
    await bot.delete_webhook(drop_pending_updates=True)

    # Запускаем опрос сервера Telegram (long polling)
    await dp.start_polling(bot)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, stream=sys.stdout)
    asyncio.run(main())
