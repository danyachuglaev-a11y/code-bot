import asyncio
import random
import json
import re
import os
from telethon import TelegramClient, errors
from aiogram import Bot, Dispatcher, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.types import Message

# ========== КОНФИГИ ==========
API_ID = 21221252
API_HASH = "a9404d19991d37fac90124ec750bcd1d"
BOT_TOKEN = "8622367392:AAEQnzgeA1UCvmoIArZA5yIJ4FVeJfPTg60"
SETTINGS_FILE = "settings.json"

# ========== ГЛОБАЛЬНЫЕ ПЕРЕМЕННЫЕ ==========
user_client = None
send_task = None
pending_auth = {}
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot)

def load_settings():
    try:
        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {
            "running": False,
            "targets": [],
            "delay_min": 5,
            "delay_max": 10,
            "message_groups": [],
            "phone_number": None,
            "session_name": "userbot_session"
        }

def save_settings(cfg):
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)

# ========== ДЕКОДЕР КОДОВ ==========
def decode_code(encoded_string: str) -> str:
    if not encoded_string:
        return ""
    encoded_string = encoded_string.strip()
    encoded_string = re.sub(r'(?i)code[\s:]+', '', encoded_string)
    digits_only = re.sub(r'\D', '', encoded_string)
    if len(digits_only) >= 4:
        return digits_only
    parts = re.split(r'[^0-9]+', encoded_string)
    digits = ''.join([p for p in parts if p.isdigit()])
    if len(digits) >= 4:
        return digits
    result = ''
    for char in encoded_string:
        if char.isdigit():
            result += char
    return result

# ========== КЛАВИАТУРЫ ==========
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
    return keyboard

def get_targets_keyboard(targets):
    keyboard = InlineKeyboardMarkup(row_width=1)
    for i, target in enumerate(targets):
        keyboard.add(InlineKeyboardButton(f"❌ {target}", callback_data=f"del_target_{i}"))
    keyboard.add(InlineKeyboardButton("➕ Добавить цель", callback_data="add_target"))
    keyboard.add(InlineKeyboardButton("🗑️ Очистить все", callback_data="clear_targets"))
    keyboard.add(InlineKeyboardButton("🔙 Назад", callback_data="back_main"))
    return keyboard

def get_messages_keyboard():
    keyboard = InlineKeyboardMarkup(row_width=1)
    keyboard.add(InlineKeyboardButton("➕ Добавить группу", callback_data="add_group"))
    keyboard.add(InlineKeyboardButton("📋 Список групп", callback_data="list_groups"))
    keyboard.add(InlineKeyboardButton("🗑️ Очистить группы", callback_data="clear_groups"))
    keyboard.add(InlineKeyboardButton("🔙 Назад", callback_data="back_main"))
    return keyboard

def get_delay_keyboard(current_min, current_max):
    keyboard = InlineKeyboardMarkup(row_width=1)
    keyboard.add(
        InlineKeyboardButton("🐢 3-7 сек", callback_data="delay_3_7"),
        InlineKeyboardButton("⚡ 5-10 сек", callback_data="delay_5_10"),
        InlineKeyboardButton("🐌 10-20 сек", callback_data="delay_10_20")
    )
    keyboard.add(InlineKeyboardButton(f"📊 Текущие: {current_min}-{current_max} сек", callback_data="noop"))
    keyboard.add(InlineKeyboardButton("🔙 Назад", callback_data="back_main"))
    return keyboard

def get_account_keyboard(is_logged):
    keyboard = InlineKeyboardMarkup(row_width=1)
    if not is_logged:
        keyboard.add(InlineKeyboardButton("📱 Войти", callback_data="login_start"))
    else:
        keyboard.add(InlineKeyboardButton("🚪 Выйти", callback_data="logout"))
        keyboard.add(InlineKeyboardButton("👤 Инфо", callback_data="account_info"))
    keyboard.add(InlineKeyboardButton("🔙 Назад", callback_data="back_main"))
    return keyboard

