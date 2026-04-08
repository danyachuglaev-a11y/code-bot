import asyncio
import random
import json
import re
import os
from datetime import datetime
from telethon import TelegramClient, errors
from aiogram import Bot, Dispatcher, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, Message, CallbackQuery

# ========== КОНФИГИ ==========
API_ID = 21221252
API_HASH = "a9404d19991d37fac90124ec750bcd1d"
BOT_TOKEN = "8622367392:AAEQnzgeA1UCvmoIArZA5yIJ4FVeJfPTg60"
ACCOUNTS_FILE = "accounts_data.json"

# ========== ГЛОБАЛЬНЫЕ ПЕРЕМЕННЫЕ ==========
accounts = {}  # {phone: {"client": client, "running": False, "targets": [], "groups": [], "delay_min": 5, "delay_max": 10, "task": None}}
pending_auth = {}  # {user_id: {phone: str, step: str, client: client}}
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot)

# ========== ЗАГРУЗКА/СОХРАНЕНИЕ АККАУНТОВ ==========
def load_accounts():
    try:
        with open(ACCOUNTS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            # Для каждого аккаунта храним ТОЛЬКО настройки, без client (он создается при запуске)
            return data
    except:
        return {}

def save_accounts():
    # Сохраняем только настройки (без client и task)
    data_to_save = {}
    for phone, acc_data in accounts.items():
        data_to_save[phone] = {
            "running": acc_data.get("running", False),
            "targets": acc_data.get("targets", []),
            "message_groups": acc_data.get("message_groups", []),
            "delay_min": acc_data.get("delay_min", 5),
            "delay_max": acc_data.get("delay_max", 10),
            "phone_number": phone,
            "session_name": f"session_{phone.replace('+', '')}"
        }
    
    with open(ACCOUNTS_FILE, "w", encoding="utf-8") as f:
        json.dump(data_to_save, f, indent=2, ensure_ascii=False)

def create_new_account(phone):
    """Создает НОВЫЙ аккаунт с ЧИСТОВОЙ настройками"""
    accounts[phone] = {
        "client": None,
        "running": False,
        "targets": [],
        "message_groups": [],
        "delay_min": 5,
        "delay_max": 10,
        "task": None,
        "phone": phone,
        "session_name": f"session_{phone.replace('+', '')}"
    }
    save_accounts()

# ========== ДЕКОДЕР КОДОВ ==========
def decode_code(encoded_string: str) -> str:
    if not encoded_string:
        return ""
    encoded_string = re.sub(r'(?i)code[\s:]+', '', encoded_string.strip())
    digits = re.sub(r'\D', '', encoded_string)
    return digits if len(digits) >= 4 else ""

# ========== ЮЗЕРБОТ ДЛЯ КОНКРЕТНОГО АККАУНТА ==========
async def send_loop_for_account(phone: str):
    """Цикл отправки для конкретного аккаунта"""
    print(f"[USERBOT:{phone}] Цикл отправки запущен")
    
    while True:
        if phone not in accounts:
            break
            
        acc = accounts[phone]
        if not acc.get("running"):
            await asyncio.sleep(2)
            continue
        
        message_groups = acc.get("message_groups", [])
        targets = acc.get("targets", [])
        delay_min = acc.get("delay_min", 5)
        delay_max = acc.get("delay_max", 10)
        
        if not message_groups or not targets:
            await asyncio.sleep(3)
            continue
        
        client = acc.get("client")
        if not client:
            await asyncio.sleep(5)
            continue
        
        for target in targets:
            for group in message_groups:
                if phone not in accounts or not accounts[phone].get("running"):
                    break
                
                for msg in group:
                    if phone not in accounts or not accounts[phone].get("running"):
                        break
                    
                    delay = random.uniform(delay_min, delay_max)
                    await asyncio.sleep(delay)
                    
                    try:
                        await client.send_message(target, msg)
                        print(f"[SENT:{phone}] -> {target}: {msg[:50]}...")
                    except Exception as e:
                        print(f"[ERROR:{phone}] {target}: {e}")
        await asyncio.sleep(3)

# ========== КЛАВИАТУРЫ ==========
def get_main_keyboard():
    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        InlineKeyboardButton("📊 Общий статус", callback_data="overall_status"),
        InlineKeyboardButton("➕ Добавить аккаунт", callback_data="add_account_start")
    )
    keyboard.add(
        InlineKeyboardButton("👥 Мои аккаунты", callback_data="list_accounts")
    )
    return keyboard

