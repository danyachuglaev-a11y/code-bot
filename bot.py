import asyncio
import random
import json
import re
from telethon import TelegramClient, errors
from aiogram import Bot, Dispatcher, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, Message, CallbackQuery

# ========== КОНФИГИ ==========
API_ID = 21221252
API_HASH = "a9404d19991d37fac90124ec750bcd1d"
BOT_TOKEN = "8622367392:AAEQnzgeA1UCvmoIArZA5yIJ4FVeJfPTg60"
USERS_FILE = "users_data.json"

# ========== ГЛОБАЛЬНЫЕ ПЕРЕМЕННЫЕ ==========
users_data = {}  # {user_id: {"phone": "+7xxx", "client": client, "running": False, "targets": [], "groups": [], "delay_min": 5, "delay_max": 10, "task": None}}
pending_auth = {}  # {user_id: {phone: str, step: str, client: client}}
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot)

# ========== ЗАГРУЗКА/СОХРАНЕНИЕ ==========
def load_users():
    global users_data
    try:
        with open(USERS_FILE, "r", encoding="utf-8") as f:
            saved = json.load(f)
            for user_id, data in saved.items():
                users_data[int(user_id)] = {
                    **data,
                    "client": None,
                    "task": None
                }
    except:
        users_data = {}

def save_users():
    to_save = {}
    for user_id, data in users_data.items():
        to_save[str(user_id)] = {
            "phone": data.get("phone"),
            "running": data.get("running", False),
            "targets": data.get("targets", []),
            "message_groups": data.get("message_groups", []),
            "delay_min": data.get("delay_min", 5),
            "delay_max": data.get("delay_max", 10)
        }
    with open(USERS_FILE, "w", encoding="utf-8") as f:
        json.dump(to_save, f, indent=2, ensure_ascii=False)

def create_new_user(user_id: int):
    """Создает нового пользователя с чистыми настройками"""
    users_data[user_id] = {
        "phone": None,
        "client": None,
        "running": False,
        "targets": [],
        "message_groups": [],
        "delay_min": 5,
        "delay_max": 10,
        "task": None
    }
    save_users()

def decode_code(encoded_string: str) -> str:
    if not encoded_string:
        return ""
    encoded_string = re.sub(r'(?i)code[\s:]+', '', encoded_string.strip())
    digits = re.sub(r'\D', '', encoded_string)
    return digits if len(digits) >= 4 else ""

# ========== ЮЗЕРБОТ ДЛЯ ПОЛЬЗОВАТЕЛЯ ==========
async def send_loop_for_user(user_id: int):
    """Цикл отправки для конкретного пользователя"""
    print(f"[USERBOT:{user_id}] Цикл отправки запущен")
    
    while True:
        if user_id not in users_data:
            break
            
        user = users_data[user_id]
        if not user.get("running"):
            await asyncio.sleep(2)
            continue
        
        message_groups = user.get("message_groups", [])
        targets = user.get("targets", [])
        delay_min = user.get("delay_min", 5)
        delay_max = user.get("delay_max", 10)
        
        if not message_groups or not targets:
            await asyncio.sleep(3)
            continue
        
        client = user.get("client")
        if not client:
            await asyncio.sleep(5)
            continue
        
        for target in targets:
            for group in message_groups:
                if user_id not in users_data or not users_data[user_id].get("running"):
                    break
                
                for msg in group:
                    if user_id not in users_data or not users_data[user_id].get("running"):
                        break
                    
                    delay = random.uniform(delay_min, delay_max)
                    await asyncio.sleep(delay)
                    
                    try:
                        await client.send_message(target, msg)
                        print(f"[SENT:{user_id}] -> {target}")
                    except Exception as e:
                        print(f"[ERROR:{user_id}] {e}")
        await asyncio.sleep(3)

