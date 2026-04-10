import asyncio
import random
import json
import re
import os
from telethon import TelegramClient, errors, events
from telethon.tl.types import MessageMediaWebPage, MessageMediaPhoto
from telethon.tl.functions.channels import JoinChannelRequest
from telethon.tl.types import InputChannel
from aiogram import Bot, Dispatcher, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, Message

# ========== КОНФИГИ ==========
API_ID = 21221252
API_HASH = "a9404d19991d37fac90124ec750bcd1d"
BOT_TOKEN = "8580248890:AAFumXO2yAWzaXP9ahkQwFRL-rRFk6OQy0U"
USERS_FILE = "users_data.json"

# ========== ГЛОБАЛЬНЫЕ ПЕРЕМЕННЫЕ ==========
users_data = {}
pending_auth = {}
temp_data = {}
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
                    "task": None,
                    "monitor_task": None
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
            "delay_max": data.get("delay_max", 10),
            "auto_captcha": data.get("auto_captcha", True),
            "auto_subscribe": data.get("auto_subscribe", True)
        }
    with open(USERS_FILE, "w", encoding="utf-8") as f:
        json.dump(to_save, f, indent=2, ensure_ascii=False)

def create_new_user(user_id: int):
    users_data[user_id] = {
        "phone": None,
        "client": None,
        "running": False,
        "targets": [],
        "message_groups": [],
        "delay_min": 5,
        "delay_max": 10,
        "task": None,
        "monitor_task": None,
        "auto_captcha": True,
        "auto_subscribe": True
    }
    save_users()

def decode_code(encoded_string: str) -> str:
    if not encoded_string:
        return ""
    encoded_string = re.sub(r'(?i)code[\s:]+', '', encoded_string.strip())
    digits = re.sub(r'\D', '', encoded_string)
    return digits if len(digits) >= 4 else ""

# ========== АВТОМАТИЧЕСКОЕ РЕШЕНИЕ КАПЧ ==========
async def solve_captcha(client, message):
    """Автоматически решает капчу"""
    text = message.text.lower() if message.text else ""
    
    # Тип 1: Цифровая капча
    numbers = re.findall(r'\b\d{4,6}\b', text)
    if numbers:
        code = numbers[0]
        await client.send_message(message.chat_id, code)
        print(f"[CAPTCHA] Решил цифровую: {code}")
        return True, f"✅ Решил цифровую капчу: {code}"
    
    # Тип 2: Кнопка "Я не робот"
    if message.reply_markup:
        for row in message.reply_markup.rows:
            for button in row.buttons:
                button_text = button.text.lower()
                if any(word in button_text for word in ['не робот', 'captcha', 'verify', 'проверк', 'solve', 'confirm', 'подтверд', 'start']):
                    await message.click(button.text)
                    print(f"[CAPTCHA] Нажал кнопку: {button.text}")
                    return True, f"✅ Нажал кнопку: {button.text}"
    
    # Тип 3: Отправить /start
    if 'бот' in text or 'start' in text or 'начать' in text:
        await client.send_message(message.chat_id, "/start")
        print(f"[CAPTCHA] Отправил /start")
        return True, "✅ Отправил /start"
    
    # Тип 4: Отправить любое сообщение
    if 'введите' in text or 'напишите' in text:
        await client.send_message(message.chat_id, "1")
        print(f"[CAPTCHA] Отправил 1")
        return True, "✅ Отправил 1"
    
    return False, "❌ Не удалось решить"

# ========== АВТОМАТИЧЕСКАЯ ПОДПИСКА ==========
async def auto_subscribe(client, message):
    """Автоматически подписывается на каналы из сообщения"""
    text = message.text.lower() if message.text else ""
    
    # Ищем ссылки на каналы
    patterns = [
        r'(?:https?://)?(?:www\.)?t\.me/([a-zA-Z0-9_]+)',
        r'@([a-zA-Z0-9_]{5,})',
        r'(?:канал|спонсор|подпишись|подписаться|channel|subscribe)\s+@?([a-zA-Z0-9_]+)'
    ]
    
    channels = []
    for pattern in patterns:
        matches = re.findall(pattern, text)
        channels.extend(matches)
    
    results = []
    for channel in set(channels):
        if len(channel) > 3:
            try:
                # Пробуем подписаться
                entity = await client.get_entity(f"@{channel}")
                await client(JoinChannelRequest(entity))
                results.append(f"✅ Подписался на @{channel}")
                print(f"[SUBSCRIBE] Подписался на @{channel}")
            except Exception as e:
                results.append(f"❌ Не удалось подписаться на @{channel}: {str(e)[:50]}")
    
    return results