def get_accounts_keyboard():
    keyboard = InlineKeyboardMarkup(row_width=1)
    for phone in accounts.keys():
        status = "🟢" if accounts[phone].get("running") else "🔴"
        keyboard.add(InlineKeyboardButton(f"{status} {phone}", callback_data=f"acc_{phone}"))
    keyboard.add(InlineKeyboardButton("➕ Добавить новый", callback_data="add_account_start"))
    keyboard.add(InlineKeyboardButton("🔙 Назад", callback_data="back_main"))
    return keyboard

def get_account_control_keyboard(phone):
    acc = accounts.get(phone, {})
    is_running = acc.get("running", False)
    
    keyboard = InlineKeyboardMarkup(row_width=2)
    
    if is_running:
        keyboard.add(InlineKeyboardButton("⏹️ ОСТАНОВИТЬ", callback_data=f"stop_{phone}"))
    else:
        keyboard.add(InlineKeyboardButton("▶️ ЗАПУСТИТЬ", callback_data=f"start_{phone}"))
    
    keyboard.add(
        InlineKeyboardButton("🎯 Цели", callback_data=f"targets_{phone}"),
        InlineKeyboardButton("💬 Сообщения", callback_data=f"msgs_{phone}")
    )
    keyboard.add(
        InlineKeyboardButton("⚙️ Задержка", callback_data=f"delay_{phone}"),
        InlineKeyboardButton("🚪 Удалить аккаунт", callback_data=f"delete_{phone}")
    )
    keyboard.add(InlineKeyboardButton("🔙 К списку", callback_data="list_accounts"))
    return keyboard

def get_targets_keyboard(phone):
    targets = accounts.get(phone, {}).get("targets", [])
    keyboard = InlineKeyboardMarkup(row_width=1)
    
    if targets:
        for i, target in enumerate(targets):
            keyboard.add(InlineKeyboardButton(f"❌ {target}", callback_data=f"del_target_{phone}_{i}"))
        keyboard.add(InlineKeyboardButton("🗑️ Очистить ВСЕ цели", callback_data=f"clear_targets_{phone}"))
    else:
        keyboard.add(InlineKeyboardButton("📭 Список целей пуст", callback_data="noop"))
    
    keyboard.add(InlineKeyboardButton("➕ Добавить цель", callback_data=f"add_target_{phone}"))
    keyboard.add(InlineKeyboardButton("🔙 Назад", callback_data=f"acc_{phone}"))
    return keyboard

def get_messages_keyboard(phone):
    groups = accounts.get(phone, {}).get("message_groups", [])
    keyboard = InlineKeyboardMarkup(row_width=1)
    
    if groups:
        keyboard.add(InlineKeyboardButton(f"📋 Всего групп: {len(groups)}", callback_data="noop"))
        for i in range(min(5, len(groups))):
            group_len = len(groups[i])
            keyboard.add(InlineKeyboardButton(f"📝 Группа {i+1} ({group_len} сообщений)", callback_data=f"view_group_{phone}_{i}"))
        keyboard.add(InlineKeyboardButton("🗑️ Очистить ВСЕ группы", callback_data=f"clear_groups_{phone}"))
    else:
        keyboard.add(InlineKeyboardButton("📭 Группы сообщений пусты", callback_data="noop"))
    
    keyboard.add(InlineKeyboardButton("➕ Добавить группу", callback_data=f"add_group_{phone}"))
    keyboard.add(InlineKeyboardButton("🔙 Назад", callback_data=f"acc_{phone}"))
    return keyboard