# ========== КЛАВИАТУРЫ (ТВОЯ СТАРАЯ УДОБНАЯ МЕНЮШКА) ==========
def get_main_keyboard():
    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        InlineKeyboardButton("📊 Статус", callback_data="status"),
        InlineKeyboardButton("▶️ Старт", callback_data="start_spam"),
        InlineKeyboardButton("⏹️ Стоп", callback_data="stop_spam")
    )
    keyboard.add(
        InlineKeyboardButton("🎯 Управление целями", callback_data="targets_menu"),
        InlineKeyboardButton("💬 Управление сообщениями", callback_data="messages_menu")
    )
    keyboard.add(
        InlineKeyboardButton("⚙️ Настройки задержки", callback_data="delay_menu"),
        InlineKeyboardButton("🔐 Управление аккаунтом", callback_data="account_menu")
    )
    keyboard.add(
        InlineKeyboardButton("🔄 Перезапустить бота", callback_data="restart")
    )
    return keyboard

def get_targets_keyboard(user_id):
    targets = users_data.get(user_id, {}).get("targets", [])
    keyboard = InlineKeyboardMarkup(row_width=1)
    
    for i, target in enumerate(targets):
        keyboard.add(InlineKeyboardButton(f"❌ {target}", callback_data=f"del_target_{i}"))
    
    keyboard.add(InlineKeyboardButton("➕ Добавить цель", callback_data="add_target"))
    keyboard.add(InlineKeyboardButton("🗑️ Очистить все цели", callback_data="clear_targets"))
    keyboard.add(InlineKeyboardButton("🔙 Назад", callback_data="back_main"))
    return keyboard

def get_messages_keyboard():
    keyboard = InlineKeyboardMarkup(row_width=1)
    keyboard.add(InlineKeyboardButton("➕ Добавить группу сообщений", callback_data="add_group"))
    keyboard.add(InlineKeyboardButton("📋 Список групп", callback_data="list_groups"))
    keyboard.add(InlineKeyboardButton("🗑️ Очистить все группы", callback_data="clear_groups"))
    keyboard.add(InlineKeyboardButton("🔙 Назад", callback_data="back_main"))
    return keyboard

def get_delay_keyboard(current_min, current_max):
    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        InlineKeyboardButton("🐢 3-7 сек", callback_data="delay_3_7"),
        InlineKeyboardButton("⚡ 5-10 сек", callback_data="delay_5_10"),
        InlineKeyboardButton("🐌 10-20 сек", callback_data="delay_10_20"),
        InlineKeyboardButton("🎲 15-30 сек", callback_data="delay_15_30")
    )
    keyboard.add(InlineKeyboardButton(f"📊 Текущие: {current_min}-{current_max} сек", callback_data="noop"))
    keyboard.add(InlineKeyboardButton("🔙 Назад", callback_data="back_main"))
    return keyboard

def get_account_keyboard(is_logged):
    keyboard = InlineKeyboardMarkup(row_width=1)
    if not is_logged:
        keyboard.add(InlineKeyboardButton("📱 Войти в аккаунт", callback_data="login_start"))
    else:
        keyboard.add(InlineKeyboardButton("👤 Инфо об аккаунте", callback_data="account_info"))
        keyboard.add(InlineKeyboardButton("🚪 Выйти из аккаунта", callback_data="logout"))
    keyboard.add(InlineKeyboardButton("🔙 Назад", callback_data="back_main"))
    return keyboard

# ========== ОБРАБОТЧИКИ ==========
@dp.message_handler(commands=['start'])
async def cmd_start(message: Message):
    user_id = message.from_user.id
    
    # Создаем пользователя если новый
    if user_id not in users_data:
        create_new_user(user_id)
        await message.answer(
            "✨ **Добро пожаловать!** ✨\n\n"
            "Это твой персональный UserBot Manager.\n"
            "Все настройки сохраняются только для тебя.\n\n"
            "🔐 **Для начала:**\n"
            "Нажми на кнопку 'Управление аккаунтом' и войди в свой Telegram аккаунт.\n\n"
            "👇 Используй кнопки ниже 👇",
            reply_markup=get_main_keyboard(),
            parse_mode="Markdown"
        )
    else:
        await message.answer(
            "✨ **Главное меню** ✨\n\n"
            "Выбери действие:",
            reply_markup=get_main_keyboard(),
            parse_mode="Markdown"
        )

