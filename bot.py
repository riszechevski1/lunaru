
import asyncio
import os
import sqlite3
import html

from dotenv import load_dotenv

from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart, Command
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)


# ==========================================
# НАСТРОЙКИ
# ==========================================

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))

if not BOT_TOKEN or not ADMIN_ID:
    raise RuntimeError("Проверь BOT_TOKEN и ADMIN_ID в файле .env")

DB_NAME = "lunaris.db"

STATUSES = {
    "new": "Новый",
    "progress": "В работе",
    "done": "Выполнен",
}

STATUS_EMOJI = {
    "Новый": "🆕",
    "В работе": "🔄",
    "Выполнен": "✅",
}


# ==========================================
# УСЛУГИ
# ==========================================

SERVICES = {
    "question": {
        "name": "Ответ на конкретный вопрос",
        "price": 299,
        "description": (
            "Персональный расклад на один вопрос. "
            "Подходит для тем любви, отношений, работы, "
            "финансов и других жизненных ситуаций."
        ),
    },

    "general": {
        "name": "Общий расклад",
        "price": 599,
        "description": (
            "Развёрнутый анализ текущей ситуации, "
            "важных обстоятельств, возможностей "
            "и ближайших перспектив."
        ),
    },
}


# ==========================================
# СОСТОЯНИЯ
# ==========================================

class OrderStates(StatesGroup):
    waiting_question = State()


class AdminStates(StatesGroup):
    waiting_result_text = State()
    waiting_result_photos = State()


# ==========================================
# БАЗА ДАННЫХ
# ==========================================