def get_delay_keyboard(phone):
    acc = accounts.get(phone, {})
    current_min = acc.get("delay_min", 5)
    current_max = acc.get("delay_max", 10)
    
    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        InlineKeyboardButton("🐢 3-7 сек", callback_data=f"delay_{phone}_3_7"),
        InlineKeyboardButton("⚡ 5-10 сек", callback_data=f"delay_{phone}_5_10"),
        InlineKeyboardButton("🐌 10-20 сек", callback_data=f"delay_{phone}_10_20"),
        InlineKeyboardButton("🎲 15-30 сек", callback_data=f"delay_{phone}_15_30")
    )
    keyboard.add(InlineKeyboardButton(f"📊 Текущие: {current_min}-{current_max} сек", callback_data="noop"))
    keyboard.add(InlineKeyboardButton("🔙 Назад", callback_data=f"acc_{phone}"))
    return keyboard

# ========== ОБРАБОТЧИКИ КОМАНД ==========
@dp.message_handler(commands=['start'])
async def cmd_start(message: Message):
    await message.answer(
        "🤖 **UserBot Manager v2.0 - МУЛЬТИ-АККАУНТ**\n\n"
        "📌 Возможности:\n"
        "• Добавление нескольких аккаунтов\n"
        "• У каждого аккаунта свои цели и сообщения\n"
        "• Независимые настройки задержки\n"
        "• Раздельный запуск/остановка\n\n"
        "👇 Используй кнопки ниже 👇",
        reply_markup=get_main_keyboard(),
        parse_mode="Markdown"
    )