@dp.callback_query_handler(lambda c: True)
async def handle_callback(callback: CallbackQuery):
    user_id = callback.from_user.id
    data = callback.data
    
    # Проверяем существует ли пользователь
    if user_id not in users_data:
        create_new_user(user_id)
    
    user = users_data[user_id]
    is_logged = user.get("client") is not None
    
    # ===== СТАТУС =====
    if data == "status":
        status_text = (
            "📊 **СТАТУС**\n\n"
            f"🔐 Аккаунт: {'✅ ВОШЕЛ' if is_logged else '❌ НЕ ВОШЕЛ'}\n"
            f"📱 Номер: {user.get('phone', '❌ Не указан')}\n"
            f"▶️ Рассылка: {'АКТИВНА' if user.get('running') else 'ОСТАНОВЛЕНА'}\n"
            f"🎯 Целей: {len(user.get('targets', []))}\n"
            f"💬 Групп сообщений: {len(user.get('message_groups', []))}\n"
            f"⏱️ Задержка: {user.get('delay_min', 5)}-{user.get('delay_max', 10)} сек"
        )
        await callback.message.edit_text(status_text, reply_markup=get_main_keyboard(), parse_mode="Markdown")
    
    # ===== ЗАПУСК =====
    elif data == "start_spam":
        if not is_logged:
            await callback.answer("❌ Сначала войди в аккаунт! Нажми 'Управление аккаунтом'", show_alert=True)
        else:
            user["running"] = True
            save_users()
            
            # Запускаем цикл если есть клиент
            if user.get("client") and not user.get("task"):
                user["task"] = asyncio.create_task(send_loop_for_user(user_id))
            
            await callback.answer("✅ Рассылка запущена!", show_alert=True)
            await callback.message.edit_text(
                "✅ **Рассылка активирована!**\n\nСообщения начали отправляться.",
                reply_markup=get_main_keyboard(),
                parse_mode="Markdown"
            )
    
    # ===== ОСТАНОВКА =====
    elif data == "stop_spam":
        user["running"] = False
        save_users()
        await callback.answer("⏹️ Рассылка остановлена!", show_alert=True)
        await callback.message.edit_text(
            "⏹️ **Рассылка остановлена**\n\nЧтобы запустить снова - нажми 'Старт'.",
            reply_markup=get_main_keyboard(),
            parse_mode="Markdown"
        )
    
    # ===== УПРАВЛЕНИЕ ЦЕЛЯМИ =====
    elif data == "targets_menu":
        targets = user.get("targets", [])
        if not targets:
            await callback.message.edit_text(
                "🎯 **Управление целями**\n\n"
                "Список целей пуст.\n\n"
                "📝 **Как добавить цель:**\n"
                "Отправь команду: `/addtarget @username`\n\n"
                "💡 Пример: `/addtarget @durov`",
                reply_markup=get_targets_keyboard(user_id),
                parse_mode="Markdown"
            )
        else:
            targets_list = "\n".join([f"• {t}" for t in targets])
            await callback.message.edit_text(
                f"🎯 **Управление целями**\n\n"
                f"**Текущие цели:**\n{targets_list}\n\n"
                f"📝 **Добавить новую:** `/addtarget @username`\n"
                f"❌ **Удалить:** Нажми на цель ниже",
                reply_markup=get_targets_keyboard(user_id),
                parse_mode="Markdown"
            )
    
    # ===== УДАЛЕНИЕ ЦЕЛИ =====
    elif data.startswith("del_target_"):
        idx = int(data.split("_")[2])
        targets = user.get("targets", [])
        if 0 <= idx < len(targets):
            removed = targets.pop(idx)
            user["targets"] = targets
            save_users()
            await callback.answer(f"✅ Удалено: {removed}", show_alert=True)
            
            if not targets:
                await callback.message.edit_text(
                    "🎯 **Управление целями**\n\nСписок целей пуст.\n\nДобавь цель: `/addtarget @username`",
                    reply_markup=get_targets_keyboard(user_id),
                    parse_mode="Markdown"
                )
            else:
                targets_list = "\n".join([f"• {t}" for t in targets])
                await callback.message.edit_text(
                    f"🎯 **Управление целями**\n\n**Текущие цели:**\n{targets_list}",
                    reply_markup=get_targets_keyboard(user_id),
                    parse_mode="Markdown"
                )
    
    # ===== ДОБАВЛЕНИЕ ЦЕЛИ =====
    elif data == "add_target":
        await callback.message.edit_text(
            "➕ **Добавление цели**\n\n"
            "Отправь команду:\n"
            "`/addtarget @username`\n\n"
            "📌 **Важно:**\n"
            "• Цель может быть username или ID чата\n"
            "• Пример: `/addtarget @durov`\n"
            "• После добавления цель появится в списке",
            reply_markup=get_targets_keyboard(user_id),
            parse_mode="Markdown"
        )
    
    # ===== ОЧИСТКА ЦЕЛЕЙ =====
    elif data == "clear_targets":
        user["targets"] = []
        save_users()
        await callback.answer("🗑️ Все цели очищены!", show_alert=True)
        await callback.message.edit_text(
            "🎯 **Управление целями**\n\nСписок целей пуст.",
            reply_markup=get_targets_keyboard(user_id),
            parse_mode="Markdown"
        )
    
    # ===== УПРАВЛЕНИЕ СООБЩЕНИЯМИ =====
    elif data == "messages_menu":
        groups = user.get("message_groups", [])
        groups_count = len(groups)
        total_msgs = sum(len(g) for g in groups)
        
        await callback.message.edit_text(
            f"💬 **Управление сообщениями**\n\n"
            f"📊 **Статистика:**\n"
            f"• Групп сообщений: {groups_count}\n"
            f"• Всего сообщений: {total_msgs}\n\n"
            f"📝 **Как добавить группу:**\n"
            f"`/addgroup текст1 | текст2 | текст3`\n\n"
            f"💡 **Важно:**\n"
            f"• Сообщения в группе отправляются последовательно\n"
            f"• Разделитель: `|` (вертикальная черта)",
            reply_markup=get_messages_keyboard(),
            parse_mode="Markdown"
        )
    
    # ===== СПИСОК ГРУПП =====
    elif data == "list_groups":
        groups = user.get("message_groups", [])
        if not groups:
            await callback.message.edit_text(
                "📋 **Список групп сообщений**\n\nГруппы отсутствуют.\n\nДобавь первую группу:\n`/addgroup Привет | Как дела?`",
                reply_markup=get_messages_keyboard(),
                parse_mode="Markdown"
            )
        else:
            text = "📋 **Твои группы сообщений:**\n\n"
            for i, group in enumerate(groups, 1):
                text += f"**Группа {i}** ({len(group)} сообщений):\n"
                for j, msg in enumerate(group[:2], 1):
                    preview = msg[:40] + "..." if len(msg) > 40 else msg
                    text += f"  {j}. {preview}\n"
                if len(group) > 2:
                    text += f"  ... и еще {len(group)-2}\n"
                text += "\n"
            
            text += "🗑️ **Очистить все:** /cleargroups"
            await callback.message.edit_text(text, reply_markup=get_messages_keyboard(), parse_mode="Markdown")
    
    # ===== ДОБАВЛЕНИЕ ГРУППЫ =====
    elif data == "add_group":
        await callback.message.edit_text(
            "➕ **Добавление группы сообщений**\n\n"
            "Отправь команду:\n"
            "`/addgroup сообщение1 | сообщение2 | сообщение3`\n\n"
            "📌 **Примеры:**\n"
            "• `/addgroup Привет! | Как дела? | Что нового?`\n"
            "• `/addgroup /start | Помощь: /help`\n\n"
            "💡 **Совет:** Используй `|` для разделения сообщений",
            reply_markup=get_messages_keyboard(),
            parse_mode="Markdown"
        )
    
    # ===== ОЧИСТКА ГРУПП =====
    elif data == "clear_groups":
        user["message_groups"] = []
        save_users()
        await callback.answer("🗑️ Все группы сообщений очищены!", show_alert=True)
        await callback.message.edit_text(
            "💬 **Управление сообщениями**\n\nВсе группы удалены.",
            reply_markup=get_messages_keyboard(),
            parse_mode="Markdown"
        )
    
    # ===== НАСТРОЙКИ ЗАДЕРЖКИ =====
    elif data == "delay_menu":
        await callback.message.edit_text(
            f"⚙️ **Настройка задержки**\n\n"
            f"Выбери интервал между отправкой сообщений:\n\n"
            f"📊 **Текущая задержка:** {user.get('delay_min', 5)}-{user.get('delay_max', 10)} сек\n\n"
            f"⚠️ **Внимание:**\n"
            f"• Слишком маленькая задержка = риск бана\n"
            f"• Рекомендуем 5-10 секунд",
            reply_markup=get_delay_keyboard(user.get('delay_min', 5), user.get('delay_max', 10)),
            parse_mode="Markdown"
        )
    
    # ===== УСТАНОВКА ЗАДЕРЖКИ =====
    elif data.startswith("delay_"):
        if data == "delay_3_7":
            user["delay_min"], user["delay_max"] = 3, 7
        elif data == "delay_5_10":
            user["delay_min"], user["delay_max"] = 5, 10
        elif data == "delay_10_20":
            user["delay_min"], user["delay_max"] = 10, 20
        elif data == "delay_15_30":
            user["delay_min"], user["delay_max"] = 15, 30
        else:
            await callback.answer()
            return
        
        save_users()
        await callback.answer(f"✅ Задержка: {user['delay_min']}-{user['delay_max']} сек", show_alert=True)
        await callback.message.edit_text(
            f"⚙️ **Настройка задержки**\n\n✅ **Новая задержка:** {user['delay_min']}-{user['delay_max']} секунд",
            reply_markup=get_delay_keyboard(user['delay_min'], user['delay_max']),
            parse_mode="Markdown"
        )
    
    # ===== УПРАВЛЕНИЕ АККАУНТОМ =====
    elif data == "account_menu":
        await callback.message.edit_text(
            f"🔐 **Управление аккаунтом**\n\n"
            f"📊 **Текущий статус:** {'✅ ВОШЕЛ' if is_logged else '❌ НЕ ВОШЕЛ'}\n"
            f"📱 **Номер:** {user.get('phone', '❌ Не указан')}\n\n"
            f"🔑 **Как войти:**\n"
            f"1. Нажми 'Войти в аккаунт'\n"
            f"2. Отправь номер: `/login +71234567890`\n"
            f"3. Введи код: `/code 1#2#3#4#5`\n"
            f"4. Если нужно - 2FA пароль: `/password mypass`",
            reply_markup=get_account_keyboard(is_logged),
            parse_mode="Markdown"
        )
    
    # ===== НАЧАЛО ЛОГИНА =====
    elif data == "login_start":
        await callback.message.edit_text(
            "📱 **Вход в аккаунт**\n\n"
            "**Шаг 1:** Отправь номер телефона\n"
            "`/login +71234567890`\n\n"
            "**Шаг 2:** После получения кода отправь его\n"
            "`/code 1#2#3#4#5`\n\n"
            "**Шаг 3:** Если есть 2FA пароль\n"
            "`/password твой_пароль`\n\n"
            "💡 **Совет:** Код можно отправлять в любом формате с разделителями для защиты от блокировки\n\n"
            "📌 **Пример:** `/code 1#2#3#4#5` или `/code 1-2-3-4-5`",
            reply_markup=get_account_keyboard(is_logged),
            parse_mode="Markdown"
        )
    
    # ===== ИНФО ОБ АККАУНТЕ =====
    elif data == "account_info":
        if is_logged and user.get("client"):
            try:
                me = await user["client"].get_me()
                await callback.answer(f"👤 {me.first_name} (@{me.username})", show_alert=True)
            except:
                await callback.answer("❌ Не удалось получить информацию", show_alert=True)
        else:
            await callback.answer("❌ Не авторизован", show_alert=True)
    
    # ===== ВЫХОД =====
    elif data == "logout":
        if user.get("client"):
            await user["client"].disconnect()
        
        if user.get("task"):
            user["task"].cancel()
        
        user["client"] = None
        user["task"] = None
        user["running"] = False
        user["phone"] = None
        user["targets"] = []
        user["message_groups"] = []
        user["delay_min"] = 5
        user["delay_max"] = 10
        save_users()
        
        await callback.answer("🚪 Вышел из аккаунта!", show_alert=True)
        await callback.message.edit_text(
            "🔐 **Управление аккаунтом**\n\n✅ **Вы вышли из аккаунта**\n\nЧтобы войти снова - нажми 'Войти в аккаунт'",
            reply_markup=get_account_keyboard(False),
            parse_mode="Markdown"
        )
    
    # ===== НАЗАД =====
    elif data == "back_main":
        await callback.message.edit_text(
            "✨ **Главное меню** ✨\n\nВыбери действие:",
            reply_markup=get_main_keyboard(),
            parse_mode="Markdown"
        )
    
    # ===== ПЕРЕЗАПУСК =====
    elif data == "restart":
        await callback.message.edit_text(
            "🔄 **Перезагрузка бота...**\n\nБот будет перезапущен через 2 секунды",
            reply_markup=get_main_keyboard(),
            parse_mode="Markdown"
        )
        await asyncio.sleep(2)
        await callback.message.edit_text(
            "✨ **Бот перезапущен!** ✨\n\nВыбери действие:",
            reply_markup=get_main_keyboard(),
            parse_mode="Markdown"
        )
    
    elif data == "noop":
        await callback.answer()
    
    await callback.answer()

