import asyncio
import random
import json
import re
import os
from telethon import TelegramClient, errors, events
from telethon.tl.functions.channels import JoinChannelRequest
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

def load_users():
    global users_data
    try:
        with open(USERS_FILE, "r", encoding="utf-8") as f:
            saved = json.load(f)
            for user_id, data in saved.items():
                users_data[int(user_id)] = {**data, "client": None, "task": None, "monitor_task": None}
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
        "phone": None, "client": None, "running": False, "targets": [], "messages": [],
        "delay_min": 5, "delay_max": 10, "task": None, "monitor_task": None,
        "auto_captcha": True, "auto_subscribe": True
    }
    save_users()

def decode_code(encoded_string: str) -> str:
    return re.sub(r'\D', '', encoded_string) if encoded_string else ""

# ========== КНОПКИ (БЕЗ Markdown) ==========
def main_kb():
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton("📊 СТАТУС", callback_data="status"),
        InlineKeyboardButton("▶️ СТАРТ", callback_data="start"),
        InlineKeyboardButton("⏹️ СТОП", callback_data="stop"),
        InlineKeyboardButton("🎯 ЦЕЛИ", callback_data="targets"),
        InlineKeyboardButton("💬 СООБЩЕНИЯ", callback_data="messages"),
        InlineKeyboardButton("⚙️ ЗАДЕРЖКА", callback_data="delay"),
        InlineKeyboardButton("🔐 АККАУНТ", callback_data="account"),
        InlineKeyboardButton("🛡️ АВТО", callback_data="auto")
    )
    return kb

def targets_kb(uid):
    targets = users_data.get(uid, {}).get("targets", [])
    kb = InlineKeyboardMarkup(row_width=1)
    for i, t in enumerate(targets):
        kb.add(InlineKeyboardButton(f"❌ {t}", callback_data=f"del_target_{i}"))
    kb.add(InlineKeyboardButton("➕ ДОБАВИТЬ", callback_data="add_target"))
    kb.add(InlineKeyboardButton("🗑️ ОЧИСТИТЬ", callback_data="clear_targets"))
    kb.add(InlineKeyboardButton("🔙 НАЗАД", callback_data="back"))
    return kb

def messages_kb(uid):
    msgs = users_data.get(uid, {}).get("messages", [])
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

def delay_kb(current_min, current_max):
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton("3-7 СЕК", callback_data="delay_3_7"),
        InlineKeyboardButton("5-10 СЕК", callback_data="delay_5_10"),
        InlineKeyboardButton("10-20 СЕК", callback_data="delay_10_20"),
        InlineKeyboardButton("15-30 СЕК", callback_data="delay_15_30"),
        InlineKeyboardButton(f"📊 {current_min}-{current_max} СЕК", callback_data="noop"),
        InlineKeyboardButton("🔙 НАЗАД", callback_data="back")
    )
    return kb

def account_kb(is_logged):
    kb = InlineKeyboardMarkup(row_width=1)
    if not is_logged:
        kb.add(InlineKeyboardButton("📱 ВОЙТИ", callback_data="login"))
    else:
        kb.add(InlineKeyboardButton("👤 ИНФО", callback_data="info"))
        kb.add(InlineKeyboardButton("🚪 ВЫЙТИ", callback_data="logout"))
    kb.add(InlineKeyboardButton("🔙 НАЗАД", callback_data="back"))
    return kb

def auto_kb(uid):
    user = users_data.get(uid, {})
    cap = "✅ ВКЛ" if user.get("auto_captcha", True) else "❌ ВЫКЛ"
    sub = "✅ ВКЛ" if user.get("auto_subscribe", True) else "❌ ВЫКЛ"
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(InlineKeyboardButton(f"🤖 КАПЧА: {cap}", callback_data="toggle_cap"))
    kb.add(InlineKeyboardButton(f"📢 ПОДПИСКА: {sub}", callback_data="toggle_sub"))
    kb.add(InlineKeyboardButton("🔙 НАЗАД", callback_data="back"))
    return kb

def back_kb(back_to):
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(InlineKeyboardButton("❌ ОТМЕНА", callback_data=back_to))
    return kb