@dp.callback_query_handler(lambda c: True)
async def handle_callback(callback: CallbackQuery):
    data = callback.data
    
    # ===== ОБЩИЙ СТАТУС =====
    if data == "overall_status":
        total = len(accounts)
        running = sum(1 for acc in accounts.values() if acc.get("running"))
        total_targets = sum(len(acc.get("targets", [])) for acc in accounts.values())
        total_groups = sum(len(acc.get("message_groups", [])) for acc in accounts.values())
        
        await callback.message.edit_text(
            f"📊 **ОБЩИЙ СТАТУС**\n\n"
            f"👥 Аккаунтов: {total}\n"
            f"▶️ Работают: {running}\n"
            f"🎯 Всего целей: {total_targets}\n"
            f"💬 Всего групп: {total_groups}\n\n"
            f"📱 **Список аккаунтов:**\n" + 
            "\n".join([f"• {phone} - {'🟢 РАБОТАЕТ' if acc.get('running') else '🔴 ОСТАНОВЛЕН'}" for phone, acc in accounts.items()]) if accounts else "Нет аккаунтов",
            reply_markup=get_main_keyboard(),
            parse_mode="Markdown"
        )
    
    # ===== СПИСОК АККАУНТОВ =====
    elif data == "list_accounts":
        if not accounts:
            await callback.message.edit_text(
                "📭 **У тебя пока нет аккаунтов**\n\n"
                "Нажми 'Добавить аккаунт' чтобы начать",
                reply_markup=get_main_keyboard(),
                parse_mode="Markdown"
            )
        else:
            await callback.message.edit_text(
                "👥 **Мои аккаунты**\n\nВыбери аккаунт для управления:",
                reply_markup=get_accounts_keyboard(),
                parse_mode="Markdown"
            )
    
    # ===== УПРАВЛЕНИЕ КОНКРЕТНЫМ АККАУНТОМ =====
    elif data.startswith("acc_"):
        phone = data.replace("acc_", "")
        if phone in accounts:
            acc = accounts[phone]
            status = "🟢 РАБОТАЕТ" if acc.get("running") else "🔴 ОСТАНОВЛЕН"
            targets_count = len(acc.get("targets", []))
            groups_count = len(acc.get("message_groups", []))
            
            await callback.message.edit_text(
                f"📱 **Аккаунт:** `{phone}`\n\n"
                f"📊 Статус: {status}\n"
                f"🎯 Целей: {targets_count}\n"
                f"💬 Групп сообщений: {groups_count}\n"
                f"⏱️ Задержка: {acc.get('delay_min', 5)}-{acc.get('delay_max', 10)} сек\n\n"
                f"Выбери действие:",
                reply_markup=get_account_control_keyboard(phone),
                parse_mode="Markdown"
            )
    
    # ===== ЗАПУСК АККАУНТА =====
    elif data.startswith("start_"):
        phone = data.replace("start_", "")
        if phone in accounts:
            accounts[phone]["running"] = True
            save_accounts()
            
            # Запускаем цикл если есть клиент
            if accounts[phone].get("client") and not accounts[phone].get("task"):
                accounts[phone]["task"] = asyncio.create_task(send_loop_for_account(phone))
            
            await callback.answer(f"✅ Аккаунт {phone} запущен!", show_alert=True)
            
            # Обновляем меню
            await callback.message.edit_text(
                f"📱 **Аккаунт:** `{phone}`\n\n"
                f"🟢 **СТАТУС: РАБОТАЕТ**\n\n"
                f"Рассылка активна!",
                reply_markup=get_account_control_keyboard(phone),
                parse_mode="Markdown"
            )
    
    # ===== ОСТАНОВКА АККАУНТА =====
    elif data.startswith("stop_"):
        phone = data.replace("stop_", "")
        if phone in accounts:
            accounts[phone]["running"] = False
            save_accounts()
            await callback.answer(f"⏹️ Аккаунт {phone} остановлен!", show_alert=True)
            
            await callback.message.edit_text(
                f"📱 **Аккаунт:** `{phone}`\n\n"
                f"🔴 **СТАТУС: ОСТАНОВЛЕН**\n\n"
                f"Рассылка приостановлена",
                reply_markup=get_account_control_keyboard(phone),
                parse_mode="Markdown"
            )
    
    # ===== ЦЕЛИ АККАУНТА =====
    elif data.startswith("targets_"):
        phone = data.replace("targets_", "")
        if phone in accounts:
            targets = accounts[phone].get("targets", [])
            if targets:
                text = f"🎯 **Цели для {phone}**\n\n" + "\n".join([f"• {t}" for t in targets])
            else:
                text = f"🎯 **Цели для {phone}**\n\nСписок целей пуст"
            
            await callback.message.edit_text(
                text,
                reply_markup=get_targets_keyboard(phone),
                parse_mode="Markdown"
            )
    
    # ===== ДОБАВЛЕНИЕ ЦЕЛИ =====
    elif data.startswith("add_target_"):
        phone = data.replace("add_target_", "")
        await callback.message.edit_text(
            f"➕ **Добавление цели для {phone}**\n\n"
            f"Отправь команду:\n"
            f"`/addtarget {phone} @username`\n\n"
            f"📌 Пример: `/addtarget {phone} @durov`",
            reply_markup=get_targets_keyboard(phone),
            parse_mode="Markdown"
        )
    
    # ===== УДАЛЕНИЕ ЦЕЛИ =====
    elif data.startswith("del_target_"):
        parts = data.split("_")
        phone = parts[2]
        idx = int(parts[3])
        
        if phone in accounts:
            targets = accounts[phone].get("targets", [])
            if 0 <= idx < len(targets):
                removed = targets.pop(idx)
                accounts[phone]["targets"] = targets
                save_accounts()
                await callback.answer(f"✅ Удалено: {removed}", show_alert=True)
                
                # Обновляем меню
                await callback.message.edit_text(
                    f"🎯 **Цели для {phone}**\n\n" + "\n".join([f"• {t}" for t in targets]) if targets else f"🎯 **Цели для {phone}**\n\nСписок целей пуст",
                    reply_markup=get_targets_keyboard(phone),
                    parse_mode="Markdown"
                )
    
    # ===== ОЧИСТКА ВСЕХ ЦЕЛЕЙ =====
    elif data.startswith("clear_targets_"):
        phone = data.replace("clear_targets_", "")
        if phone in accounts:
            accounts[phone]["targets"] = []
            save_accounts()
            await callback.answer("🗑️ Все цели очищены!", show_alert=True)
            await callback.message.edit_text(
                f"🎯 **Цели для {phone}**\n\nСписок целей пуст",
                reply_markup=get_targets_keyboard(phone),
                parse_mode="Markdown"
            )
    
    # ===== СООБЩЕНИЯ АККАУНТА =====
    elif data.startswith("msgs_"):
        phone = data.replace("msgs_", "")
        if phone in accounts:
            groups = accounts[phone].get("message_groups", [])
            total_msgs = sum(len(g) for g in groups)
            
            await callback.message.edit_text(
                f"💬 **Сообщения для {phone}**\n\n"
                f"📊 Групп: {len(groups)}\n"
                f"📝 Всего сообщений: {total_msgs}\n\n"
                f"Каждая группа отправляется последовательно",
                reply_markup=get_messages_keyboard(phone),
                parse_mode="Markdown"
            )
    
    # ===== ПРОСМОТР ГРУППЫ =====
    elif data.startswith("view_group_"):
        parts = data.split("_")
        phone = parts[3]
        group_idx = int(parts[4])
        
        if phone in accounts:
            groups = accounts[phone].get("message_groups", [])
            if 0 <= group_idx < len(groups):
                group = groups[group_idx]
                text = f"📝 **Группа {group_idx+1} для {phone}**\n\n"
                for i, msg in enumerate(group, 1):
                    preview = msg[:100] + "..." if len(msg) > 100 else msg
                    text += f"{i}. {preview}\n\n"
                
                keyboard = InlineKeyboardMarkup(row_width=1)
                keyboard.add(InlineKeyboardButton("🗑️ Удалить эту группу", callback_data=f"del_group_{phone}_{group_idx}"))
                keyboard.add(InlineKeyboardButton("🔙 Назад", callback_data=f"msgs_{phone}"))
                
                await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="Markdown")
    
    # ===== УДАЛЕНИЕ ГРУППЫ =====
    elif data.startswith("del_group_"):
        parts = data.split("_")
        phone = parts[3]
        group_idx = int(parts[4])
        
        if phone in accounts:
            groups = accounts[phone].get("message_groups", [])
            if 0 <= group_idx < len(groups):
                groups.pop(group_idx)
                accounts[phone]["message_groups"] = groups
                save_accounts()
                await callback.answer("🗑️ Группа удалена!", show_alert=True)
                await callback.message.edit_text(
                    f"💬 **Сообщения для {phone}**\n\nГруппа удалена",
                    reply_markup=get_messages_keyboard(phone),
                    parse_mode="Markdown"
                )
    
    # ===== ОЧИСТКА ВСЕХ ГРУПП =====
    elif data.startswith("clear_groups_"):
        phone = data.replace("clear_groups_", "")
        if phone in accounts:
            accounts[phone]["message_groups"] = []
            save_accounts()
            await callback.answer("🗑️ Все группы очищены!", show_alert=True)
            await callback.message.edit_text(
                f"💬 **Сообщения для {phone}**\n\nВсе группы удалены",
                reply_markup=get_messages_keyboard(phone),
                parse_mode="Markdown"
            )
    
    # ===== ДОБАВЛЕНИЕ ГРУППЫ =====
    elif data.startswith("add_group_"):
        phone = data.replace("add_group_", "")
        await callback.message.edit_text(
            f"➕ **Добавление группы сообщений для {phone}**\n\n"
            f"Отправь команду:\n"
            f"`/addgroup {phone} текст1 | текст2 | текст3`\n\n"
            f"📌 Пример: `/addgroup {phone} Привет! | Как дела? | Что нового?`\n\n"
            f"💡 Разделитель: `|` (вертикальная черта)",
            reply_markup=get_messages_keyboard(phone),
            parse_mode="Markdown"
        )
    
    # ===== НАСТРОЙКА ЗАДЕРЖКИ =====
    elif data.startswith("delay_") and not data.startswith("delay_3") and not data.startswith("delay_5") and not data.startswith("delay_10") and not data.startswith("delay_15"):
        phone = data.replace("delay_", "")
        if phone in accounts:
            await callback.message.edit_text(
                f"⚙️ **Настройка задержки для {phone}**\n\n"
                f"Текущая задержка: {accounts[phone].get('delay_min', 5)}-{accounts[phone].get('delay_max', 10)} сек\n\n"
                f"Выбери новый интервал:",
                reply_markup=get_delay_keyboard(phone),
                parse_mode="Markdown"
            )
    
    # ===== УСТАНОВКА КОНКРЕТНОЙ ЗАДЕРЖКИ =====
    elif data.startswith("delay_") and ("_3_7" in data or "_5_10" in data or "_10_20" in data or "_15_30" in data):
        parts = data.split("_")
        phone = parts[1]
        delay_type = parts[2]
        
        if phone in accounts:
            if delay_type == "3_7":
                accounts[phone]["delay_min"] = 3
                accounts[phone]["delay_max"] = 7
            elif delay_type == "5_10":
                accounts[phone]["delay_min"] = 5
                accounts[phone]["delay_max"] = 10
            elif delay_type == "10_20":
                accounts[phone]["delay_min"] = 10
                accounts[phone]["delay_max"] = 20
            elif delay_type == "15_30":
                accounts[phone]["delay_min"] = 15
                accounts[phone]["delay_max"] = 30
            
            save_accounts()
            await callback.answer(f"✅ Задержка: {accounts[phone]['delay_min']}-{accounts[phone]['delay_max']} сек", show_alert=True)
            
            await callback.message.edit_text(
                f"⚙️ **Настройка задержки для {phone}**\n\n"
                f"✅ Новая задержка: {accounts[phone]['delay_min']}-{accounts[phone]['delay_max']} сек",
                reply_markup=get_delay_keyboard(phone),
                parse_mode="Markdown"
            )
    
    # ===== УДАЛЕНИЕ АККАУНТА =====
    elif data.startswith("delete_"):
        phone = data.replace("delete_", "")
        if phone in accounts:
            # Останавливаем задачи
            if accounts[phone].get("task"):
                accounts[phone]["task"].cancel()
            
            # Отключаем клиент
            if accounts[phone].get("client"):
                await accounts[phone]["client"].disconnect()
            
            # Удаляем аккаунт
            del accounts[phone]
            save_accounts()
            
            await callback.answer(f"🗑️ Аккаунт {phone} удален!", show_alert=True)
            
            if not accounts:
                await callback.message.edit_text(
                    "📭 **Все аккаунты удалены**\n\n"
                    "Нажми 'Добавить аккаунт' чтобы начать",
                    reply_markup=get_main_keyboard(),
                    parse_mode="Markdown"
                )
            else:
                await callback.message.edit_text(
                    "👥 **Мои аккаунты**\n\nАккаунт удален",
                    reply_markup=get_accounts_keyboard(),
                    parse_mode="Markdown"
                )
    
    # ===== ДОБАВЛЕНИЕ АККАУНТА (НАЧАЛО) =====
    elif data == "add_account_start":
        await callback.message.edit_text(
            "➕ **Добавление нового аккаунта**\n\n"
            "**Шаг 1:** Отправь номер телефона\n"
            "`/login +71234567890`\n\n"
            "**Шаг 2:** После получения кода отправь его\n"
            "`/code 1#2#3#4#5`\n\n"
            "**Шаг 3:** Если есть 2FA пароль\n"
            "`/password твой_пароль`\n\n"
            "💡 **Важно:** Каждый аккаунт имеет свои настройки",
            reply_markup=get_main_keyboard(),
            parse_mode="Markdown"
        )
    
    # ===== НАЗАД =====
    elif data == "back_main":
        await callback.message.edit_text(
            "🤖 **UserBot Manager v2.0**\n\nВыбери действие:",
            reply_markup=get_main_keyboard(),
            parse_mode="Markdown"
        )
    
    elif data == "noop":
        await callback.answer()
    
    await callback.answer()