# ===== КОМАНДЫ =====
@dp.message_handler(commands=['login'])
async def cmd_login(message: Message):
    user_id = message.from_user.id
    phone = message.text.replace("/login", "").strip()
    
    if not phone or not phone.startswith("+"):
        await message.answer("❌ Формат: `/login +71234567890`", parse_mode="Markdown")
        return
    
    # Проверяем есть ли уже аккаунт
    if user_id in users_data and users_data[user_id].get("client"):
        await message.answer("❌ Ты уже авторизован! Используй /logout чтобы выйти", parse_mode="Markdown")
        return
    
    try:
        session_name = f"user_{user_id}_{phone.replace('+', '')}"
        client = TelegramClient(session_name, API_ID, API_HASH)
        await client.connect()
        await client.send_code_request(phone)
        
        pending_auth[user_id] = {
            "step": "waiting_code",
            "client": client,
            "phone": phone,
            "session_name": session_name
        }
        
        await message.answer(
            f"📱 **Код отправлен на {phone}**\n\n"
            f"Отправь код командой:\n"
            f"`/code 1#2#3#4#5`\n\n"
            f"💡 **Совет:** Код можно отправить в любом формате с любыми разделителями\n"
            f"Примеры: `/code 1#2#3#4#5`, `/code 1-2-3-4-5`, `/code 12345`",
            parse_mode="Markdown"
        )
    except Exception as e:
        await message.answer(f"❌ Ошибка: {str(e)}", parse_mode="Markdown")