def init_db():
    with sqlite3.connect(DB_NAME) as db:
        db.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                username TEXT,
                service TEXT NOT NULL,
                price INTEGER NOT NULL,
                question TEXT NOT NULL,
                status TEXT DEFAULT 'Новый',
                result_text TEXT
            )
        """)


def get_order(order_id):
    with sqlite3.connect(DB_NAME) as db:
        return db.execute(
            """
            SELECT id, user_id, username, service,
                   price, question, status, result_text
            FROM orders
            WHERE id = ?
            """,
            (order_id,)
        ).fetchone()


def get_order_counts():
    with sqlite3.connect(DB_NAME) as db:
        total = db.execute(
            "SELECT COUNT(*) FROM orders"
        ).fetchone()[0]

        new = db.execute(
            "SELECT COUNT(*) FROM orders WHERE status = 'Новый'"
        ).fetchone()[0]

        progress = db.execute(
            "SELECT COUNT(*) FROM orders WHERE status = 'В работе'"
        ).fetchone()[0]

        done = db.execute(
            "SELECT COUNT(*) FROM orders WHERE status = 'Выполнен'"
        ).fetchone()[0]

    return total, new, progress, done


# ==========================================
# КЛАВИАТУРЫ
# ==========================================

def main_keyboard(user_id=None):
    buttons = [
        [
            InlineKeyboardButton(
                text="🔮 Ответ на конкретный вопрос — 299 ₽",
                callback_data="service_info:question"
            )
        ],
        [
            InlineKeyboardButton(
                text="🌙 Общий расклад — 599 ₽",
                callback_data="service_info:general"
            )
        ],
        [
            InlineKeyboardButton(
                text="📋 Мои заказы",
                callback_data="my_orders"
            )
        ],
        [
            InlineKeyboardButton(
                text="ℹ️ О проекте",
                callback_data="about"
            )
        ],
    ]

    if user_id == ADMIN_ID:
        buttons.append([
            InlineKeyboardButton(
                text="⚙️ Панель администратора",
                callback_data="admin_panel"
            )
        ])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def service_info_keyboard(service_id):
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="🛒 Оформить заказ",
                callback_data=f"service:{service_id}"
            )
        ],
        [
            InlineKeyboardButton(
                text="🔙 Назад к услугам",
                callback_data="back_home"
            )
        ]
    ])


def back_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="🔙 Главное меню",
                callback_data="back_home"
            )
        ]
    ])


def admin_menu_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="🆕 Новые",
                callback_data="orders:new:0"
            )
        ],
        [
            InlineKeyboardButton(
                text="🔄 В работе",
                callback_data="orders:progress:0"
            )
        ],
        [
            InlineKeyboardButton(
                text="✅ Выполненные",
                callback_data="orders:done:0"
            )
        ],
        [
            InlineKeyboardButton(
                text="🔙 Главное меню",
                callback_data="back_home"
            )
        ],
    ])


def orders_keyboard(status_key, page, orders, total_pages):
    buttons = []

    for order in orders:
        order_id, service, price, status = order

        buttons.append([
            InlineKeyboardButton(
                text=f"Заказ №{order_id} · {price} ₽",
                callback_data=f"order:{order_id}:{status_key}:{page}"
            )
        ])

    navigation = []

    if page > 0:
        navigation.append(
            InlineKeyboardButton(
                text="⬅️ Назад",
                callback_data=f"orders:{status_key}:{page - 1}"
            )
        )

    if page + 1 < total_pages:
        navigation.append(
            InlineKeyboardButton(
                text="Вперёд ➡️",
                callback_data=f"orders:{status_key}:{page + 1}"
            )
        )

    if navigation:
        buttons.append(navigation)

    buttons.append([
        InlineKeyboardButton(
            text="🔙 К панели",
            callback_data="admin_panel"
        )
    ])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def order_detail_keyboard(order_id, status, status_key, page):
    buttons = []

    if status == "Новый":
        buttons.append([
            InlineKeyboardButton(
                text="🔄 Взять в работу",
                callback_data=f"take:{order_id}:{status_key}:{page}"
            )
        ])

    if status in ("Новый", "В работе"):
        buttons.append([
            InlineKeyboardButton(
                text="✉️ Отправить результат",
                callback_data=f"result:{order_id}"
            )
        ])

    buttons.append([
        InlineKeyboardButton(
            text="⬅️ К списку заказов",
            callback_data=f"orders:{status_key}:{page}"
        )
    ])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


# ==========================================
# ИНИЦИАЛИЗАЦИЯ БОТА
# ==========================================

bot = Bot(
    token=BOT_TOKEN,
    default=DefaultBotProperties(
        parse_mode=ParseMode.HTML
    )
)

dp = Dispatcher()


# ==========================================
# ГЛАВНОЕ МЕНЮ
# ==========================================

@dp.message(CommandStart())
async def start(message: Message, state: FSMContext):
    await state.clear()

    await message.answer(
        "🌙 <b>Добро пожаловать в Lunaris Tarot!</b>\n\n"
        "Здесь ты можешь выбрать индивидуальный расклад "
        "Таро и ознакомиться с его условиями.\n\n"
        "Выбери интересующую тебя услугу:",
        reply_markup=main_keyboard(message.from_user.id)
    )


@dp.callback_query(F.data == "back_home")
async def back_home(callback: CallbackQuery):
    await callback.message.edit_text(
        "🌙 <b>Добро пожаловать в Lunaris Tarot!</b>\n\n"
        "Здесь ты можешь выбрать индивидуальный расклад "
        "Таро и ознакомиться с его условиями.\n\n"
        "Выбери интересующую тебя услугу:",
        reply_markup=main_keyboard(callback.from_user.id)
    )

    await callback.answer()


# ==========================================
# О ПРОЕКТЕ
# ==========================================

@dp.callback_query(F.data == "about")
async def about(callback: CallbackQuery):
    await callback.message.edit_text(
        "🌙 <b>О Lunaris Tarot</b>\n\n"
        "Lunaris Tarot — пространство индивидуальных "
        "раскладов Таро.\n\n"
        "Каждый расклад выполняется вручную с использованием "
        "физической колоды. Результат включает фотографии "
        "выпавших карт и текстовую интерпретацию.\n\n"
        "Таро используется для саморефлексии и развлечения "
        "и не заменяет профессиональную консультацию.",
        reply_markup=main_keyboard(callback.from_user.id)
    )

    await callback.answer()


# ==========================================
# ПОДРОБНОЕ ОПИСАНИЕ УСЛУГИ
# ==========================================

@dp.callback_query(F.data.startswith("service_info:"))
async def service_info(callback: CallbackQuery):
    service_id = callback.data.split(":")[1]
    service = SERVICES.get(service_id)

    if not service:
        await callback.answer(
            "Услуга не найдена",
            show_alert=True
        )
        return

    await callback.message.edit_text(
        f"🌙 <b>{html.escape(service['name'])}</b>\n\n"
        f"{html.escape(service['description'])}\n\n"
        "✨ <b>В услугу входит:</b>\n"
        "• Индивидуальный расклад\n"
        "• Персональная интерпретация карт\n"
        "• Фотографии выпавших карт\n\n"
        f"Стоимость: <b>{service['price']} ₽</b>\n\n"
        "Нажми кнопку ниже, чтобы оформить заказ.",
        reply_markup=service_info_keyboard(service_id)
    )

    await callback.answer()


# ==========================================
# НАЧАЛО ОФОРМЛЕНИЯ ЗАКАЗА
# ==========================================

@dp.callback_query(F.data.startswith("service:"))
async def choose_service(
    callback: CallbackQuery,
    state: FSMContext
):
    service_id = callback.data.split(":")[1]
    service = SERVICES.get(service_id)

    if not service:
        await callback.answer(
            "Услуга не найдена",
            show_alert=True
        )
        return

    await state.clear()

    await state.update_data(
        service_id=service_id
    )

    await state.set_state(
        OrderStates.waiting_question
    )

    await callback.message.edit_text(
        f"🛒 <b>Оформление заказа</b>\n\n"
        f"Услуга: <b>{html.escape(service['name'])}</b>\n"
        f"Стоимость: <b>{service['price']} ₽</b>\n\n"
        "Теперь напиши свой вопрос или опиши ситуацию.\n\n"
        "Постарайся сформулировать запрос максимально понятно.\n\n"
        "Для отмены оформления нажми /cancel."
    )

    await callback.answer()


# ==========================================
# ОТМЕНА ОФОРМЛЕНИЯ
# ==========================================

@dp.message(Command("cancel"))
async def cancel(
    message: Message,
    state: FSMContext
):
    await state.clear()

    await message.answer(
        "Оформление заказа отменено.",
        reply_markup=main_keyboard(message.from_user.id)
    )


# ==========================================
# ПОЛУЧЕНИЕ ВОПРОСА И СОЗДАНИЕ ЗАКАЗА
# ==========================================

@dp.message(OrderStates.waiting_question)
async def receive_question(
    message: Message,
    state: FSMContext
):
    if not message.text:
        await message.answer(
            "Пожалуйста, отправь свой запрос текстом."
        )
        return

    question = message.text.strip()

    if len(question) < 5:
        await message.answer(
            "Напиши немного подробнее, пожалуйста."
        )
        return

    if len(question) > 2000:
        await message.answer(
            "Слишком длинный запрос. Максимум 2000 символов."
        )
        return

    data = await state.get_data()
    service = SERVICES[data["service_id"]]

    with sqlite3.connect(DB_NAME) as db:
        cursor = db.execute(
            """
            INSERT INTO orders
            (user_id, username, service, price, question)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                message.from_user.id,
                message.from_user.username,
                service["name"],
                service["price"],
                question
            )
        )

        order_id = cursor.lastrowid

    await state.clear()

    username = (
        f"@{message.from_user.username}"
        if message.from_user.username
        else "Не указан"
    )

    admin_text = (
        "🌙 <b>Новый заказ Lunaris Tarot</b>\n\n"
        f"Заказ №{order_id}\n"
        f"Услуга: {html.escape(service['name'])}\n"
        f"Стоимость: {service['price']} ₽\n\n"
        f"Клиент: {html.escape(message.from_user.full_name)}\n"
        f"Username: {html.escape(username)}\n"
        f"Telegram ID: <code>{message.from_user.id}</code>\n\n"
        f"<b>Запрос клиента:</b>\n"
        f"{html.escape(question)}"
    )

    try:
        await bot.send_message(
            ADMIN_ID,
            admin_text,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="📂 Открыть заказ",
                        callback_data=f"order:{order_id}:new:0"
                    )
                ]
            ])
        )

    except Exception as error:
        print(f"Ошибка уведомления администратора: {error}")

    await message.answer(
        f"🌙 <b>Заявка №{order_id} принята!</b>\n\n"
        "Твой запрос сохранён и ожидает обработки.\n\n"
        "Оплата пока не подключена. Мы сообщим тебе, "
        "когда заказ будет готов к дальнейшему оформлению.",
        reply_markup=main_keyboard(message.from_user.id)
    )