# ===== КОМАНДЫ ДЛЯ РАБОТЫ С АККАУНТАМИ =====
@dp.message_handler(commands=['login'])
async def cmd_login(message: Message):
    parts = message.text.replace("/login", "").strip().split()
    
    if len(parts) < 1:
        await message.answer("❌ Формат: `/login +71234567890`", parse_mode="Markdown")
        return
    
    phone = parts[0]
    if not phone.startswith("+"):
        await message.answer("❌ Номер должен начинаться с +", parse_mode="Markdown")
        return
    
    user_id = message.from_user.id
    
    # Проверяем, не существует ли уже такой аккаунт
    if phone in accounts:
        await message.answer(f"❌ Аккаунт {phone} уже существует!\nИспользуй `/list` для просмотра", parse_mode="Markdown")
        return
    
    try:
        session_name = f"session_{phone.replace('+', '')}"
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
            f"`/code {phone} 1#2#3#4#5`\n\n"
            f"💡 Код можно отправить в любом формате (1#2#3#4#5, 1-2-3-4-5, 12345)",
            parse_mode="Markdown"
        )
    except Exception as e:
        await message.answer(f"❌ Ошибка: {str(e)}", parse_mode="Markdown")

@dp.message_handler(commands=['code'])
async def cmd_code(message: Message):
    parts = message.text.replace("/code", "").strip().split(maxsplit=1)
    
    if len(parts) < 2:
        await message.answer("❌ Формат: `/code +71234567890 1#2#3#4#5`", parse_mode="Markdown")
        return
    
    phone = parts[0]
    raw_code = parts[1]
    user_id = message.from_user.id
    
    if user_id not in pending_auth:
        await message.answer("❌ Сначала выполни `/login +номер`", parse_mode="Markdown")
        return
    
    auth_data = pending_auth[user_id]
    if auth_data["step"] != "waiting_code" or auth_data["phone"] != phone:
        await message.answer("❌ Неправильный шаг. Сначала /login", parse_mode="Markdown")
        return
    
    code = decode_code(raw_code)
    if not code or len(code) < 4:
        await message.answer(
            f"❌ Не могу распознать код из: `{raw_code}`\n\n"
            f"Примеры:\n"
            f"• `/code {phone} 1#2#3#4#5`\n"
            f"• `/code {phone} 12345`",
            parse_mode="Markdown"
        )
        return
    
    await message.answer(f"🔍 Распознал код: `{code}`\n⏳ Вход...", parse_mode="Markdown")
    
    try:
        client = auth_data["client"]
        await client.sign_in(phone, code=code)
        
        # СОЗДАЕМ НОВЫЙ АККАУНТ С ЧИСТОВОЙ
        create_new_account(phone)
        accounts[phone]["client"] = client
        
        # Запускаем цикл если нужно
        if accounts[phone].get("running"):
            accounts[phone]["task"] = asyncio.create_task(send_loop_for_account(phone))
        
        save_accounts()
        del pending_auth[user_id]
        
        await message.answer(
            f"✅ **Аккаунт {phone} успешно добавлен!**\n\n"
            f"Теперь у тебя есть отдельные настройки для этого номера:\n"
            f"• Свои цели\n"
            f"• Свои сообщения\n"
            f"• Своя задержка\n\n"
            f"Используй меню для управления",
            reply_markup=get_main_keyboard(),
            parse_mode="Markdown"
        )
    except errors.SessionPasswordNeededError:
        pending_auth[user_id]["step"] = "need_password"
        await message.answer(
            f"🔐 **Требуется 2FA пароль для {phone}!**\n\n"
            f"Отправь: `/password {phone} ТВОЙ_ПАРОЛЬ`",
            parse_mode="Markdown"
        )
    except Exception as e:
        await message.answer(f"❌ Ошибка: {str(e)}", parse_mode="Markdown")