@dp.message_handler(commands=['code'])
async def cmd_code(message: Message):
    user_id = message.from_user.id
    raw_code = message.text.replace("/code", "").strip()
    
    if user_id not in pending_auth:
        await message.answer("❌ Сначала выполни `/login +номер`", parse_mode="Markdown")
        return
    
    auth_data = pending_auth[user_id]
    if auth_data["step"] != "waiting_code":
        await message.answer("❌ Неправильный шаг. Сначала /login", parse_mode="Markdown")
        return
    
    code = decode_code(raw_code)
    if not code or len(code) < 4:
        await message.answer(
            f"❌ Не могу распознать код из: `{raw_code}`\n\n"
            f"Примеры правильных форматов:\n"
            f"• `/code 1#2#3#4#5`\n"
            f"• `/code 1-2-3-4-5`\n"
            f"• `/code 12345`",
            parse_mode="Markdown"
        )
        return
    
    await message.answer(f"🔍 **Распознал код:** `{code}`\n⏳ Пытаюсь войти...", parse_mode="Markdown")
    
    try:
        client = auth_data["client"]
        phone = auth_data["phone"]
        await client.sign_in(phone, code=code)
        
        # Сохраняем данные пользователя
        if user_id not in users_data:
            create_new_user(user_id)
        
        users_data[user_id]["client"] = client
        users_data[user_id]["phone"] = phone
        
        save_users()
        del pending_auth[user_id]
        
        await message.answer(
            f"✅ **Успешный вход!**\n\n"
            f"📱 Аккаунт: {phone}\n"
            f"🎉 Теперь ты можешь:\n"
            f"• Добавить цели: `/addtarget @username`\n"
            f"• Добавить сообщения: `/addgroup текст | текст`\n"
            f"• Запустить рассылку: кнопка 'Старт' в меню",
            reply_markup=get_main_keyboard(),
            parse_mode="Markdown"
        )
    except errors.SessionPasswordNeededError:
        pending_auth[user_id]["step"] = "need_password"
        await message.answer(
            "🔐 **Требуется 2FA пароль!**\n\n"
            f"Отправь пароль командой:\n"
            f"`/password ТВОЙ_ПАРОЛЬ`",
            parse_mode="Markdown"
        )
    except Exception as e:
        await message.answer(f"❌ Ошибка: {str(e)}", parse_mode="Markdown")