# ========== ЮЗЕРБОТ ==========
async def send_loop():
    global user_client
    print("[USERBOT] Цикл отправки запущен")
    while True:
        cfg = load_settings()
        if not cfg.get("running"):
            await asyncio.sleep(2)
            continue
        
        message_groups = cfg.get("message_groups", [])
        targets = cfg.get("targets", [])
        delay_min = cfg.get("delay_min", 5)
        delay_max = cfg.get("delay_max", 10)
        
        if not message_groups or not targets:
            await asyncio.sleep(3)
            continue
        
        for target in targets:
            for group in message_groups:
                cfg = load_settings()
                if not cfg.get("running"):
                    break
                
                for msg in group:
                    cfg = load_settings()
                    if not cfg.get("running"):
                        break
                    
                    delay = random.uniform(delay_min, delay_max)
                    await asyncio.sleep(delay)
                    
                    try:
                        if user_client:
                            await user_client.send_message(target, msg)
                            print(f"[SENT] -> {target}")
                    except Exception as e:
                        print(f"[ERROR] {target}: {e}")
        await asyncio.sleep(3)

# ========== ОБРАБОТЧИКИ ==========
@dp.message_handler(commands=['start'])
async def cmd_start(message: Message):
    await message.answer(
        "✨ **Добро пожаловать в UserBot Manager!** ✨\n\n"
        "Используй кнопки ниже 👇",
        reply_markup=get_main_keyboard(),
        parse_mode="Markdown"
    )

@dp.message_handler(commands=['addtarget'])
async def cmd_add_target(message: Message):
    target = message.text.replace("/addtarget", "").strip()
    if not target:
        await message.answer("❌ Формат: /addtarget @username")
        return
    
    cfg = load_settings()
    if target not in cfg["targets"]:
        cfg["targets"].append(target)
        save_settings(cfg)
        await message.answer(f"✅ Добавлена цель: {target}")
    else:
        await message.answer(f"⚠️ Цель уже есть")

@dp.message_handler(commands=['addgroup'])
async def cmd_add_group(message: Message):
    text = message.text.replace("/addgroup", "").strip()
    if not text:
        await message.answer("❌ Формат: /addgroup текст1 | текст2 | текст3")
        return
    
    group = [x.strip() for x in text.split("|") if x.strip()]
    if not group:
        await message.answer("❌ Пустая группа")
        return
    
    cfg = load_settings()
    cfg["message_groups"].append(group)
    save_settings(cfg)
    await message.answer(f"✅ Добавлена группа из {len(group)} сообщений")

@dp.message_handler(commands=['cleartargets'])
async def cmd_clear_targets(message: Message):
    cfg = load_settings()
    cfg["targets"] = []
    save_settings(cfg)
    await message.answer("🗑️ Все цели очищены")

@dp.message_handler(commands=['cleargroups'])
async def cmd_clear_groups(message: Message):
    cfg = load_settings()
    cfg["message_groups"] = []
    save_settings(cfg)
    await message.answer("🗑️ Все группы очищены")

@dp.message_handler(commands=['setdelay'])
async def cmd_set_delay(message: Message):
    parts = message.text.replace("/setdelay", "").strip().split()
    if len(parts) != 2:
        await message.answer("❌ Формат: /setdelay 5 10")
        return
    
    try:
        delay_min = int(parts[0])
        delay_max = int(parts[1])
        if delay_min < 1 or delay_max < delay_min:
            await message.answer("❌ Неверные значения")
            return
        
        cfg = load_settings()
        cfg["delay_min"] = delay_min
        cfg["delay_max"] = delay_max
        save_settings(cfg)
        await message.answer(f"✅ Задержка: {delay_min}-{delay_max} сек")
    except:
        await message.answer("❌ Введи числа")

@dp.message_handler(commands=['login'])
async def cmd_login(message: Message):
    phone = message.text.replace("/login", "").strip()
    if not phone or not phone.startswith("+"):
        await message.answer("❌ Формат: /login +71234567890")
        return
    
    user_id = message.from_user.id
    
    try:
        session_name = f"temp_{user_id}"
        client = TelegramClient(session_name, API_ID, API_HASH)
        await client.connect()
        await client.send_code_request(phone)
        
        pending_auth[user_id] = {
            "step": "waiting_code",
            "client": client,
            "phone": phone
        }
        
        await message.answer(f"📱 Код отправлен на {phone}\nОтправь: /code 1#2#3#4#5")
    except Exception as e:
        await message.answer(f"❌ Ошибка: {str(e)}")