# ==========================================
# МОИ ЗАКАЗЫ
# ==========================================

@dp.callback_query(F.data == "my_orders")
async def my_orders(callback: CallbackQuery):
    with sqlite3.connect(DB_NAME) as db:
        orders = db.execute(
            """
            SELECT id, service, price, status
            FROM orders
            WHERE user_id = ?
            ORDER BY id DESC
            LIMIT 10
            """,
            (callback.from_user.id,)
        ).fetchall()

    if not orders:
        text = (
            "📋 <b>Мои заказы</b>\n\n"
            "У тебя пока нет заказов."
        )

    else:
        text = "📋 <b>Мои последние заказы</b>\n\n"

        for order_id, service, price, status in orders:
            emoji = STATUS_EMOJI.get(status, "📦")

            text += (
                f"Заказ №{order_id}\n"
                f"{html.escape(service)}\n"
                f"{price} ₽ · {emoji} {html.escape(status)}\n\n"
            )

    await callback.message.edit_text(
        text,
        reply_markup=main_keyboard(callback.from_user.id)
    )

    await callback.answer()


# ==========================================
# ПАНЕЛЬ АДМИНИСТРАТОРА
# ==========================================

@dp.callback_query(F.data == "admin_panel")
async def admin_panel(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer(
            "Нет доступа",
            show_alert=True
        )
        return

    total, new, progress, done = get_order_counts()

    await callback.message.edit_text(
        "⚙️ <b>Панель администратора</b>\n\n"
        f"📦 Всего заказов: <b>{total}</b>\n\n"
        f"🆕 Новые: <b>{new}</b>\n"
        f"🔄 В работе: <b>{progress}</b>\n"
        f"✅ Выполненные: <b>{done}</b>\n\n"
        "Выбери категорию заказов:",
        reply_markup=admin_menu_keyboard()
    )

    await callback.answer()


# ==========================================
# СПИСОК ЗАКАЗОВ ПО СТАТУСУ
# ==========================================

@dp.callback_query(F.data.startswith("orders:"))
async def show_orders(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer(
            "Нет доступа",
            show_alert=True
        )
        return

    try:
        _, status_key, page_text = callback.data.split(":")
        page = int(page_text)

    except (ValueError, IndexError):
        await callback.answer(
            "Некорректный запрос",
            show_alert=True
        )
        return

    status = STATUSES.get(status_key)

    if not status or page < 0:
        await callback.answer(
            "Раздел не найден",
            show_alert=True
        )
        return

    per_page = 5
    offset = page * per_page

    with sqlite3.connect(DB_NAME) as db:
        total = db.execute(
            "SELECT COUNT(*) FROM orders WHERE status = ?",
            (status,)
        ).fetchone()[0]

        orders = db.execute(
            """
            SELECT id, service, price, status
            FROM orders
            WHERE status = ?
            ORDER BY id DESC
            LIMIT ? OFFSET ?
            """,
            (status, per_page, offset)
        ).fetchall()

    total_pages = max(
        1,
        (total + per_page - 1) // per_page
    )

    if page >= total_pages:
        page = total_pages - 1
        offset = page * per_page

        with sqlite3.connect(DB_NAME) as db:
            orders = db.execute(
                """
                SELECT id, service, price, status
                FROM orders
                WHERE status = ?
                ORDER BY id DESC
                LIMIT ? OFFSET ?
                """,
                (status, per_page, offset)
            ).fetchall()

    emoji = STATUS_EMOJI[status]

    if not orders:
        text = (
            f"{emoji} <b>{status}</b>\n\n"
            "В этом разделе пока нет заказов."
        )

    else:
        text = (
            f"{emoji} <b>{status}</b>\n\n"
            f"Всего заказов: {total}\n"
            f"Страница: {page + 1} из {total_pages}\n\n"
            "Выбери заказ:"
        )

    await callback.message.edit_text(
        text,
        reply_markup=orders_keyboard(
            status_key,
            page,
            orders,
            total_pages
        )
    )

    await callback.answer()


# ==========================================
# КАРТОЧКА ЗАКАЗА
# ==========================================

@dp.callback_query(F.data.startswith("order:"))
async def order_detail(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer(
            "Нет доступа",
            show_alert=True
        )
        return

    try:
        _, order_id_text, status_key, page_text = callback.data.split(":")
        order_id = int(order_id_text)
        page = int(page_text)

    except (ValueError, IndexError):
        await callback.answer(
            "Некорректный заказ",
            show_alert=True
        )
        return

    order = get_order(order_id)

    if not order:
        await callback.answer(
            "Заказ не найден",
            show_alert=True
        )
        return

    (
        order_id,
        user_id,
        username,
        service,
        price,
        question,
        status,
        result_text
    ) = order

    username_text = (
        f"@{username}"
        if username
        else "Не указан"
    )

    text = (
        f"📦 <b>Заказ №{order_id}</b>\n\n"
        f"Услуга: {html.escape(service)}\n"
        f"Стоимость: {price} ₽\n"
        f"Статус: {STATUS_EMOJI.get(status, '📦')} "
        f"{html.escape(status)}\n\n"
        f"<b>Клиент:</b> {html.escape(username_text)}\n"
        f"Telegram ID: <code>{user_id}</code>\n\n"
        f"<b>Запрос клиента:</b>\n"
        f"{html.escape(question)}"
    )

    if result_text:
        text += (
            "\n\n<b>Текст отправленного результата:</b>\n"
            f"{html.escape(result_text[:1000])}"
        )

    await callback.message.edit_text(
        text,
        reply_markup=order_detail_keyboard(
            order_id,
            status,
            status_key,
            page
        )
    )

    await callback.answer()


# ==========================================
# ВЗЯТЬ ЗАКАЗ В РАБОТУ
# ==========================================

@dp.callback_query(F.data.startswith("take:"))
async def take_order(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer(
            "Нет доступа",
            show_alert=True
        )
        return

    try:
        _, order_id_text, status_key, page_text = callback.data.split(":")
        order_id = int(order_id_text)
        page = int(page_text)

    except (ValueError, IndexError):
        await callback.answer(
            "Некорректный заказ",
            show_alert=True
        )
        return

    with sqlite3.connect(DB_NAME) as db:
        cursor = db.execute(
            """
            UPDATE orders
            SET status = 'В работе'
            WHERE id = ? AND status = 'Новый'
            """,
            (order_id,)
        )

    if cursor.rowcount == 0:
        await callback.answer(
            "Заказ уже изменён или не найден.",
            show_alert=True
        )
        return

    order = get_order(order_id)

    await callback.answer("Заказ взят в работу!")

    if order:
        await callback.message.edit_text(
            "🔄 <b>Заказ взят в работу!</b>\n\n"
            f"Заказ №{order_id}\n"
            f"Услуга: {html.escape(order[3])}\n"
            f"Стоимость: {order[4]} ₽\n"
            "Статус: 🔄 В работе\n\n"
            f"<b>Запрос клиента:</b>\n{html.escape(order[5])}",
            reply_markup=order_detail_keyboard(
                order_id,
                "В работе",
                status_key,
                page
            )
        )


# ==========================================
# НАЧАТЬ ОТПРАВКУ РЕЗУЛЬТАТА
# ==========================================

@dp.callback_query(F.data.startswith("result:"))
async def begin_result(
    callback: CallbackQuery,
    state: FSMContext
):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer(
            "Нет доступа",
            show_alert=True
        )
        return

    try:
        order_id = int(callback.data.split(":")[1])

    except (ValueError, IndexError):
        await callback.answer(
            "Некорректный номер заказа",
            show_alert=True
        )
        return

    order = get_order(order_id)

    if not order:
        await callback.answer(
            "Заказ не найден",
            show_alert=True
        )
        return

    if order[6] == "Выполнен":
        await callback.answer(
            "Этот заказ уже выполнен.",
            show_alert=True
        )
        return

    await state.clear()

    await state.update_data(
        order_id=order_id,
        customer_id=order[1],
        photos=[]
    )

    await state.set_state(
        AdminStates.waiting_result_text
    )

    await callback.message.answer(
        f"✉️ <b>Отправка результата заказа №{order_id}</b>\n\n"
        "Сначала отправь текст интерпретации.\n\n"
        "Для отмены отправки нажми /cancel."
    )

    await callback.answer()


# ==========================================
# ПОЛУЧИТЬ ТЕКСТ РЕЗУЛЬТАТА
# ==========================================

@dp.message(AdminStates.waiting_result_text)
async def receive_result_text(
    message: Message,
    state: FSMContext
):
    if message.from_user.id != ADMIN_ID:
        return

    if not message.text:
        await message.answer(
            "Отправь текст интерпретации обычным сообщением."
        )
        return

    await state.update_data(
        result_text=message.text
    )

    await state.set_state(
        AdminStates.waiting_result_photos
    )

    await message.answer(
        "✅ Текст сохранён.\n\n"
        "Теперь отправляй фотографии карт по одной.\n\n"
        "Когда закончишь, напиши /done.\n"
        "Если фотографий нет, тоже напиши /done."
    )


# ==========================================
# ПОЛУЧИТЬ ФОТОГРАФИИ
# ==========================================

@dp.message(
    AdminStates.waiting_result_photos,
    F.photo
)
async def receive_result_photo(
    message: Message,
    state: FSMContext
):
    if message.from_user.id != ADMIN_ID:
        return

    data = await state.get_data()
    photos = data.get("photos", [])

    photos.append(message.photo[-1].file_id)

    await state.update_data(
        photos=photos
    )

    await message.answer(
        f"📷 Фото принято. Всего фотографий: {len(photos)}.\n\n"
        "Отправь следующее или напиши /done."
    )


# ==========================================
# ЗАВЕРШИТЬ И ОТПРАВИТЬ РЕЗУЛЬТАТ
# ==========================================

@dp.message(
    AdminStates.waiting_result_photos,
    Command("done")
)
async def finish_result(
    message: Message,
    state: FSMContext
):
    if message.from_user.id != ADMIN_ID:
        return

    data = await state.get_data()

    order_id = data["order_id"]
    customer_id = data["customer_id"]
    result_text = data["result_text"]
    photos = data.get("photos", [])

    order = get_order(order_id)

    if not order or order[6] == "Выполнен":
        await state.clear()

        await message.answer(
            "Заказ не найден или уже выполнен. "
            "Проверь его в панели администратора."
        )
        return

    try:
        await bot.send_message(
            customer_id,
            "🌙 <b>Твой расклад готов!</b>\n\n"
            f"Заказ №{order_id}\n\n"
            f"{html.escape(result_text)}"
        )

        for photo_id in photos:
            await bot.send_photo(
                customer_id,
                photo_id
            )

        with sqlite3.connect(DB_NAME) as db:
            db.execute(
                """
                UPDATE orders
                SET status = 'Выполнен', result_text = ?
                WHERE id = ?
                """,
                (result_text, order_id)
            )

        await state.clear()

        await message.answer(
            f"✅ Результат заказа №{order_id} отправлен клиенту.\n\n"
            "Статус заказа изменён на «Выполнен»."
        )

    except Exception as error:
        print(f"Ошибка отправки результата: {error}")

        await message.answer(
            "⚠️ Не удалось полностью отправить результат.\n\n"
            "Проверь доступность чата с клиентом. "
            "Перед повторной отправкой проверь, "
            "не получил ли клиент уже часть результата."
        )


# ==========================================
# ЗАПУСК
# ==========================================

async def main():
    init_db()

    print("Lunaris Tarot запущен!")

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