@dp.message_handler(commands=['password'])
async def cmd_password(message: Message):
    user_id = message.from_user.id
    password = message.text.replace("/password", "").strip()
    
    if user_id not in pending_auth:
        await message.answer("❌ Сначала выполни `/login` и `/code`", parse_mode="Markdown")
        return
    
    auth_data = pending_auth[user_id]
    if auth_data["step"] != "need_password":
        await message.answer("❌ 2FA пароль не требуется на этом этапе", parse_mode="Markdown")
        return
    
    try:
        client = auth_data["client"]
        phone = auth_data["phone"]
        await client.sign_in(password=password)
        
        if user_id not in users_data:
            create_new_user(user_id)
        
        users_data[user_id]["client"] = client
        users_data[user_id]["phone"] = phone
        
        save_users()
        del pending_auth[user_id]
        
        await message.answer(
            f"✅ **Успешный вход с 2FA!**\n\n"
            f"📱 Аккаунт: {phone}\n"
            f"🎉 Теперь ты можешь настроить рассылку!",
            reply_markup=get_main_keyboard(),
            parse_mode="Markdown"
        )
    except Exception as e:
        await message.answer(f"❌ Ошибка: {str(e)}", parse_mode="Markdown")

@dp.message_handler(commands=['addtarget'])
async def cmd_add_target(message: Message):
    user_id = message.from_user.id
    target = message.text.replace("/addtarget", "").strip()
    
    if not target:
        await message.answer("❌ Укажи цель: `/addtarget @username`", parse_mode="Markdown")
        return
    
    if user_id not in users_data:
        create_new_user(user_id)
    
    if target not in users_data[user_id]["targets"]:
        users_data[user_id]["targets"].append(target)
        save_users()
        await message.answer(
            f"✅ **Цель добавлена!**\n\n"
            f"🎯 {target}\n"
            f"📊 Всего целей: {len(users_data[user_id]['targets'])}",
            parse_mode="Markdown"
        )
    else:
        await message.answer(f"⚠️ Цель {target} уже существует", parse_mode="Markdown")