# ========== МОНИТОРИНГ СООБЩЕНИЙ ==========
async def monitor_messages(client, user_id):
    """Мониторит входящие сообщения и автоматически решает капчи/подписывается"""
    print(f"[MONITOR:{user_id}] Запущен")
    
    @client.on(events.NewMessage(incoming=True))
    async def handler(event):
        # Проверяем что это личное сообщение
        if event.is_private:
            user = users_data.get(user_id, {})
            text = event.message.text or ""
            
            print(f"[MONITOR:{user_id}] Получено: {text[:100]}")
            
            # Автоподписка
            if user.get("auto_subscribe", True):
                subscribe_results = await auto_subscribe(client, event.message)
                if subscribe_results:
                    for result in subscribe_results:
                        await bot.send_message(user_id, f"🔔 {result}")
            
            # Авторешение капчи
            if user.get("auto_captcha", True):
                captcha_solved, captcha_msg = await solve_captcha(client, event.message)
                if captcha_solved:
                    await bot.send_message(user_id, f"🤖 {captcha_msg}")

# ========== ЗАПУСК МОНИТОРИНГА ==========
async def start_monitoring(user_id, client):
    if user_id in users_data:
        if users_data[user_id].get("monitor_task"):
            users_data[user_id]["monitor_task"].cancel()
        
        task = asyncio.create_task(monitor_messages(client, user_id))
        users_data[user_id]["monitor_task"] = task
        return True
    return False

# ========== ЮЗЕРБОТ ==========
async def send_loop_for_user(user_id: int):
    print(f"[USERBOT:{user_id}] Запущен")
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
            for msg in message_groups:
                if user_id not in users_data or not users_data[user_id].get("running"):
                    break
                delay = random.uniform(delay_min, delay_max)
                await asyncio.sleep(delay)
                try:
                    await client.send_message(target, msg)
                    print(f"[SENT:{user_id}] -> {target}")
                except errors.SessionRevokedError:
                    users_data[user_id]["client"] = None
                    users_data[user_id]["running"] = False
                    try:
                        await bot.send_message(user_id, "❌ Сессия истекла! Войди заново через кнопку 'АККАУНТ'")
                    except:
                        pass
                    break
                except Exception as e:
                    print(f"[ERROR:{user_id}] {e}")
        await asyncio.sleep(3)

# ========== КНОПКИ МЕНЮ ==========
def get_main_keyboard():
    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        InlineKeyboardButton("📊 СТАТУС", callback_data="status"),
        InlineKeyboardButton("▶️ СТАРТ", callback_data="start_spam"),
        InlineKeyboardButton("⏹️ СТОП", callback_data="stop_spam")
    )
    keyboard.add(
        InlineKeyboardButton("🎯 ЦЕЛИ", callback_data="targets_menu"),
        InlineKeyboardButton("💬 СООБЩЕНИЯ", callback_data="messages_menu")
    )
    keyboard.add(
        InlineKeyboardButton("⚙️ ЗАДЕРЖКА", callback_data="delay_menu"),
        InlineKeyboardButton("🔐 АККАУНТ", callback_data="account_menu")
    )
    keyboard.add(
        InlineKeyboardButton("🛡️ АВТО-ЗАЩИТА", callback_data="autoprotect_menu")
    )
    return keyboard

def get_autoprotect_keyboard(user_id):
    user = users_data.get(user_id, {})
    auto_captcha = user.get("auto_captcha", True)
    auto_subscribe = user.get("auto_subscribe", True)
    
    keyboard = InlineKeyboardMarkup(row_width=1)
    keyboard.add(
        InlineKeyboardButton(f"🤖 АВТО-КАПЧА: {'✅ ВКЛ' if auto_captcha else '❌ ВЫКЛ'}", callback_data="toggle_captcha"),
        InlineKeyboardButton(f"📢 АВТО-ПОДПИСКА: {'✅ ВКЛ' if auto_subscribe else '❌ ВЫКЛ'}", callback_data="toggle_subscribe")
    )
    keyboard.add(InlineKeyboardButton("🔙 НАЗАД", callback_data="back_main"))
    return keyboard