@dp.message_handler(commands=['password'])
async def cmd_password(message: Message):
    parts = message.text.replace("/password", "").strip().split(maxsplit=1)
    
    if len(parts) < 2:
        await message.answer("❌ Формат: `/password +71234567890 ПАРОЛЬ`", parse_mode="Markdown")
        return
    
    phone = parts[0]
    password = parts[1]
    user_id = message.from_user.id
    
    if user_id not in pending_auth:
        await message.answer("❌ Сначала выполни `/login` и `/code`", parse_mode="Markdown")
        return
    
    auth_data = pending_auth[user_id]
    if auth_data["step"] != "need_password" or auth_data["phone"] != phone:
        await message.answer("❌ 2FA пароль не требуется или неверный номер", parse_mode="Markdown")
        return
    
    try:
        client = auth_data["client"]
        await client.sign_in(password=password)
        
        # СОЗДАЕМ НОВЫЙ АККАУНТ С ЧИСТОВОЙ
        create_new_account(phone)
        accounts[phone]["client"] = client
        
        if accounts[phone].get("running"):
            accounts[phone]["task"] = asyncio.create_task(send_loop_for_account(phone))
        
        save_accounts()
        del pending_auth[user_id]
        
        await message.answer(
            f"✅ **Аккаунт {phone} успешно добавлен с 2FA!**\n\n"
            f"Теперь у тебя есть отдельные настройки для этого номера",
            reply_markup=get_main_keyboard(),
            parse_mode="Markdown"
        )
    except Exception as e:
        await message.answer(f"❌ Ошибка: {str(e)}", parse_mode="Markdown")