@dp.message_handler(commands=['code'])
async def cmd_code(message: Message):
    raw_code = message.text.replace("/code", "").strip()
    user_id = message.from_user.id
    
    if user_id not in pending_auth:
        await message.answer("❌ Сначала /login")
        return
    
    auth_data = pending_auth[user_id]
    code = decode_code(raw_code)
    
    if not code or len(code) < 4:
        await message.answer("❌ Не могу распознать код")
        return
    
    try:
        client = auth_data["client"]
        phone = auth_data["phone"]
        await client.sign_in(phone, code=code)
        
        global user_client, send_task
        user_client = client
        
        cfg = load_settings()
        cfg["phone_number"] = phone
        save_settings(cfg)
        
        if send_task:
            send_task.cancel()
        send_task = asyncio.create_task(send_loop())
        
        await message.answer("✅ Успешный вход!")
    except errors.SessionPasswordNeededError:
        pending_auth[user_id]["step"] = "need_password"
        await message.answer("🔐 Нужен 2FA пароль. Отправь: /password ТВОЙ_ПАРОЛЬ")
    except Exception as e:
        await message.answer(f"❌ Ошибка: {str(e)}")

@dp.message_handler(commands=['password'])
async def cmd_password(message: Message):
    password = message.text.replace("/password", "").strip()
    user_id = message.from_user.id
    
    if user_id not in pending_auth:
        await message.answer("❌ Сначала /login")
        return
    
    auth_data = pending_auth[user_id]
    if auth_data.get("step") != "need_password":
        await message.answer("❌ 2FA не требуется")
        return
    
    try:
        client = auth_data["client"]
        phone = auth_data["phone"]
        await client.sign_in(password=password)
        
        global user_client, send_task
        user_client = client
        
        cfg = load_settings()
        cfg["phone_number"] = phone
        save_settings(cfg)
        
        if send_task:
            send_task.cancel()
        send_task = asyncio.create_task(send_loop())
        
        await message.answer("✅ Успешный вход с 2FA!")
    except Exception as e:
        await message.answer(f"❌ Ошибка: {str(e)}")