# ========== ОТПРАВКА ==========
async def send_loop(uid):
    while True:
        try:
            if uid not in users_data:
                break
            user = users_data[uid]
            if not user.get("running"):
                await asyncio.sleep(2)
                continue
            messages = user.get("messages", [])
            targets = user.get("targets", [])
            if not messages or not targets:
                await asyncio.sleep(3)
                continue
            client = user.get("client")
            if not client:
                await asyncio.sleep(5)
                continue
            for target in targets:
                for msg in messages:
                    if not users_data[uid].get("running"):
                        break
                    await asyncio.sleep(random.uniform(user.get("delay_min", 5), user.get("delay_max", 10)))
                    try:
                        if isinstance(msg, dict) and msg.get("type") == "photo":
                            if msg.get("file_path") and os.path.exists(msg["file_path"]):
                                await client.send_file(target, msg["file_path"], caption=msg.get("caption", ""))
                            else:
                                await client.send_file(target, msg["file_id"], caption=msg.get("caption", ""))
                        else:
                            await client.send_message(target, str(msg))
                        print(f"[SENT] {uid} -> {target}")
                    except errors.SessionRevokedError:
                        users_data[uid]["client"] = None
                        users_data[uid]["running"] = False
                        try:
                            await bot.send_message(uid, "❌ Сессия истекла! Войди заново")
                        except:
                            pass
                        break
                    except Exception as e:
                        print(f"[ERROR] {e}")
            await asyncio.sleep(3)
        except:
            await asyncio.sleep(1)

# ========== ОБРАБОТЧИКИ ==========
@dp.message_handler(commands=['start'])
async def start_cmd(message: Message):
    uid = message.from_user.id
    if uid not in users_data:
        create_new_user(uid)
    await message.answer("🤖 БОТ ГОТОВ\n\n👇 ВЫБЕРИ ДЕЙСТВИЕ", reply_markup=main_kb())