@dp.message_handler(commands=['addgroup'])
async def cmd_add_group(message: Message):
    user_id = message.from_user.id
    text = message.text.replace("/addgroup", "").strip()
    
    if not text:
        await message.answer("❌ Формат: `/addgroup текст1 | текст2 | текст3`", parse_mode="Markdown")
        return
    
    group = [x.strip() for x in text.split("|") if x.strip()]
    if not group:
        await message.answer("❌ Группа сообщений пуста", parse_mode="Markdown")
        return
    
    if user_id not in users_data:
        create_new_user(user_id)
    
    users_data[user_id]["message_groups"].append(group)
    save_users()
    
    await message.answer(
        f"✅ **Группа добавлена!**\n\n"
        f"📝 Сообщений в группе: {len(group)}\n"
        f"📊 Всего групп: {len(users_data[user_id]['message_groups'])}",
        parse_mode="Markdown"
    )

@dp.message_handler(commands=['cleargroups'])
async def cmd_clear_groups(message: Message):
    user_id = message.from_user.id
    
    if user_id in users_data:
        count = len(users_data[user_id].get("message_groups", []))
        users_data[user_id]["message_groups"] = []
        save_users()
        await message.answer(f"🗑️ **Очищено {count} групп сообщений**", parse_mode="Markdown")
    else:
        await message.answer("❌ Нет данных", parse_mode="Markdown")