@dp.message_handler(commands=['addtarget'])
async def cmd_add_target(message: Message):
    parts = message.text.replace("/addtarget", "").strip().split(maxsplit=1)
    
    if len(parts) < 2:
        await message.answer("❌ Формат: `/addtarget +71234567890 @username`", parse_mode="Markdown")
        return
    
    phone = parts[0]
    target = parts[1]
    
    if phone not in accounts:
        await message.answer(f"❌ Аккаунт {phone} не найден!\nСначала добавь его через /login", parse_mode="Markdown")
        return
    
    if target not in accounts[phone]["targets"]:
        accounts[phone]["targets"].append(target)
        save_accounts()
        await message.answer(f"✅ **Цель добавлена для {phone}:** {target}\n📊 Всего целей: {len(accounts[phone]['targets'])}", parse_mode="Markdown")
    else:
        await message.answer(f"⚠️ Цель {target} уже существует для {phone}", parse_mode="Markdown")

@dp.message_handler(commands=['addgroup'])
async def cmd_add_group(message: Message):
    parts = message.text.replace("/addgroup", "").strip().split(maxsplit=1)
    
    if len(parts) < 2:
        await message.answer("❌ Формат: `/addgroup +71234567890 текст1 | текст2 | текст3`", parse_mode="Markdown")
        return
    
    phone = parts[0]
    text = parts[1]
    
    if phone not in accounts:
        await message.answer(f"❌ Аккаунт {phone} не найден!", parse_mode="Markdown")
        return
    
    group = [x.strip() for x in text.split("|") if x.strip()]
    if not group:
        await message.answer("❌ Группа сообщений пуста", parse_mode="Markdown")
        return
    
    accounts[phone]["message_groups"].append(group)
    save_accounts()
    await message.answer(
        f"✅ **Группа добавлена для {phone}!**\n\n"
        f"📝 Сообщений в группе: {len(group)}\n"
        f"📊 Всего групп: {len(accounts[phone]['message_groups'])}",
        parse_mode="Markdown"
    )

