import asyncio
import random
import json
import re
import os
from telethon import TelegramClient, errors, events
from telethon.tl.functions.channels import JoinChannelRequest
from aiogram import Bot, Dispatcher, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, Message
from aiogram.contrib.middlewares.logging import LoggingMiddleware

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
            "messages": data.get("messages", []),
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
        "messages": [],
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
    digits = re.sub(r'\D', '', encoded_string)
    return digits if len(digits) >= 4 else ""

# ========== АВТО-РЕШЕНИЕ КАПЧ ==========
async def solve_captcha(client, message):
    text = message.text.lower() if message.text else ""
    
    numbers = re.findall(r'\b\d{4,6}\b', text)
    if numbers:
        await client.send_message(message.chat_id, numbers[0])
        return True, f"✅ Решил капчу: {numbers[0]}"
    
    if message.reply_markup:
        for row in message.reply_markup.rows:
            for button in row.buttons:
                if any(word in button.text.lower() for word in ['не робот', 'captcha', 'verify', 'проверк', 'start']):
                    await message.click(button.text)
                    return True, f"✅ Нажал кнопку: {button.text}"
    
    if 'start' in text or 'начать' in text:
        await client.send_message(message.chat_id, "/start")
        return True, "✅ Отправил /start"
    
    return False, ""

# ========== АВТО-ПОДПИСКА ==========
async def auto_subscribe(client, message):
    text = message.text.lower() if message.text else ""
    
    patterns = [
        r'(?:https?://)?(?:www\.)?t\.me/([a-zA-Z0-9_]+)',
        r'@([a-zA-Z0-9_]{5,})'
    ]
    
    channels = []
    for pattern in patterns:
        matches = re.findall(pattern, text)
        channels.extend(matches)
    
    results = []
    for channel in set(channels):
        if len(channel) > 3:
            try:
                entity = await client.get_entity(f"@{channel}")
                await client(JoinChannelRequest(entity))
                results.append(f"✅ Подписался на @{channel}")
            except:
                pass
    return results

# ========== МОНИТОРИНГ ==========
async def monitor_messages(client, user_id):
    @client.on(events.NewMessage(incoming=True))
    async def handler(event):
        if event.is_private:
            user = users_data.get(user_id, {})
            
            if user.get("auto_subscribe", True):
                results = await auto_subscribe(client, event.message)
                for r in results:
                    await bot.send_message(user_id, r)
            
            if user.get("auto_captcha", True):
                solved, msg = await solve_captcha(client, event.message)
                if solved:
                    await bot.send_message(user_id, msg)

async def start_monitoring(user_id, client):
    if users_data[user_id].get("monitor_task"):
        users_data[user_id]["monitor_task"].cancel()
    users_data[user_id]["monitor_task"] = asyncio.create_task(monitor_messages(client, user_id))

# ========== ОТПРАВКА ==========
async def send_loop(user_id: int):
    while True:
        if user_id not in users_data:
            break
        user = users_data[user_id]
        if not user.get("running"):
            await asyncio.sleep(2)
            continue
        
        messages = user.get("messages", [])
        targets = user.get("targets", [])
        delay_min = user.get("delay_min", 5)
        delay_max = user.get("delay_max", 10)
        
        if not messages or not targets:
            await asyncio.sleep(3)
            continue
        
        client = user.get("client")
        if not client:
            await asyncio.sleep(5)
            continue
        
        for target in targets:
            for msg in messages:
                if not users_data[user_id].get("running"):
                    break
                
                delay = random.uniform(delay_min, delay_max)
                await asyncio.sleep(delay)
                
                try:
                    if isinstance(msg, dict) and msg.get("type") == "photo":
                        if msg.get("file_path") and os.path.exists(msg["file_path"]):
                            await client.send_file(target, msg["file_path"], caption=msg.get("caption", ""))
                        else:
                            await client.send_file(target, msg["file_id"], caption=msg.get("caption", ""))
                    else:
                        await client.send_message(target, str(msg))
                    print(f"[SENT] {user_id} -> {target}")
                except errors.SessionRevokedError:
                    users_data[user_id]["client"] = None
                    users_data[user_id]["running"] = False
                    await bot.send_message(user_id, "❌ Сессия истекла! Войди заново")
                    break
                except Exception as e:
                    print(f"[ERROR] {e}")
        
        await asyncio.sleep(3)