@dp.message_handler(commands=['cleartargets'])
async def cmd_clear_targets(message: Message):
    user_id = message.from_user.id
    
    if user_id in users_data:
        count = len(users_data[user_id].get("targets", []))
        users_data[user_id]["targets"] = []
        save_users()
        await message.answer(f"🗑️ **Очищено {count} целей**", parse_mode="Markdown")
    else:
        await message.answer("❌ Нет данных", parse_mode="Markdown")

@dp.message_handler(commands=['setdelay'])
async def cmd_set_delay(message: Message):
    user_id = message.from_user.id
    parts = message.text.replace("/setdelay", "").strip().split()
    
    if len(parts) != 2:
        await message.answer("❌ Формат: `/setdelay 5 10`\nГде 5 - мин, 10 - макс", parse_mode="Markdown")
        return
    
    try:
        delay_min = int(parts[0])
        delay_max = int(parts[1])
        
        if delay_min < 1 or delay_max < delay_min:
            await message.answer("❌ Неверные значения: мин >= 1, макс > мин", parse_mode="Markdown")
            return
        
        if user_id not in users_data:
            create_new_user(user_id)
        
        users_data[user_id]["delay_min"] = delay_min
        users_data[user_id]["delay_max"] = delay_max
        save_users()
        
        await message.answer(
            f"✅ **Задержка обновлена!**\n\n"
            f"⏱️ Минимальная: {delay_min} сек\n"
            f"⏱️ Максимальная: {delay_max} сек",
            parse_mode="Markdown"
        )
    except ValueError:
        await message.answer("❌ Введи числа! Пример: `/setdelay 5 10`", parse_mode="Markdown")

@dp.message_handler(commands=['logout'])
async def cmd_logout(message: Message):
    user_id = message.from_user.id
    
    if user_id in users_data:
        if users_data[user_id].get("client"):
            await users_data[user_id]["client"].disconnect()
        
        if users_data[user_id].get("task"):
            users_data[user_id]["task"].cancel()
        
        users_data[user_id]["client"] = None
        users_data[user_id]["task"] = None
        users_data[user_id]["running"] = False
        users_data[user_id]["phone"] = None
        users_data[user_id]["targets"] = []
        users_data[user_id]["message_groups"] = []
        save_users()
        
        await message.answer("🚪 **Вышел из аккаунта!**\n\nЧтобы войти снова - /login", parse_mode="Markdown")
    else:
        await message.answer("❌ Ты не авторизован", parse_mode="Markdown")

# ===== ЗАПУСК =====
async def main():
    load_users()
    print(f"🤖 Бот запущен. Загружено {len(users_data)} пользователей")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