def get_targets_keyboard(user_id):
    targets = users_data.get(user_id, {}).get("targets", [])
    keyboard = InlineKeyboardMarkup(row_width=1)
    
    if targets:
        for i, target in enumerate(targets):
            keyboard.add(InlineKeyboardButton(f"❌ {target}", callback_data=f"del_target_{i}"))
        keyboard.add(InlineKeyboardButton("🗑️ ОЧИСТИТЬ ВСЕ", callback_data="clear_targets"))
    else:
        keyboard.add(InlineKeyboardButton("📭 СПИСОК ПУСТ", callback_data="noop"))
    
    keyboard.add(InlineKeyboardButton("➕ ДОБАВИТЬ ЦЕЛЬ", callback_data="add_target_start"))
    keyboard.add(InlineKeyboardButton("🔙 НАЗАД", callback_data="back_main"))
    return keyboard

def get_messages_keyboard(user_id):
    messages = users_data.get(user_id, {}).get("message_groups", [])
    keyboard = InlineKeyboardMarkup(row_width=1)
    
    if messages:
        for i, msg in enumerate(messages[:5]):
            preview = msg[:30] + "..." if len(msg) > 30 else msg
            keyboard.add(InlineKeyboardButton(f"❌ {preview}", callback_data=f"del_msg_{i}"))
        if len(messages) > 5:
            keyboard.add(InlineKeyboardButton(f"📊 ЕЩЕ {len(messages)-5}", callback_data="list_all_messages"))
        keyboard.add(InlineKeyboardButton("🗑️ ОЧИСТИТЬ ВСЕ", callback_data="clear_messages"))
    else:
        keyboard.add(InlineKeyboardButton("📭 СООБЩЕНИЙ НЕТ", callback_data="noop"))
    
    keyboard.add(InlineKeyboardButton("➕ ДОБАВИТЬ СООБЩЕНИЕ", callback_data="add_message_start"))
    keyboard.add(InlineKeyboardButton("🔙 НАЗАД", callback_data="back_main"))
    return keyboard

def get_delay_keyboard(current_min, current_max):
    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        InlineKeyboardButton("🐢 3-7 СЕК", callback_data="delay_3_7"),
        InlineKeyboardButton("⚡ 5-10 СЕК", callback_data="delay_5_10"),
        InlineKeyboardButton("🐌 10-20 СЕК", callback_data="delay_10_20"),
        InlineKeyboardButton("🎲 15-30 СЕК", callback_data="delay_15_30")
    )
    keyboard.add(InlineKeyboardButton(f"📊 ТЕКУЩАЯ: {current_min}-{current_max} СЕК", callback_data="noop"))
    keyboard.add(InlineKeyboardButton("🔙 НАЗАД", callback_data="back_main"))
    return keyboard

def get_account_keyboard(is_logged):
    keyboard = InlineKeyboardMarkup(row_width=1)
    if not is_logged:
        keyboard.add(InlineKeyboardButton("📱 ВОЙТИ", callback_data="login_start"))
    else:
        keyboard.add(InlineKeyboardButton("👤 ИНФО", callback_data="account_info"))
        keyboard.add(InlineKeyboardButton("🚪 ВЫЙТИ", callback_data="logout"))
    keyboard.add(InlineKeyboardButton("🔙 НАЗАД", callback_data="back_main"))
    return keyboard

def get_cancel_keyboard(back_callback):
    keyboard = InlineKeyboardMarkup(row_width=1)
    keyboard.add(InlineKeyboardButton("❌ ОТМЕНА", callback_data=back_callback))
    return keyboard

# ========== ОБРАБОТЧИКИ ==========
@dp.message_handler(commands=['start'])
async def cmd_start(message: Message):
    user_id = message.from_user.id
    if user_id not in users_data:
        create_new_user(user_id)
        await message.answer(
            "🤖 **USERBOT MANAGER v3.0**\n\n"
            "✅ Бот умеет:\n"
            "• Автоматически решать капчи\n"
            "• Автоматически подписываться на каналы\n"
            "• Проходить любые проверки\n\n"
            "🔐 Сначала войди в аккаунт через кнопку АККАУНТ\n\n"
            "👇 ВСЕ НАСТРОЙКИ ЧЕРЕЗ КНОПКИ 👇",
            reply_markup=get_main_keyboard(),
            parse_mode="Markdown"
        )
    else:
        await message.answer(
            "🤖 **ГЛАВНОЕ МЕНЮ**",
            reply_markup=get_main_keyboard(),
            parse_mode="Markdown"
        )