# ========== КНОПКИ ==========
def main_keyboard():
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton("📊 СТАТУС", callback_data="status"),
        InlineKeyboardButton("▶️ СТАРТ", callback_data="start"),
        InlineKeyboardButton("⏹️ СТОП", callback_data="stop")
    )
    kb.add(
        InlineKeyboardButton("🎯 ЦЕЛИ", callback_data="targets"),
        InlineKeyboardButton("💬 СООБЩЕНИЯ", callback_data="messages")
    )
    kb.add(
        InlineKeyboardButton("⚙️ ЗАДЕРЖКА", callback_data="delay"),
        InlineKeyboardButton("🔐 АККАУНТ", callback_data="account"),
        InlineKeyboardButton("🛡️ АВТО", callback_data="auto")
    )
    return kb

def targets_keyboard(user_id):
    targets = users_data.get(user_id, {}).get("targets", [])
    kb = InlineKeyboardMarkup(row_width=1)
    for i, t in enumerate(targets):
        kb.add(InlineKeyboardButton(f"❌ {t}", callback_data=f"del_target_{i}"))
    kb.add(InlineKeyboardButton("➕ ДОБАВИТЬ", callback_data="add_target"))
    kb.add(InlineKeyboardButton("🗑️ ОЧИСТИТЬ", callback_data="clear_targets"))
    kb.add(InlineKeyboardButton("🔙 НАЗАД", callback_data="back"))
    return kb

def messages_keyboard(user_id):
    msgs = users_data.get(user_id, {}).get("messages", [])
    kb = InlineKeyboardMarkup(row_width=1)
    for i, m in enumerate(msgs[:5]):
        if isinstance(m, dict):
            kb.add(InlineKeyboardButton(f"❌ ФОТО {i+1}", callback_data=f"del_msg_{i}"))
        else:
            preview = m[:25] + "..." if len(m) > 25 else m
            kb.add(InlineKeyboardButton(f"❌ {preview}", callback_data=f"del_msg_{i}"))
    kb.add(InlineKeyboardButton("📝 ДОБАВИТЬ ТЕКСТ", callback_data="add_text"))
    kb.add(InlineKeyboardButton("📸 ДОБАВИТЬ ФОТО", callback_data="add_photo"))
    kb.add(InlineKeyboardButton("🗑️ ОЧИСТИТЬ", callback_data="clear_messages"))
    kb.add(InlineKeyboardButton("🔙 НАЗАД", callback_data="back"))
    return kb

def delay_keyboard(current_min, current_max):
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton("3-7 СЕК", callback_data="delay_3_7"),
        InlineKeyboardButton("5-10 СЕК", callback_data="delay_5_10"),
        InlineKeyboardButton("10-20 СЕК", callback_data="delay_10_20"),
        InlineKeyboardButton("15-30 СЕК", callback_data="delay_15_30")
    )
    kb.add(InlineKeyboardButton(f"📊 {current_min}-{current_max} СЕК", callback_data="noop"))
    kb.add(InlineKeyboardButton("🔙 НАЗАД", callback_data="back"))
    return kb

def account_keyboard(is_logged):
    kb = InlineKeyboardMarkup(row_width=1)
    if not is_logged:
        kb.add(InlineKeyboardButton("📱 ВОЙТИ", callback_data="login"))
    else:
        kb.add(InlineKeyboardButton("👤 ИНФО", callback_data="info"))
        kb.add(InlineKeyboardButton("🚪 ВЫЙТИ", callback_data="logout"))
    kb.add(InlineKeyboardButton("🔙 НАЗАД", callback_data="back"))
    return kb

def auto_keyboard(user_id):
    user = users_data.get(user_id, {})
    cap = "✅ ВКЛ" if user.get("auto_captcha", True) else "❌ ВЫКЛ"
    sub = "✅ ВКЛ" if user.get("auto_subscribe", True) else "❌ ВЫКЛ"
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(InlineKeyboardButton(f"🤖 КАПЧА: {cap}", callback_data="toggle_cap"))
    kb.add(InlineKeyboardButton(f"📢 ПОДПИСКА: {sub}", callback_data="toggle_sub"))
    kb.add(InlineKeyboardButton("🔙 НАЗАД", callback_data="back"))
    return kb