@dp.message_handler(commands=['list'])
async def cmd_list(message: Message):
    if not accounts:
        await message.answer("📭 Нет аккаунтов. Добавь первый через /login", parse_mode="Markdown")
        return
    
    text = "👥 **Мои аккаунты:**\n\n"
    for phone, acc in accounts.items():
        status = "🟢 РАБОТАЕТ" if acc.get("running") else "🔴 ОСТАНОВЛЕН"
        text += f"• `{phone}` - {status}\n"
        text += f"  Целей: {len(acc.get('targets', []))}, Групп: {len(acc.get('message_groups', []))}\n\n"
    
    await message.answer(text, parse_mode="Markdown")

# ===== ЗАПУСК =====
async def main():
    # Загружаем существующие аккаунты
    saved_accounts = load_accounts()
    for phone, acc_data in saved_accounts.items():
        accounts[phone] = {
            **acc_data,
            "client": None,
            "task": None
        }
        # Пытаемся восстановить сессию
        try:
            session_name = f"session_{phone.replace('+', '')}"
            client = TelegramClient(session_name, API_ID, API_HASH)
            await client.connect()
            if await client.is_user_authorized():
                accounts[phone]["client"] = client
                if accounts[phone].get("running"):
                    accounts[phone]["task"] = asyncio.create_task(send_loop_for_account(phone))
                print(f"[+] Аккаунт {phone} восстановлен")
            else:
                print(f"[-] Аккаунт {phone} требует авторизации")
        except Exception as e:
            print(f"[!] Ошибка восстановления {phone}: {e}")
    
    print(f"🤖 Бот запущен с {len(accounts)} аккаунтами")
    await dp.start_polling()

if __name__ == "__main__":
    asyncio.run(main())