@dp.callback_query_handler(lambda c: True)
async def handle_callback(call: CallbackQuery):
    uid = call.from_user.id
    data = call.data
    
    if uid not in users_data:
        create_new_user(uid)
    
    user = users_data[uid]
    is_logged = user.get("client") is not None
    
    if data == "status":
        await call.message.edit_text(
            f"📊 СТАТУС\n\n"
            f"АККАУНТ: {'✅ ВОШЕЛ' if is_logged else '❌ НЕ ВОШЕЛ'}\n"
            f"НОМЕР: {user.get('phone', 'НЕТ')}\n"
            f"РАССЫЛКА: {'🟢 РАБОТАЕТ' if user.get('running') else '🔴 СТОП'}\n"
            f"ЦЕЛЕЙ: {len(user.get('targets', []))}\n"
            f"СООБЩЕНИЙ: {len(user.get('messages', []))}\n"
            f"ЗАДЕРЖКА: {user.get('delay_min', 5)}-{user.get('delay_max', 10)} СЕК\n"
            f"АВТО-ЗАЩИТА: {'ВКЛ' if user.get('auto_captcha', True) else 'ВЫКЛ'}",
            reply_markup=main_kb()
        )
        await call.answer()
    
    elif data == "start":
        if not is_logged:
            await call.answer("❌ ВОЙДИ В АККАУНТ!", show_alert=True)
        else:
            user["running"] = True
            save_users()
            if user.get("client") and not user.get("task"):
                user["task"] = asyncio.create_task(send_loop(uid))
            await call.answer("✅ ЗАПУЩЕНО!", show_alert=True)
            await call.message.edit_text("✅ РАССЫЛКА ЗАПУЩЕНА", reply_markup=main_kb())
    
    elif data == "stop":
        user["running"] = False
        save_users()
        await call.answer("⏹️ ОСТАНОВЛЕНО!", show_alert=True)
        await call.message.edit_text("⏹️ РАССЫЛКА ОСТАНОВЛЕНА", reply_markup=main_kb())
    
    elif data == "targets":
        targets = user.get("targets", [])
        text = "🎯 ЦЕЛИ:\n\n" + "\n".join([f"• {t}" for t in targets]) if targets else "🎯 ЦЕЛИ ПУСТЫ"
        await call.message.edit_text(text, reply_markup=targets_kb(uid))
    
    elif data == "add_target":
        temp_data[uid] = {"action": "add_target"}
        await call.message.edit_text(
            "➕ ДОБАВЛЕНИЕ ЦЕЛИ\n\n"
            "📝 ОТПРАВЬ USERNAME:\n\n"
            "Пример: @durov или https://t.me/durov",
            reply_markup=back_kb("targets")
        )
    
    elif data.startswith("del_target_"):
        idx = int(data.split("_")[2])
        targets = user.get("targets", [])
        if idx < len(targets):
            targets.pop(idx)
            user["targets"] = targets
            save_users()
            await call.answer("✅ УДАЛЕНО!", show_alert=True)
            text = "🎯 ЦЕЛИ:\n\n" + "\n".join([f"• {t}" for t in targets]) if targets else "🎯 ЦЕЛИ ПУСТЫ"
            await call.message.edit_text(text, reply_markup=targets_kb(uid))
    
    elif data == "clear_targets":
        user["targets"] = []
        save_users()
        await call.answer("🗑️ ОЧИЩЕНО!", show_alert=True)
        await call.message.edit_text("🎯 ВСЕ ЦЕЛИ ОЧИЩЕНЫ", reply_markup=targets_kb(uid))
    
    elif data == "messages":
        msgs = user.get("messages", [])
        if not msgs:
            await call.message.edit_text("💬 СООБЩЕНИЙ НЕТ", reply_markup=messages_kb(uid))
        else:
            text = "💬 СООБЩЕНИЯ:\n\n"
            for i, m in enumerate(msgs, 1):
                text += f"{i}. 📸 ФОТО\n" if isinstance(m, dict) else f"{i}. {m[:40]}\n"
            await call.message.edit_text(text, reply_markup=messages_kb(uid))
    
    elif data == "add_text":
        temp_data[uid] = {"action": "add_text"}
        await call.message.edit_text("📝 ДОБАВЛЕНИЕ ТЕКСТА\n\n📤 ОТПРАВЬ ТЕКСТ:", reply_markup=back_kb("messages"))
    
    elif data == "add_photo":
        temp_data[uid] = {"action": "add_photo", "waiting": True}
        await call.message.edit_text("📸 ДОБАВЛЕНИЕ ФОТО\n\n📤 ОТПРАВЬ ФОТО (можно с подписью)", reply_markup=back_kb("messages"))
    
    elif data.startswith("del_msg_"):
        idx = int(data.split("_")[2])
        msgs = user.get("messages", [])
        if idx < len(msgs):
            msgs.pop(idx)
            user["messages"] = msgs
            save_users()
            await call.answer("✅ УДАЛЕНО!", show_alert=True)
            await call.message.edit_text("💬 ОБНОВЛЕНО", reply_markup=messages_kb(uid))
    
    elif data == "clear_messages":
        user["messages"] = []
        save_users()
        await call.answer("🗑️ ОЧИЩЕНО!", show_alert=True)
        await call.message.edit_text("💬 ВСЕ СООБЩЕНИЯ ОЧИЩЕНЫ", reply_markup=messages_kb(uid))
    
    elif data == "delay":
        await call.message.edit_text(f"⚙️ ЗАДЕРЖКА: {user.get('delay_min', 5)}-{user.get('delay_max', 10)} СЕК", reply_markup=delay_kb(user.get('delay_min', 5), user.get('delay_max', 10)))
    
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
        await call.message.edit_text(f"⚙️ ЗАДЕРЖКА: {user['delay_min']}-{user['delay_max']} СЕК", reply_markup=delay_kb(user['delay_min'], user['delay_max']))
    
    elif data == "account":
        await call.message.edit_text(f"🔐 АККАУНТ\n\nСТАТУС: {'✅ ВОШЕЛ' if is_logged else '❌ НЕ ВОШЕЛ'}\nНОМЕР: {user.get('phone', 'НЕТ')}", reply_markup=account_kb(is_logged))
    
    elif data == "login":
        temp_data[uid] = {"action": "login", "step": "phone"}
        await call.message.edit_text("📱 ВХОД\n\n📝 ОТПРАВЬ НОМЕР: +71234567890", reply_markup=back_kb("account"))
    
    elif data == "info":
        if is_logged and user.get("client"):
            try:
                me = await user["client"].get_me()
                await call.answer(f"👤 {me.first_name}", show_alert=True)
            except:
                await call.answer("❌ ОШИБКА", show_alert=True)
        else:
            await call.answer("❌ НЕ АВТОРИЗОВАН", show_alert=True)
    
    elif data == "logout":
        if user.get("client"):
            try:
                await user["client"].disconnect()
            except:
                pass
        if user.get("task"):
            try:
                user["task"].cancel()
            except:
                pass
        if user.get("monitor_task"):
            try:
                user["monitor_task"].cancel()
            except:
                pass
        user["client"] = None
        user["task"] = None
        user["monitor_task"] = None
        user["running"] = False
        user["phone"] = None
        save_users()
        await call.answer("🚪 ВЫШЕЛ!", show_alert=True)
        await call.message.edit_text("🔐 ВЫШЕЛ ИЗ АККАУНТА", reply_markup=account_kb(False))
    
    elif data == "auto":
        await call.message.edit_text("🛡️ АВТОМАТИЧЕСКАЯ ЗАЩИТА", reply_markup=auto_kb(uid))
    
    elif data == "toggle_cap":
        user["auto_captcha"] = not user.get("auto_captcha", True)
        save_users()
        await call.answer(f"АВТО-КАПЧА: {'ВКЛ' if user['auto_captcha'] else 'ВЫКЛ'}", show_alert=True)
        await call.message.edit_text("🛡️ АВТО-ЗАЩИТА", reply_markup=auto_kb(uid))
    
    elif data == "toggle_sub":
        user["auto_subscribe"] = not user.get("auto_subscribe", True)
        save_users()
        await call.answer(f"АВТО-ПОДПИСКА: {'ВКЛ' if user['auto_subscribe'] else 'ВЫКЛ'}", show_alert=True)
        await call.message.edit_text("🛡️ АВТО-ЗАЩИТА", reply_markup=auto_kb(uid))
    
    elif data == "back":
        await call.message.edit_text("🤖 ГЛАВНОЕ МЕНЮ", reply_markup=main_kb())
    
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
                    await message.answer(f"✅ ЦЕЛЬ ДОБАВЛЕНА: {target}\n\n📊 ВСЕГО ЦЕЛЕЙ: {len(users_data[uid]['targets'])}")
                else:
                    await message.answer(f"⚠️ УЖЕ ЕСТЬ")
            del temp_data[uid]
            return
        
        elif action == "add_text":
            if text:
                users_data[uid]["messages"].append(text)
                save_users()
                await message.answer(f"✅ ТЕКСТ ДОБАВЛЕН!\n\n📊 ВСЕГО: {len(users_data[uid]['messages'])}")
            del temp_data[uid]
            return
        
        elif action == "login":
            step = temp_data[uid].get("step")
            
            if step == "phone":
                phone = text if text.startswith("+") else "+" + text
                try:
                    session_name = f"user_{uid}"
                    for f in os.listdir("."):
                        if f.startswith(session_name) and f.endswith(".session"):
                            try:
                                os.remove(f)
                            except:
                                pass
                    client = TelegramClient(session_name, API_ID, API_HASH)
                    await client.connect()
                    await client.send_code_request(phone)
                    temp_data[uid] = {"action": "login", "step": "code", "client": client, "phone": phone}
                    await message.answer(f"📱 КОД ОТПРАВЛЕН\n\n📝 ОТПРАВЬ КОД:")
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
                        del temp_data[uid]
                        await message.answer(f"✅ УСПЕШНЫЙ ВХОД!\n\n🛡️ АВТО-ЗАЩИТА АКТИВНА", reply_markup=main_kb())
                    except errors.SessionPasswordNeededError:
                        temp_data[uid]["step"] = "2fa"
                        await message.answer("🔐 НУЖЕН 2FA ПАРОЛЬ!\n\n📝 ОТПРАВЬ ПАРОЛЬ:")
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
                    del temp_data[uid]
                    await message.answer(f"✅ УСПЕШНЫЙ ВХОД С 2FA!\n\n🛡️ АВТО-ЗАЩИТА АКТИВНА", reply_markup=main_kb())
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
        
        photo_info = {"type": "photo", "file_id": file_id, "caption": caption, "file_path": None}
        
        try:
            file = await bot.get_file(file_id)
            path = f"photos/{uid}_{int(asyncio.get_event_loop().time())}.jpg"
            await bot.download_file(file.file_path, path)
            photo_info["file_path"] = path
        except:
            pass
        
        users_data[uid]["messages"].append(photo_info)
        save_users()
        await message.answer(f"✅ ФОТО ДОБАВЛЕНО!\n📸 ПОДПИСЬ: {caption[:50] if caption else 'НЕТ'}\n📊 ВСЕГО: {len(users_data[uid]['messages'])}")
        del temp_data[uid]
    else:
        await message.answer("📸 ФОТО НЕ ДОБАВЛЕНО\n\nСНАЧАЛА НАЖМИ 'ДОБАВИТЬ ФОТО' В МЕНЮ", reply_markup=main_kb())

# ========== ЗАПУСК ==========
async def main():
    load_users()
    print("=" * 50)
    print("🤖 БОТ ЗАПУЩЕН")
    print("=" * 50)
    
    for uid, user in users_data.items():
        if user.get("client") and user.get("running"):
            user["task"] = asyncio.create_task(send_loop(uid))
    
    await dp.start_polling()

if __name__ == "__main__":
    asyncio.run(main())