def back_keyboard(back_to):
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(InlineKeyboardButton("❌ ОТМЕНА", callback_data=back_to))
    return kb

# ========== ОБРАБОТЧИКИ ==========
@dp.message_handler(commands=['start'])
async def start_cmd(message: Message):
    uid = message.from_user.id
    if uid not in users_data:
        create_new_user(uid)
    await message.answer("🤖 **ГОТОВ К РАБОТЕ**\n\n👇 ВЫБЕРИ ДЕЙСТВИЕ", reply_markup=main_keyboard(), parse_mode="Markdown")

@dp.callback_query_handler(lambda c: True)
async def handle_callback(call: CallbackQuery):
    uid = call.from_user.id
    data = call.data
    
    if uid not in users_data:
        create_new_user(uid)
    
    user = users_data[uid]
    is_logged = user.get("client") is not None
    
    # СТАТУС
    if data == "status":
        await call.message.edit_text(
            f"📊 **СТАТУС**\n\n"
            f"🔐 АККАУНТ: {'✅ ВОШЕЛ' if is_logged else '❌ НЕ ВОШЕЛ'}\n"
            f"📱 НОМЕР: {user.get('phone', 'НЕТ')}\n"
            f"▶️ РАССЫЛКА: {'🟢 РАБОТАЕТ' if user.get('running') else '🔴 СТОП'}\n"
            f"🎯 ЦЕЛЕЙ: {len(user.get('targets', []))}\n"
            f"💬 СООБЩЕНИЙ: {len(user.get('messages', []))}\n"
            f"⏱️ ЗАДЕРЖКА: {user.get('delay_min', 5)}-{user.get('delay_max', 10)} СЕК\n"
            f"🛡️ АВТО-ЗАЩИТА: {'ВКЛ' if user.get('auto_captcha', True) else 'ВЫКЛ'}",
            reply_markup=main_keyboard(), parse_mode="Markdown"
        )
        await call.answer()
    
    # СТАРТ/СТОП
    elif data == "start":
        if not is_logged:
            await call.answer("❌ ВОЙДИ В АККАУНТ!", show_alert=True)
        else:
            user["running"] = True
            save_users()
            if user.get("client") and not user.get("task"):
                user["task"] = asyncio.create_task(send_loop(uid))
            await call.answer("✅ ЗАПУЩЕНО!", show_alert=True)
            await call.message.edit_text("✅ **РАССЫЛКА ЗАПУЩЕНА**", reply_markup=main_keyboard(), parse_mode="Markdown")
    
    elif data == "stop":
        user["running"] = False
        save_users()
        await call.answer("⏹️ ОСТАНОВЛЕНО!", show_alert=True)
        await call.message.edit_text("⏹️ **РАССЫЛКА ОСТАНОВЛЕНА**", reply_markup=main_keyboard(), parse_mode="Markdown")
    
    # ЦЕЛИ
    elif data == "targets":
        targets = user.get("targets", [])
        text = "🎯 **ЦЕЛИ:**\n\n" + "\n".join([f"• {t}" for t in targets]) if targets else "🎯 **ЦЕЛИ ПУСТЫ**"
        await call.message.edit_text(text, reply_markup=targets_keyboard(uid), parse_mode="Markdown")
    
    elif data == "add_target":
        temp_data[uid] = {"action": "add_target"}
        await call.message.edit_text(
            "➕ **ДОБАВЛЕНИЕ ЦЕЛИ**\n\n"
            "📝 **ОТПРАВЬ USERNAME:**\n\n"
            "Пример: @durov или https://t.me/durov",
            reply_markup=back_keyboard("targets"), parse_mode="Markdown"
        )
    
    elif data.startswith("del_target_"):
        idx = int(data.split("_")[2])
        targets = user.get("targets", [])
        if idx < len(targets):
            targets.pop(idx)
            user["targets"] = targets
            save_users()
            await call.answer("✅ УДАЛЕНО!", show_alert=True)
            text = "🎯 **ЦЕЛИ:**\n\n" + "\n".join([f"• {t}" for t in targets]) if targets else "🎯 **ЦЕЛИ ПУСТЫ**"
            await call.message.edit_text(text, reply_markup=targets_keyboard(uid), parse_mode="Markdown")
    
    elif data == "clear_targets":
        user["targets"] = []
        save_users()
        await call.answer("🗑️ ОЧИЩЕНО!", show_alert=True)
        await call.message.edit_text("🎯 **ВСЕ ЦЕЛИ ОЧИЩЕНЫ**", reply_markup=targets_keyboard(uid), parse_mode="Markdown")
    
    # СООБЩЕНИЯ
    elif data == "messages":
        msgs = user.get("messages", [])
        if not msgs:
            await call.message.edit_text("💬 **СООБЩЕНИЙ НЕТ**", reply_markup=messages_keyboard(uid), parse_mode="Markdown")
        else:
            text = "💬 **СООБЩЕНИЯ:**\n\n"
            for i, m in enumerate(msgs, 1):
                if isinstance(m, dict):
                    text += f"{i}. 📸 ФОТО\n"
                else:
                    text += f"{i}. {m[:40]}\n"
            await call.message.edit_text(text, reply_markup=messages_keyboard(uid), parse_mode="Markdown")
    
    elif data == "add_text":
        temp_data[uid] = {"action": "add_text"}
        await call.message.edit_text(
            "📝 **ДОБАВЛЕНИЕ ТЕКСТА**\n\n"
            "📤 **ОТПРАВЬ ТЕКСТ:**",
            reply_markup=back_keyboard("messages"), parse_mode="Markdown"
        )
    
    elif data == "add_photo":
        temp_data[uid] = {"action": "add_photo", "waiting": True}
        await call.message.edit_text(
            "📸 **ДОБАВЛЕНИЕ ФОТО**\n\n"
            "📤 **ОТПРАВЬ ФОТО** (можно с подписью)\n\n"
            "💡 После отправки фото добавится в список",
            reply_markup=back_keyboard("messages"), parse_mode="Markdown"
        )
    
    elif data.startswith("del_msg_"):
        idx = int(data.split("_")[2])
        msgs = user.get("messages", [])
        if idx < len(msgs):
            msgs.pop(idx)
            user["messages"] = msgs
            save_users()
            await call.answer("✅ УДАЛЕНО!", show_alert=True)
            await call.message.edit_text("💬 **ОБНОВЛЕНО**", reply_markup=messages_keyboard(uid), parse_mode="Markdown")
    
    elif data == "clear_messages":
        user["messages"] = []
        save_users()
        await call.answer("🗑️ ОЧИЩЕНО!", show_alert=True)
        await call.message.edit_text("💬 **ВСЕ СООБЩЕНИЯ ОЧИЩЕНЫ**", reply_markup=messages_keyboard(uid), parse_mode="Markdown")
    
    # ЗАДЕРЖКА
    elif data == "delay":
        await call.message.edit_text(
            f"⚙️ **ЗАДЕРЖКА:** {user.get('delay_min', 5)}-{user.get('delay_max', 10)} СЕК",
            reply_markup=delay_keyboard(user.get('delay_min', 5), user.get('delay_max', 10)),
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
        save_users()
        await call.answer(f"✅ {user['delay_min']}-{user['delay_max']} СЕК", show_alert=True)
        await call.message.edit_text(
            f"⚙️ **ЗАДЕРЖКА:** {user['delay_min']}-{user['delay_max']} СЕК",
            reply_markup=delay_keyboard(user['delay_min'], user['delay_max']),
            parse_mode="Markdown"
        )
    
    # АККАУНТ
    elif data == "account":
        await call.message.edit_text(
            f"🔐 **АККАУНТ**\n\n"
            f"СТАТУС: {'✅ ВОШЕЛ' if is_logged else '❌ НЕ ВОШЕЛ'}\n"
            f"НОМЕР: {user.get('phone', 'НЕТ')}",
            reply_markup=account_keyboard(is_logged), parse_mode="Markdown"
        )
    
    elif data == "login":
        temp_data[uid] = {"action": "login", "step": "phone"}
        await call.message.edit_text(
            "📱 **ВХОД**\n\n"
            "📝 **ОТПРАВЬ НОМЕР:** +71234567890",
            reply_markup=back_keyboard("account"), parse_mode="Markdown"
        )
    
    elif data == "info":
        if is_logged and user.get("client"):
            try:
                me = await user["client"].get_me()
                await call.answer(f"👤 {me.first_name} (@{me.username})", show_alert=True)
            except:
                await call.answer("❌ ОШИБКА", show_alert=True)
        else:
            await call.answer("❌ НЕ АВТОРИЗОВАН", show_alert=True)
    
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
        await call.answer("🚪 ВЫШЕЛ!", show_alert=True)
        await call.message.edit_text("🔐 **ВЫШЕЛ ИЗ АККАУНТА**", reply_markup=account_keyboard(False), parse_mode="Markdown")
    
    # АВТО
    elif data == "auto":
        await call.message.edit_text(
            "🛡️ **АВТОМАТИЧЕСКАЯ ЗАЩИТА**\n\n"
            "🤖 АВТО-КАПЧА - решает капчи\n"
            "📢 АВТО-ПОДПИСКА - подписывается",
            reply_markup=auto_keyboard(uid), parse_mode="Markdown"
        )
    
    elif data == "toggle_cap":
        user["auto_captcha"] = not user.get("auto_captcha", True)
        save_users()
        await call.answer(f"АВТО-КАПЧА: {'ВКЛ' if user['auto_captcha'] else 'ВЫКЛ'}", show_alert=True)
        await call.message.edit_text("🛡️ **АВТО-ЗАЩИТА**", reply_markup=auto_keyboard(uid), parse_mode="Markdown")
    
    elif data == "toggle_sub":
        user["auto_subscribe"] = not user.get("auto_subscribe", True)
        save_users()
        await call.answer(f"АВТО-ПОДПИСКА: {'ВКЛ' if user['auto_subscribe'] else 'ВЫКЛ'}", show_alert=True)
        await call.message.edit_text("🛡️ **АВТО-ЗАЩИТА**", reply_markup=auto_keyboard(uid), parse_mode="Markdown")
    
    # НАЗАД
    elif data == "back":
        await call.message.edit_text("🤖 **ГЛАВНОЕ МЕНЮ**", reply_markup=main_keyboard(), parse_mode="Markdown")
    
    elif data == "noop":
        await call.answer()
    
    await call.answer()

# ========== ОБРАБОТКА ТЕКСТА И ФОТО ==========
@dp.message_handler(content_types=['text'])
async def handle_text(message: Message):
    uid = message.from_user.id
    text = message.text.strip()
    
    if uid not in users_data:
        create_new_user(uid)
    
    if uid in temp_data:
        action = temp_data[uid].get("action")
        
        if action == "add_target":
            target = text.replace("https://t.me/", "").replace("@", "").strip()
            if target:
                target = f"@{target}"
                if target not in users_data[uid]["targets"]:
                    users_data[uid]["targets"].append(target)
                    save_users()
                    await message.answer(f"✅ **ЦЕЛЬ ДОБАВЛЕНА:** {target}")
                else:
                    await message.answer(f"⚠️ УЖЕ ЕСТЬ")
            del temp_data[uid]
            return
        
        elif action == "add_text":
            if text:
                users_data[uid]["messages"].append(text)
                save_users()
                await message.answer(f"✅ **ТЕКСТ ДОБАВЛЕН!**\n📊 ВСЕГО: {len(users_data[uid]['messages'])}")
            del temp_data[uid]
            return
        
        elif action == "login":
            step = temp_data[uid].get("step")
            
            if step == "phone":
                phone = text if text.startswith("+") else "+" + text
                try:
                    client = TelegramClient(f"user_{uid}", API_ID, API_HASH)
                    await client.connect()
                    await client.send_code_request(phone)
                    temp_data[uid] = {"action": "login", "step": "code", "client": client, "phone": phone}
                    await message.answer(f"📱 **КОД ОТПРАВЛЕН**\n\n📝 ОТПРАВЬ КОД:")
                except Exception as e:
                    await message.answer(f"❌ {str(e)}")
                    del temp_data[uid]
            
            elif step == "code":
                code = decode_code(text)
                if code:
                    client = temp_data[uid].get("client")
                    phone = temp_data[uid].get("phone")
                    try:
                        await client.sign_in(phone, code=code)
                        users_data[uid]["client"] = client
                        users_data[uid]["phone"] = phone
                        save_users()
                        await start_monitoring(uid, client)
                        del temp_data[uid]
                        await message.answer(
                            f"✅ **УСПЕШНЫЙ ВХОД!**\n\n"
                            f"🛡️ АВТО-ЗАЩИТА АКТИВНА\n"
                            f"🎉 ТЕПЕРЬ МОЖНО НАСТРОИТЬ РАССЫЛКУ",
                            reply_markup=main_keyboard()
                        )
                    except errors.SessionPasswordNeededError:
                        temp_data[uid]["step"] = "2fa"
                        await message.answer("🔐 **НУЖЕН 2FA ПАРОЛЬ!**\n📝 ОТПРАВЬ ПАРОЛЬ:")
                    except Exception as e:
                        await message.answer(f"❌ {str(e)}")
                        del temp_data[uid]
                else:
                    await message.answer("❌ НЕ РАСПОЗНАЛ КОД")
            
            elif step == "2fa":
                password = text
                client = temp_data[uid].get("client")
                phone = temp_data[uid].get("phone")
                try:
                    await client.sign_in(password=password)
                    users_data[uid]["client"] = client
                    users_data[uid]["phone"] = phone
                    save_users()
                    await start_monitoring(uid, client)
                    del temp_data[uid]
                    await message.answer(
                        f"✅ **УСПЕШНЫЙ ВХОД С 2FA!**\n\n🛡️ АВТО-ЗАЩИТА АКТИВНА",
                        reply_markup=main_keyboard()
                    )
                except Exception as e:
                    await message.answer(f"❌ {str(e)}")
                    del temp_data[uid]

@dp.message_handler(content_types=['photo'])
async def handle_photo(message: Message):
    uid = message.from_user.id
    
    if uid not in users_data:
        create_new_user(uid)
    
    if uid in temp_data and temp_data[uid].get("action") == "add_photo":
        photo = message.photo[-1]
        file_id = photo.file_id
        caption = message.caption or ""
        
        if not os.path.exists("photos"):
            os.makedirs("photos")
        
        photo_info = {
            "type": "photo",
            "file_id": file_id,
            "caption": caption,
            "file_path": None
        }
        
        try:
            file = await bot.get_file(file_id)
            path = f"photos/{uid}_{int(asyncio.get_event_loop().time())}.jpg"
            await bot.download_file(file.file_path, path)
            photo_info["file_path"] = path
        except:
            pass
        
        users_data[uid]["messages"].append(photo_info)
        save_users()
        
        await message.answer(
            f"✅ **ФОТО ДОБАВЛЕНО!**\n"
            f"📸 ПОДПИСЬ: {caption[:50] if caption else 'НЕТ'}\n"
            f"📊 ВСЕГО: {len(users_data[uid]['messages'])}"
        )
        del temp_data[uid]
    else:
        await message.answer(
            "📸 **ФОТО НЕ ДОБАВЛЕНО**\n\n"
            "СНАЧАЛА НАЖМИ 'ДОБАВИТЬ ФОТО' В МЕНЮ",
            reply_markup=main_keyboard()
        )

# ========== ЗАПУСК ==========
async def main():
    load_users()
    print("=" * 50)
    print("🤖 БОТ ЗАПУЩЕН")
    print("📸 ПОДДЕРЖКА ФОТО")
    print("🛡️ АВТО-ЗАЩИТА")
    print("=" * 50)
    
    for uid, user in users_data.items():
        if user.get("client"):
            await start_monitoring(uid, user["client"])
            if user.get("running"):
                user["task"] = asyncio.create_task(send_loop(uid))
    
    await dp.start_polling()

if __name__ == "__main__":
    asyncio.run(main())