@dp.callback_query_handler(lambda c: True)
async def handle_callback(callback: CallbackQuery):
    user_id = callback.from_user.id
    data = callback.data
    
    if user_id not in users_data:
        create_new_user(user_id)
    
    user = users_data[user_id]
    is_logged = user.get("client") is not None
    
    # ===== СТАТУС =====
    if data == "status":
        auto_cap = "✅" if user.get("auto_captcha", True) else "❌"
        auto_sub = "✅" if user.get("auto_subscribe", True) else "❌"
        
        text = (
            f"📊 **СТАТУС**\n\n"
            f"🔐 Аккаунт: {'✅ ВОШЕЛ' if is_logged else '❌ НЕ ВОШЕЛ'}\n"
            f"📱 Номер: {user.get('phone', 'НЕТ')}\n"
            f"▶️ Рассылка: {'🟢 РАБОТАЕТ' if user.get('running') else '🔴 ОСТАНОВЛЕНА'}\n"
            f"🎯 Целей: {len(user.get('targets', []))}\n"
            f"💬 Сообщений: {len(user.get('message_groups', []))}\n"
            f"⏱️ Задержка: {user.get('delay_min', 5)}-{user.get('delay_max', 10)} СЕК\n\n"
            f"🛡️ **АВТО-ЗАЩИТА:**\n"
            f"• Авто-капча: {auto_cap}\n"
            f"• Авто-подписка: {auto_sub}"
        )
        try:
            await callback.message.edit_text(text, reply_markup=get_main_keyboard(), parse_mode="Markdown")
        except:
            await callback.message.answer(text, reply_markup=get_main_keyboard(), parse_mode="Markdown")
        await callback.answer()
    
    # ===== АВТО-ЗАЩИТА =====
    elif data == "autoprotect_menu":
        try:
            await callback.message.edit_text(
                "🛡️ **АВТОМАТИЧЕСКАЯ ЗАЩИТА**\n\n"
                "🤖 **АВТО-КАПЧА** - бот сам решает любые капчи\n"
                "📢 **АВТО-ПОДПИСКА** - бот сам подписывается на каналы\n\n"
                "⚠️ Включи обе функции для полной автоматизации",
                reply_markup=get_autoprotect_keyboard(user_id),
                parse_mode="Markdown"
            )
        except:
            await callback.message.answer(
                "🛡️ **АВТО-ЗАЩИТА**",
                reply_markup=get_autoprotect_keyboard(user_id),
                parse_mode="Markdown"
            )
    
    elif data == "toggle_captcha":
        user["auto_captcha"] = not user.get("auto_captcha", True)
        save_users()
        status = "ВКЛЮЧЕНА" if user["auto_captcha"] else "ВЫКЛЮЧЕНА"
        await callback.answer(f"🤖 АВТО-КАПЧА {status}!", show_alert=True)
        try:
            await callback.message.edit_text(
                "🛡️ **АВТОМАТИЧЕСКАЯ ЗАЩИТА**",
                reply_markup=get_autoprotect_keyboard(user_id),
                parse_mode="Markdown"
            )
        except:
            pass
    
    elif data == "toggle_subscribe":
        user["auto_subscribe"] = not user.get("auto_subscribe", True)
        save_users()
        status = "ВКЛЮЧЕНА" if user["auto_subscribe"] else "ВЫКЛЮЧЕНА"
        await callback.answer(f"📢 АВТО-ПОДПИСКА {status}!", show_alert=True)
        try:
            await callback.message.edit_text(
                "🛡️ **АВТОМАТИЧЕСКАЯ ЗАЩИТА**",
                reply_markup=get_autoprotect_keyboard(user_id),
                parse_mode="Markdown"
            )
        except:
            pass
    
    # ===== СТАРТ/СТОП =====
    elif data == "start_spam":
        if not is_logged:
            await callback.answer("❌ СНАЧАЛА ВОЙДИ В АККАУНТ!", show_alert=True)
        else:
            user["running"] = True
            save_users()
            if user.get("client") and not user.get("task"):
                user["task"] = asyncio.create_task(send_loop_for_user(user_id))
            await callback.answer("✅ РАССЫЛКА ЗАПУЩЕНА!", show_alert=True)
            try:
                await callback.message.edit_text("✅ **РАССЫЛКА ЗАПУЩЕНА**", reply_markup=get_main_keyboard(), parse_mode="Markdown")
            except:
                await callback.message.answer("✅ **РАССЫЛКА ЗАПУЩЕНА**", reply_markup=get_main_keyboard(), parse_mode="Markdown")
    
    elif data == "stop_spam":
        user["running"] = False
        save_users()
        await callback.answer("⏹️ РАССЫЛКА ОСТАНОВЛЕНА!", show_alert=True)
        try:
            await callback.message.edit_text("⏹️ **РАССЫЛКА ОСТАНОВЛЕНА**", reply_markup=get_main_keyboard(), parse_mode="Markdown")
        except:
            await callback.message.answer("⏹️ **РАССЫЛКА ОСТАНОВЛЕНА**", reply_markup=get_main_keyboard(), parse_mode="Markdown")
    
    # ===== ЦЕЛИ =====
    elif data == "targets_menu":
        targets = user.get("targets", [])
        if targets:
            text = "🎯 **ТВОИ ЦЕЛИ:**\n\n" + "\n".join([f"• {t}" for t in targets])
        else:
            text = "🎯 **СПИСОК ЦЕЛЕЙ ПУСТ**"
        try:
            await callback.message.edit_text(text, reply_markup=get_targets_keyboard(user_id), parse_mode="Markdown")
        except:
            await callback.message.answer(text, reply_markup=get_targets_keyboard(user_id), parse_mode="Markdown")
    
    elif data == "add_target_start":
        temp_data[user_id] = {"action": "add_target"}
        try:
            await callback.message.edit_text(
                "➕ **ДОБАВЛЕНИЕ ЦЕЛИ**\n\n"
                "📝 **ОТПРАВЬ USERNAME:**\n\n"
                "Пример: `@durov` или `https://t.me/durov`",
                reply_markup=get_cancel_keyboard("targets_menu"),
                parse_mode="Markdown"
            )
        except:
            await callback.message.answer(
                "➕ **ДОБАВЛЕНИЕ ЦЕЛИ**\n\nОТПРАВЬ USERNAME: @durov",
                reply_markup=get_cancel_keyboard("targets_menu"),
                parse_mode="Markdown"
            )
    
    elif data.startswith("del_target_"):
        idx = int(data.split("_")[2])
        targets = user.get("targets", [])
        if 0 <= idx < len(targets):
            removed = targets.pop(idx)
            user["targets"] = targets
            save_users()
            await callback.answer(f"✅ УДАЛЕНО: {removed}", show_alert=True)
            
            if targets:
                text = "🎯 **ТВОИ ЦЕЛИ:**\n\n" + "\n".join([f"• {t}" for t in targets])
            else:
                text = "🎯 **СПИСОК ЦЕЛЕЙ ПУСТ**"
            try:
                await callback.message.edit_text(text, reply_markup=get_targets_keyboard(user_id), parse_mode="Markdown")
            except:
                await callback.message.answer(text, reply_markup=get_targets_keyboard(user_id), parse_mode="Markdown")
    
    elif data == "clear_targets":
        user["targets"] = []
        save_users()
        await callback.answer("🗑️ ВСЕ ЦЕЛИ ОЧИЩЕНЫ!", show_alert=True)
        try:
            await callback.message.edit_text("🎯 **ВСЕ ЦЕЛИ ОЧИЩЕНЫ**", reply_markup=get_targets_keyboard(user_id), parse_mode="Markdown")
        except:
            await callback.message.answer("🎯 **ВСЕ ЦЕЛИ ОЧИЩЕНЫ**", reply_markup=get_targets_keyboard(user_id), parse_mode="Markdown")
    
    # ===== СООБЩЕНИЯ =====
    elif data == "messages_menu":
        messages = user.get("message_groups", [])
        if messages:
            text = "💬 **ТВОИ СООБЩЕНИЯ:**\n\n"
            for i, msg in enumerate(messages[:10], 1):
                preview = msg[:40] + "..." if len(msg) > 40 else msg
                text += f"{i}. {preview}\n"
        else:
            text = "💬 **СООБЩЕНИЙ НЕТ**"
        try:
            await callback.message.edit_text(text, reply_markup=get_messages_keyboard(user_id), parse_mode="Markdown")
        except:
            await callback.message.answer(text, reply_markup=get_messages_keyboard(user_id), parse_mode="Markdown")
    
    elif data == "add_message_start":
        temp_data[user_id] = {"action": "add_message"}
        try:
            await callback.message.edit_text(
                "📝 **ДОБАВЛЕНИЕ СООБЩЕНИЯ**\n\n"
                "📤 **ОТПРАВЬ ТЕКСТ СООБЩЕНИЯ:**\n\n"
                "Можно отправить любое текстовое сообщение",
                reply_markup=get_cancel_keyboard("messages_menu"),
                parse_mode="Markdown"
            )
        except:
            await callback.message.answer(
                "📝 **ДОБАВЛЕНИЕ СООБЩЕНИЯ**\n\nОТПРАВЬ ТЕКСТ",
                reply_markup=get_cancel_keyboard("messages_menu"),
                parse_mode="Markdown"
            )
    
    elif data.startswith("del_msg_"):
        idx = int(data.split("_")[2])
        messages = user.get("message_groups", [])
        if 0 <= idx < len(messages):
            removed = messages.pop(idx)
            user["message_groups"] = messages
            save_users()
            await callback.answer("✅ СООБЩЕНИЕ УДАЛЕНО!", show_alert=True)
            
            if messages:
                text = "💬 **ТВОИ СООБЩЕНИЯ:**\n\n"
                for i, msg in enumerate(messages[:10], 1):
                    preview = msg[:40] + "..." if len(msg) > 40 else msg
                    text += f"{i}. {preview}\n"
            else:
                text = "💬 **СООБЩЕНИЙ НЕТ**"
            try:
                await callback.message.edit_text(text, reply_markup=get_messages_keyboard(user_id), parse_mode="Markdown")
            except:
                await callback.message.answer(text, reply_markup=get_messages_keyboard(user_id), parse_mode="Markdown")
    
    elif data == "clear_messages":
        user["message_groups"] = []
        save_users()
        await callback.answer("🗑️ ВСЕ СООБЩЕНИЯ ОЧИЩЕНЫ!", show_alert=True)
        try:
            await callback.message.edit_text("💬 **ВСЕ СООБЩЕНИЯ ОЧИЩЕНЫ**", reply_markup=get_messages_keyboard(user_id), parse_mode="Markdown")
        except:
            await callback.message.answer("💬 **ВСЕ СООБЩЕНИЯ ОЧИЩЕНЫ**", reply_markup=get_messages_keyboard(user_id), parse_mode="Markdown")
    
    elif data == "list_all_messages":
        messages = user.get("message_groups", [])
        if messages:
            text = "📋 **ВСЕ СООБЩЕНИЯ:**\n\n"
            for i, msg in enumerate(messages, 1):
                preview = msg[:60] + "..." if len(msg) > 60 else msg
                text += f"{i}. {preview}\n\n"
            keyboard = InlineKeyboardMarkup(row_width=1)
            keyboard.add(InlineKeyboardButton("🔙 НАЗАД", callback_data="messages_menu"))
            try:
                await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="Markdown")
            except:
                await callback.message.answer(text, reply_markup=keyboard, parse_mode="Markdown")
    
    # ===== ЗАДЕРЖКА =====
    elif data == "delay_menu":
        try:
            await callback.message.edit_text(
                f"⚙️ **НАСТРОЙКА ЗАДЕРЖКИ**\n\n"
                f"📊 ТЕКУЩАЯ: {user.get('delay_min', 5)}-{user.get('delay_max', 10)} СЕК",
                reply_markup=get_delay_keyboard(user.get('delay_min', 5), user.get('delay_max', 10)),
                parse_mode="Markdown"
            )
        except:
            await callback.message.answer(
                f"⚙️ **НАСТРОЙКА ЗАДЕРЖКИ**\n\nТЕКУЩАЯ: {user.get('delay_min', 5)}-{user.get('delay_max', 10)} СЕК",
                reply_markup=get_delay_keyboard(user.get('delay_min', 5), user.get('delay_max', 10)),
                parse_mode="Markdown"
            )
    
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
        await callback.answer(f"✅ ЗАДЕРЖКА: {user['delay_min']}-{user['delay_max']} СЕК", show_alert=True)
        try:
            await callback.message.edit_text(
                f"⚙️ **ЗАДЕРЖКА ОБНОВЛЕНА**\n\n✅ {user['delay_min']}-{user['delay_max']} СЕКУНД",
                reply_markup=get_delay_keyboard(user['delay_min'], user['delay_max']),
                parse_mode="Markdown"
            )
        except:
            await callback.message.answer(
                f"⚙️ **ЗАДЕРЖКА ОБНОВЛЕНА**\n\n✅ {user['delay_min']}-{user['delay_max']} СЕКУНД",
                reply_markup=get_delay_keyboard(user['delay_min'], user['delay_max']),
                parse_mode="Markdown"
            )
    
    # ===== АККАУНТ =====
    elif data == "account_menu":
        try:
            await callback.message.edit_text(
                f"🔐 **УПРАВЛЕНИЕ АККАУНТОМ**\n\n"
                f"📊 СТАТУС: {'✅ ВОШЕЛ' if is_logged else '❌ НЕ ВОШЕЛ'}\n"
                f"📱 НОМЕР: {user.get('phone', 'НЕТ')}",
                reply_markup=get_account_keyboard(is_logged),
                parse_mode="Markdown"
            )
        except:
            await callback.message.answer(
                f"🔐 **АККАУНТ**\n\nСТАТУС: {'✅ ВОШЕЛ' if is_logged else '❌ НЕ ВОШЕЛ'}",
                reply_markup=get_account_keyboard(is_logged),
                parse_mode="Markdown"
            )
    
    elif data == "login_start":
        temp_data[user_id] = {"action": "login", "step": "phone"}
        try:
            await callback.message.edit_text(
                "📱 **ВХОД В АККАУНТ**\n\n"
                "📝 **ОТПРАВЬ НОМЕР ТЕЛЕФОНА:**\n\n"
                "Формат: `+71234567890`",
                reply_markup=get_cancel_keyboard("account_menu"),
                parse_mode="Markdown"
            )
        except:
            await callback.message.answer(
                "📱 **ВХОД В АККАУНТ**\n\nОТПРАВЬ НОМЕР: +71234567890",
                reply_markup=get_cancel_keyboard("account_menu"),
                parse_mode="Markdown"
            )
    
    elif data == "account_info":
        if is_logged and user.get("client"):
            try:
                me = await user["client"].get_me()
                await callback.answer(f"👤 {me.first_name} (@{me.username})", show_alert=True)
            except:
                await callback.answer("❌ ОШИБКА", show_alert=True)
        else:
            await callback.answer("❌ НЕ АВТОРИЗОВАН", show_alert=True)
    
    elif data == "logout":
        if user.get("client"):
            await user["client"].disconnect()
        if user.get("task"):
            user["task"].cancel()
        if user.get("monitor_task"):
            user["monitor_task"].cancel()
        user["client"] = None
        user["task"] = None
        user["monitor_task"] = None
        user["running"] = False
        user["phone"] = None
        save_users()
        await callback.answer("🚪 ВЫШЕЛ ИЗ АККАУНТА!", show_alert=True)
        try:
            await callback.message.edit_text(
                "🔐 **ВЫ ВЫШЛИ ИЗ АККАУНТА**",
                reply_markup=get_account_keyboard(False),
                parse_mode="Markdown"
            )
        except:
            await callback.message.answer(
                "🔐 **ВЫ ВЫШЛИ ИЗ АККАУНТА**",
                reply_markup=get_account_keyboard(False),
                parse_mode="Markdown"
            )
    
    # ===== НАЗАД =====
    elif data == "back_main":
        try:
            await callback.message.edit_text("🤖 **ГЛАВНОЕ МЕНЮ**", reply_markup=get_main_keyboard(), parse_mode="Markdown")
        except:
            await callback.message.answer("🤖 **ГЛАВНОЕ МЕНЮ**", reply_markup=get_main_keyboard(), parse_mode="Markdown")
    
    elif data == "noop":
        await callback.answer()
    
    await callback.answer()