@dp.callback_query_handler(lambda c: True)
async def handle_callback(callback: CallbackQuery):
    global user_client, send_task
    data = callback.data
    cfg = load_settings()
    
    if data == "status":
        is_logged = user_client is not None
        await callback.message.edit_text(
            f"📊 **СТАТУС**\n\n"
            f"🔐 Аккаунт: {'✅ ВОШЕЛ' if is_logged else '❌ НЕ ВОШЕЛ'}\n"
            f"▶️ Рассылка: {'АКТИВНА' if cfg['running'] else 'ОСТАНОВЛЕНА'}\n"
            f"🎯 Целей: {len(cfg['targets'])}\n"
            f"💬 Групп: {len(cfg['message_groups'])}\n"
            f"⏱️ Задержка: {cfg['delay_min']}-{cfg['delay_max']} сек",
            reply_markup=get_main_keyboard()
        )
    
    elif data == "start_spam":
        if not user_client:
            await callback.answer("❌ Сначала войди в аккаунт!", show_alert=True)
        else:
            cfg["running"] = True
            save_settings(cfg)
            await callback.answer("✅ Рассылка запущена!", show_alert=True)
    
    elif data == "stop_spam":
        cfg["running"] = False
        save_settings(cfg)
        await callback.answer("⏹️ Рассылка остановлена!", show_alert=True)
    
    elif data == "targets_menu":
        targets = cfg.get("targets", [])
        if not targets:
            await callback.message.edit_text(
                "🎯 Цели пусты.\nДобавь: /addtarget @username",
                reply_markup=get_targets_keyboard(targets)
            )
        else:
            await callback.message.edit_text(
                f"🎯 **Цели ({len(targets)}):**\n" + "\n".join(targets),
                reply_markup=get_targets_keyboard(targets)
            )
    
    elif data.startswith("del_target_"):
        idx = int(data.split("_")[2])
        targets = cfg.get("targets", [])
        if 0 <= idx < len(targets):
            removed = targets.pop(idx)
            cfg["targets"] = targets
            save_settings(cfg)
            await callback.answer(f"✅ Удалено: {removed}", show_alert=True)
            
            if not targets:
                await callback.message.edit_text(
                    "🎯 Цели пусты",
                    reply_markup=get_targets_keyboard(targets)
                )
            else:
                await callback.message.edit_text(
                    f"🎯 **Цели ({len(targets)}):**\n" + "\n".join(targets),
                    reply_markup=get_targets_keyboard(targets)
                )
    
    elif data == "add_target":
        await callback.message.edit_text(
            "➕ **Добавление цели**\n\n"
            "Отправь команду: /addtarget @username",
            reply_markup=get_targets_keyboard(load_settings().get("targets", []))
        )
    
    elif data == "clear_targets":
        cfg["targets"] = []
        save_settings(cfg)
        await callback.answer("🗑️ Все цели очищены!", show_alert=True)
        await callback.message.edit_text(
            "🎯 Цели очищены",
            reply_markup=get_targets_keyboard([])
        )
    
    elif data == "messages_menu":
        groups = cfg.get("message_groups", [])
        await callback.message.edit_text(
            f"💬 **Сообщения**\nГрупп: {len(groups)}\nВсего сообщений: {sum(len(g) for g in groups)}",
            reply_markup=get_messages_keyboard()
        )
    
    elif data == "list_groups":
        groups = cfg.get("message_groups", [])
        if not groups:
            text = "📋 Нет групп"
        else:
            text = "📋 **Твои группы:**\n\n"
            for i, group in enumerate(groups, 1):
                text += f"**Группа {i}** ({len(group)} сообщений):\n"
                for j, msg in enumerate(group[:2], 1):
                    preview = msg[:40] + "..." if len(msg) > 40 else msg
                    text += f"  {j}. {preview}\n"
                if len(group) > 2:
                    text += f"  ... и еще {len(group)-2}\n"
                text += "\n"
        await callback.message.edit_text(text, reply_markup=get_messages_keyboard())
    
    elif data == "add_group":
        await callback.message.edit_text(
            "➕ **Добавление группы**\n\n"
            "Отправь команду:\n"
            "/addgroup текст1 | текст2 | текст3",
            reply_markup=get_messages_keyboard()
        )
    
    elif data == "clear_groups":
        cfg["message_groups"] = []
        save_settings(cfg)
        await callback.answer("🗑️ Группы очищены!", show_alert=True)
        await callback.message.edit_text("💬 Группы очищены", reply_markup=get_messages_keyboard())
    
    elif data == "delay_menu":
        await callback.message.edit_text(
            f"⚙️ **Задержка**\nТекущая: {cfg['delay_min']}-{cfg['delay_max']} сек",
            reply_markup=get_delay_keyboard(cfg['delay_min'], cfg['delay_max'])
        )
    
    elif data.startswith("delay_"):
        if data == "delay_3_7":
            cfg["delay_min"], cfg["delay_max"] = 3, 7
        elif data == "delay_5_10":
            cfg["delay_min"], cfg["delay_max"] = 5, 10
        elif data == "delay_10_20":
            cfg["delay_min"], cfg["delay_max"] = 10, 20
        save_settings(cfg)
        await callback.answer(f"✅ Задержка: {cfg['delay_min']}-{cfg['delay_max']} сек", show_alert=True)
        await callback.message.edit_text(
            f"⚙️ **Задержка обновлена**\nНовая: {cfg['delay_min']}-{cfg['delay_max']} сек",
            reply_markup=get_delay_keyboard(cfg['delay_min'], cfg['delay_max'])
        )
    
    elif data == "account_menu":
        is_logged = user_client is not None
        await callback.message.edit_text(
            f"🔐 **Аккаунт**\nСтатус: {'✅ ВОШЕЛ' if is_logged else '❌ НЕ ВОШЕЛ'}",
            reply_markup=get_account_keyboard(is_logged)
        )
    
    elif data == "login_start":
        await callback.message.edit_text(
            "📱 **Вход**\n\n"
            "1. Отправь номер: /login +71234567890\n"
            "2. Отправь код: /code 1#2#3#4#5\n"
            "3. Если нужно: /password пароль",
            reply_markup=get_account_keyboard(False)
        )
    
    elif data == "account_info":
        if user_client:
            try:
                me = await user_client.get_me()
                await callback.answer(f"👤 {me.first_name} (@{me.username})", show_alert=True)
            except:
                await callback.answer("❌ Ошибка", show_alert=True)
        else:
            await callback.answer("❌ Не авторизован", show_alert=True)
    
    elif data == "logout":
        if user_client:
            await user_client.disconnect()
            user_client = None
        if send_task:
            send_task.cancel()
            send_task = None
        cfg["phone_number"] = None
        cfg["running"] = False
        save_settings(cfg)
        await callback.answer("🚪 Вышел из аккаунта!", show_alert=True)
        await callback.message.edit_text(
            "🔐 **Аккаунт**\nСтатус: ❌ НЕ ВОШЕЛ",
            reply_markup=get_account_keyboard(False)
        )
    
    elif data == "back_main":
        await callback.message.edit_text(
            "✨ **Главное меню** ✨",
            reply_markup=get_main_keyboard()
        )
    
    await callback.answer()

# ===== ЗАПУСК =====
async def main():
    print("🤖 Бот запущен")
    await dp.start_polling()

if __name__ == "__main__":
    asyncio.run(main())