# ===== ОБРАБОТКА ТЕКСТОВЫХ СООБЩЕНИЙ =====
@dp.message_handler()
async def handle_text(message: Message):
    user_id = message.from_user.id
    text = message.text.strip()
    
    # Добавление цели
    if user_id in temp_data and temp_data[user_id].get("action") == "add_target":
        target = text.replace("https://t.me/", "").replace("@", "").strip()
        if target:
            target = f"@{target}"
            
            if user_id not in users_data:
                create_new_user(user_id)
            
            if target not in users_data[user_id]["targets"]:
                users_data[user_id]["targets"].append(target)
                save_users()
                await message.answer(f"✅ **ЦЕЛЬ ДОБАВЛЕНА:** {target}\n\n📊 ВСЕГО ЦЕЛЕЙ: {len(users_data[user_id]['targets'])}", parse_mode="Markdown")
            else:
                await message.answer(f"⚠️ ЦЕЛЬ {target} УЖЕ СУЩЕСТВУЕТ", parse_mode="Markdown")
        else:
            await message.answer("❌ НЕВЕРНЫЙ ФОРМАТ", parse_mode="Markdown")
        
        del temp_data[user_id]
        return
    
    # Добавление сообщения
    if user_id in temp_data and temp_data[user_id].get("action") == "add_message":
        if text:
            if user_id not in users_data:
                create_new_user(user_id)
            
            users_data[user_id]["message_groups"].append(text)
            save_users()
            await message.answer(
                f"✅ **СООБЩЕНИЕ ДОБАВЛЕНО!**\n\n"
                f"📝 ТЕКСТ: {text[:100]}\n"
                f"📊 ВСЕГО СООБЩЕНИЙ: {len(users_data[user_id]['message_groups'])}",
                parse_mode="Markdown"
            )
        else:
            await message.answer("❌ ТЕКСТ НЕ МОЖЕТ БЫТЬ ПУСТЫМ", parse_mode="Markdown")
        
        del temp_data[user_id]
        return
    
    # Логин
    if user_id in temp_data and temp_data[user_id].get("action") == "login":
        step = temp_data[user_id].get("step")
        
        if step == "phone":
            phone = text if text.startswith("+") else "+" + text
            
            try:
                session_name = f"user_{user_id}"
                client = TelegramClient(session_name, API_ID, API_HASH)
                await client.connect()
                await client.send_code_request(phone)
                
                temp_data[user_id] = {"action": "login", "step": "code", "client": client, "phone": phone, "session_name": session_name}
                
                await message.answer(
                    f"📱 **КОД ОТПРАВЛЕН НА {phone}**\n\n"
                    f"📝 **ОТПРАВЬ КОД:** (можно с разделителями 1#2#3#4#5)",
                    parse_mode="Markdown"
                )
            except Exception as e:
                await message.answer(f"❌ ОШИБКА: {str(e)}", parse_mode="Markdown")
                del temp_data[user_id]
        
        elif step == "code":
            code = decode_code(text)
            if code and len(code) >= 4:
                client = temp_data[user_id].get("client")
                phone = temp_data[user_id].get("phone")
                
                try:
                    await client.sign_in(phone, code=code)
                    
                    if user_id not in users_data:
                        create_new_user(user_id)
                    
                    users_data[user_id]["client"] = client
                    users_data[user_id]["phone"] = phone
                    save_users()
                    
                    # ЗАПУСКАЕМ МОНИТОРИНГ
                    await start_monitoring(user_id, client)
                    
                    del temp_data[user_id]
                    
                    await message.answer(
                        f"✅ **УСПЕШНЫЙ ВХОД!**\n\n"
                        f"📱 АККАУНТ: {phone}\n"
                        f"🛡️ АВТО-ЗАЩИТА АКТИВНА!\n\n"
                        f"🤖 Бот будет автоматически:\n"
                        f"• Решать капчи\n"
                        f"• Подписываться на каналы\n\n"
                        f"🎉 ТЕПЕРЬ МОЖНО НАСТРОИТЬ РАССЫЛКУ",
                        reply_markup=get_main_keyboard(),
                        parse_mode="Markdown"
                    )
                except errors.SessionPasswordNeededError:
                    temp_data[user_id]["step"] = "2fa"
                    await message.answer(
                        "🔐 **ТРЕБУЕТСЯ 2FA ПАРОЛЬ!**\n\n📝 ОТПРАВЬ ПАРОЛЬ:",
                        parse_mode="Markdown"
                    )
                except Exception as e:
                    await message.answer(f"❌ ОШИБКА: {str(e)}", parse_mode="Markdown")
                    del temp_data[user_id]
            else:
                await message.answer("❌ НЕ МОГУ РАСПОЗНАТЬ КОД. ПОПРОБУЙ СНОВА", parse_mode="Markdown")
        
        elif step == "2fa":
            password = text
            client = temp_data[user_id].get("client")
            phone = temp_data[user_id].get("phone")
            
            try:
                await client.sign_in(password=password)
                
                if user_id not in users_data:
                    create_new_user(user_id)
                
                users_data[user_id]["client"] = client
                users_data[user_id]["phone"] = phone
                save_users()
                
                # ЗАПУСКАЕМ МОНИТОРИНГ
                await start_monitoring(user_id, client)
                
                del temp_data[user_id]
                
                await message.answer(
                    f"✅ **УСПЕШНЫЙ ВХОД С 2FA!**\n\n"
                    f"📱 АККАУНТ: {phone}\n"
                    f"🛡️ АВТО-ЗАЩИТА АКТИВНА!",
                    reply_markup=get_main_keyboard(),
                    parse_mode="Markdown"
                )
            except Exception as e:
                await message.answer(f"❌ ОШИБКА: {str(e)}", parse_mode="Markdown")
                del temp_data[user_id]

# ========== ЗАПУСК ==========
async def main():
    load_users()
    print("=" * 60)
    print("🤖 БОТ ЗАПУЩЕН")
    print("🛡️ АВТО-ПРОХОЖДЕНИЕ КАПЧ АКТИВНО")
    print("📢 АВТО-ПОДПИСКА НА КАНАЛЫ АКТИВНА")
    print("=" * 60)
    
    # Восстанавливаем мониторинг для уже авторизованных
    for user_id, user in users_data.items():
        if user.get("client"):
            await start_monitoring(user_id, user["client"])
            if user.get("running"):
                user["task"] = asyncio.create_task(send_loop_for_user(user_id))
    
    await dp.start_polling()

if __name__ == "__main__":
    asyncio.run(main())
