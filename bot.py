import os
import math
import struct
import zipfile
import tempfile
import shutil
from datetime import datetime
from aiogram import Bot, Dispatcher, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, InputFile
from aiogram.utils import executor
from dotenv import load_dotenv
import numpy as np

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHANNEL_ID = os.getenv("CHANNEL_ID", "@brmodels095")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot)

# Хранилища
user_consent = {}
user_ownership = {}

# Логи
CONSENT_LOG = "consent_log.txt"
OWNERSHIP_LOG = "ownership_log.txt"

def log_consent(user_id: int, username: str, action: str):
    with open(CONSENT_LOG, "a", encoding="utf-8") as f:
        f.write(f"{datetime.now().isoformat()} | User {user_id} (@{username}) | {action}\n")

def log_ownership(user_id: int, username: str, confirmed: bool):
    status = "CONFIRMED" if confirmed else "DECLINED"
    with open(OWNERSHIP_LOG, "a", encoding="utf-8") as f:
        f.write(f"{datetime.now().isoformat()} | User {user_id} (@{username}) | OWNERSHIP {status}\n")

# ==================== ПРОВЕРКА ПОДПИСКИ ====================

async def is_subscribed(user_id: int) -> bool:
    try:
        chat_member = await bot.get_chat_member(chat_id=CHANNEL_ID, user_id=user_id)
        return chat_member.status in ["member", "administrator", "creator", "restricted"]
    except Exception:
        return False

async def ensure_subscribed(message: types.Message) -> bool:
    user_id = message.from_user.id
    subscribed = await is_subscribed(user_id)
    
    if not subscribed:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📢 ПОДПИСАТЬСЯ", url="https://t.me/brmodels095")],
            [InlineKeyboardButton(text="✅ ПРОВЕРИТЬ", callback_data="check_subscribe")]
        ])
        await message.answer(
            "🔒 *ДОСТУП ПО ПОДПИСКЕ*\n\n"
            "Подпишитесь на канал:\n➡️ [@brmodels095](https://t.me/brmodels095)\n\n"
            "После подписки нажмите «ПРОВЕРИТЬ»",
            reply_markup=keyboard,
            parse_mode="Markdown"
        )
        return False
    return True

@dp.callback_query_handler(lambda c: c.data == "check_subscribe")
async def check_subscribe_callback(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    subscribed = await is_subscribed(user_id)
    
    if subscribed:
        await callback.message.delete()
        await cmd_start(callback.message)
    else:
        await callback.answer("❌ Вы не подписаны на канал", show_alert=True)
    await callback.answer()

# ==================== СОГЛАСИЕ ====================

@dp.message_handler(commands=["start"])
async def cmd_start(message: types.Message):
    user_id = message.from_user.id
    
    if not await ensure_subscribed(message):
        return
    
    if has_full_consent(user_id):
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ ОТОЗВАТЬ ВСЕ СОГЛАСИЯ", callback_data="revoke_all")]
        ])
        await message.answer(
            "✅ *У ВАС УЖЕ ЕСТЬ АКТИВНЫЕ СОГЛАСИЯ*\n\n"
            "📦 ОТПРАВЬТЕ .kn5 ФАЙЛ ДЛЯ КОНВЕРТАЦИИ В .obj\n\n"
            "⚠️ *ВЫ МОЖЕТЕ ОТОЗВАТЬ СОГЛАСИЕ В ЛЮБОЙ МОМЕНТ:* /revoke",
            reply_markup=keyboard,
            parse_mode="Markdown"
        )
        return
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ ДАТЬ СОГЛАСИЕ", callback_data="give_consent")],
        [InlineKeyboardButton(text="❌ ОТКАЗАТЬСЯ", callback_data="decline_consent")]
    ])
    
    await message.answer(
        "🌟 *KN5 → OBJ CONVERTER*\n\n"
        "📦 *ЧТО Я ДЕЛАЮ:*\n"
        "• КОНВЕРТИРУЮ .kn5 (Assetto Corsa) В .obj\n"
        "• СОХРАНЯЮ ТЕКСТУРЫ\n"
        "• ОТПРАВЛЯЮ АРХИВОМ\n\n"
        "📋 *2 ШАГА СОГЛАСИЯ:*\n"
        "1️⃣ СОГЛАСИЕ НА ОБРАБОТКУ ФАЙЛА\n"
        "2️⃣ ПОДТВЕРЖДЕНИЕ ПРАВ НА МОДЕЛЬ\n\n"
        "⚠️ *ОТОЗВАТЬ СОГЛАСИЕ ВСЕГДА МОЖНО:* /revoke\n\n"
        "👇 НАЧНИТЕ:",
        reply_markup=keyboard,
        parse_mode="Markdown"
    )

@dp.callback_query_handler(lambda c: c.data == "give_consent")
async def give_consent(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    username = callback.from_user.username or callback.from_user.first_name
    
    user_consent[user_id] = {
        'agreed': True,
        'agreed_at': datetime.now().isoformat(),
        'username': username
    }
    
    log_consent(user_id, username, "AGREED to file processing")
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ ПОДТВЕРЖДАЮ", callback_data="confirm_ownership")],
        [InlineKeyboardButton(text="❌ НЕ ПОДТВЕРЖДАЮ", callback_data="decline_ownership")]
    ])
    
    await callback.message.edit_text(
        "✅ *СОГЛАСИЕ ПОДТВЕРЖДЕНО*\n\n"
        "📋 *ШАГ 2: ПОДТВЕРЖДЕНИЕ ПРАВ*\n\n"
        "ПОДТВЕРДИТЕ:\n"
        "✅ ВЫ ВЛАДЕЛЕЦ МОДЕЛИ ИЛИ ИМЕЕТЕ РАЗРЕШЕНИЕ\n"
        "✅ ВЫ НЕ НАРУШАЕТЕ ПРАВА ТРЕТЬИХ ЛИЦ\n\n"
        "⚠️ *ЮРИДИЧЕСКАЯ ОТВЕТСТВЕННОСТЬ НА ВАС*\n\n"
        "👇 ПОДТВЕРДИТЕ:",
        reply_markup=keyboard,
        parse_mode="Markdown"
    )
    await callback.answer()

@dp.callback_query_handler(lambda c: c.data == "decline_consent")
async def decline_consent(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    username = callback.from_user.username or callback.from_user.first_name
    log_consent(user_id, username, "DECLINED consent")
    
    await callback.message.edit_text(
        "❌ *ВЫ ОТКАЗАЛИСЬ*\n\n"
        "ЕСЛИ ПЕРЕДУМАЕТЕ, /start",
        parse_mode="Markdown"
    )
    await callback.answer()

@dp.callback_query_handler(lambda c: c.data == "confirm_ownership")
async def confirm_ownership(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    username = callback.from_user.username or callback.from_user.first_name
    
    user_ownership[user_id] = {
        'confirmed': True,
        'confirmed_at': datetime.now().isoformat(),
        'username': username
    }
    
    log_ownership(user_id, username, True)
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ ОТОЗВАТЬ ВСЕ СОГЛАСИЯ", callback_data="revoke_all")]
    ])
    
    await callback.message.edit_text(
        "✅ *ПРАВА ПОДТВЕРЖДЕНЫ*\n\n"
        "📦 *ОТПРАВЬТЕ .kn5 ФАЙЛ ДЛЯ КОНВЕРТАЦИИ*\n\n"
        "✨ ЧТО БУДЕТ:\n"
        "1️⃣ Я КОНВЕРТИРУЮ .kn5 В .obj\n"
        "2️⃣ СОХРАНЮ ТЕКСТУРЫ\n"
        "3️⃣ ОТПРАВЛЮ АРХИВОМ\n\n"
        "⚠️ *ОТОЗВАТЬ СОГЛАСИЕ МОЖНО КНОПКОЙ НИЖЕ ИЛИ /revoke*\n\n"
        "👇 ОТПРАВЬТЕ .kn5 ФАЙЛ:",
        reply_markup=keyboard,
        parse_mode="Markdown"
    )
    await callback.answer()

@dp.callback_query_handler(lambda c: c.data == "decline_ownership")
async def decline_ownership(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    username = callback.from_user.username or callback.from_user.first_name
    log_ownership(user_id, username, False)
    
    await callback.message.edit_text(
        "❌ *ПРАВА НЕ ПОДТВЕРЖДЕНЫ*\n\n"
        "БОТ НЕ МОЖЕТ РАБОТАТЬ БЕЗ ВАШЕГО ПОДТВЕРЖДЕНИЯ.\n\n"
        "ЕСЛИ ВЫ ВЛАДЕЛЕЦ МОДЕЛИ, /start",
        parse_mode="Markdown"
    )
    await callback.answer()

# ==================== ОТЗЫВ СОГЛАСИЙ ====================

@dp.callback_query_handler(lambda c: c.data == "revoke_all")
async def revoke_all(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    username = callback.from_user.username or callback.from_user.first_name
    
    if user_id in user_consent:
        log_consent(user_id, username, "REVOKED")
        del user_consent[user_id]
    if user_id in user_ownership:
        log_ownership(user_id, username, False)
        del user_ownership[user_id]
    
    await callback.message.edit_text(
        "❌ *ВСЕ СОГЛАСИЯ ОТОЗВАНЫ*\n\n"
        "ЧТОБЫ НАЧАТЬ ЗАНОВО, /start",
        parse_mode="Markdown"
    )
    await callback.answer()

@dp.message_handler(commands=["revoke"])
async def cmd_revoke(message: types.Message):
    user_id = message.from_user.id
    username = message.from_user.username or message.from_user.first_name
    
    revoked = False
    if user_id in user_consent:
        log_consent(user_id, username, "REVOKED via /revoke")
        del user_consent[user_id]
        revoked = True
    if user_id in user_ownership:
        log_ownership(user_id, username, False)
        del user_ownership[user_id]
        revoked = True
    
    if revoked:
        await message.answer("❌ *СОГЛАСИЯ ОТОЗВАНЫ*\n\n/start ДЛЯ НОВОГО СЕАНСА", parse_mode="Markdown")
    else:
        await message.answer("ℹ️ *НЕТ АКТИВНЫХ СОГЛАСИЙ*\n\n/start", parse_mode="Markdown")

def has_full_consent(user_id: int) -> bool:
    return (user_id in user_consent and user_consent[user_id].get('agreed', False) and
            user_id in user_ownership and user_ownership[user_id].get('confirmed', False))

# ==================== КОНВЕРТЕР KN5 → OBJ ====================

class kn5Material:
    def __init__(self):
        self.name = ""
        self.shader = ""
        self.ksAmbient = 0.6
        self.ksDiffuse = 0.6
        self.ksSpecular = 0.9
        self.ksSpecularEXP = 1.0
        self.diffuseMult = 1.0
        self.useDetail = 0.0
        self.detailUVMultiplier = 1.0
        self.txDiffuse = ""
        self.txNormal = ""
        self.txDetail = ""
        self.txDetailA = ""
        self.ksEmissive = 0.0

class kn5Node:
    def __init__(self):
        self.name = "Default"
        self.parent = None
        self.tmatrix = np.identity(4)
        self.hmatrix = np.identity(4)
        self.type = 1
        self.materialID = -1
        self.vertexCount = 0
        self.indices = []
        self.position = []
        self.normal = []
        self.texture0 = []

def read_string(file, length):
    return file.read(length).decode("utf-8")

def matrix_mult(ma, mb):
    return np.matmul(np.array(ma, copy=True), np.array(mb, copy=True))

def read_nodes(file, node_list, parent_id):
    new_node = kn5Node()
    new_node.parent = parent_id
    new_node.type, = struct.unpack('<i', file.read(4))
    new_node.name = read_string(file, struct.unpack('<i', file.read(4))[0])
    children_count, = struct.unpack('<i', file.read(4))
    file.read(1)

    if new_node.type == 1:
        new_node.tmatrix = [[struct.unpack('<f', file.read(4))[0] for _ in range(4)] for _ in range(4)]
    elif new_node.type == 2:
        file.read(3)
        new_node.vertexCount, = struct.unpack('<i', file.read(4))
        for _ in range(new_node.vertexCount):
            new_node.position.extend(struct.unpack('<fff', file.read(12)))
            new_node.normal.extend(struct.unpack('<fff', file.read(12)))
            tex = struct.unpack('<ff', file.read(8))
            new_node.texture0.extend([tex[0], 1.0 - tex[1]])
            file.read(12)
        index_count, = struct.unpack('<i', file.read(4))
        new_node.indices = struct.unpack('<%dH' % index_count, file.read(index_count * 2))
        new_node.materialID, = struct.unpack('<i', file.read(4))
        file.read(29)
    elif new_node.type == 3:
        file.read(3)
        bone_count, = struct.unpack('<i', file.read(4))
        for _ in range(bone_count):
            _ = read_string(file, struct.unpack('<i', file.read(4))[0])
            file.read(64)
        new_node.vertexCount, = struct.unpack('<i', file.read(4))
        for _ in range(new_node.vertexCount):
            new_node.position.extend(struct.unpack('<fff', file.read(12)))
            new_node.normal.extend(struct.unpack('<fff', file.read(12)))
            tex = struct.unpack('<ff', file.read(8))
            new_node.texture0.extend([tex[0], 1.0 - tex[1]])
            file.read(44)
        index_count, = struct.unpack('<i', file.read(4))
        new_node.indices = struct.unpack('<%dH' % index_count, file.read(index_count * 2))
        new_node.materialID, = struct.unpack('<i', file.read(4))
        file.read(12)

    new_node.hmatrix = new_node.tmatrix if parent_id < 0 else matrix_mult(new_node.tmatrix, node_list[parent_id].hmatrix)
    node_list.append(new_node)
    current_id = len(node_list) - 1

    for _ in range(children_count):
        node_list = read_nodes(file, node_list, current_id)
    return node_list

def transparant_shader(shader):
    return shader.startswith("ksPerPixelAT") or shader in ['ksPerPixelAlpha', 'ksSkidMark', 'ksTree', 'ksGrass', 'ksFlags']

def convert_kn5_to_obj(file_data: bytes, output_dir: str) -> dict:
    with tempfile.NamedTemporaryFile(delete=False, suffix='.kn5') as tmp:
        tmp.write(file_data)
        tmp_path = tmp.name
    
    os.makedirs(output_dir, exist_ok=True)
    
    with open(tmp_path, "rb") as file:
        header = file.read(10)
        _, version = struct.unpack("<6s1I", header)
        if version > 5:
            file.read(4)
        
        tex_count, = struct.unpack("<i", file.read(4))
        for _ in range(tex_count):
            tex_type, = struct.unpack("<i", file.read(4))
            tex_name = read_string(file, struct.unpack("<i", file.read(4))[0])
            tex_size, = struct.unpack("<i", file.read(4))
            tex_path = os.path.join(output_dir, "texture", tex_name)
            os.makedirs(os.path.dirname(tex_path), exist_ok=True)
            with open(tex_path, "wb") as tf:
                tf.write(file.read(tex_size))
        
        mat_count, = struct.unpack("<i", file.read(4))
        materials = []
        for _ in range(mat_count):
            mat = kn5Material()
            mat.name = read_string(file, struct.unpack("<i", file.read(4))[0])
            mat.shader = read_string(file, struct.unpack("<i", file.read(4))[0])
            file.read(2)
            if version > 4:
                file.read(4)
            prop_count, = struct.unpack("<i", file.read(4))
            for _ in range(prop_count):
                prop_name = read_string(file, struct.unpack("<i", file.read(4))[0])
                prop_value, = struct.unpack("<f", file.read(4))
                if prop_name == "ksAmbient": mat.ksAmbient = prop_value
                elif prop_name == "ksDiffuse": mat.ksDiffuse = prop_value
                elif prop_name == "ksSpecular": mat.ksSpecular = prop_value
                elif prop_name == "ksSpecularEXP": mat.ksSpecularEXP = prop_value
                elif prop_name == "diffuseMult": mat.diffuseMult = prop_value
                elif prop_name == "useDetail": mat.useDetail = prop_value
                elif prop_name == "detailUVMultiplier": mat.detailUVMultiplier = prop_value
                elif prop_name == "ksEmissive": mat.ksEmissive = prop_value
                file.read(36)
            tex_count2, = struct.unpack("<i", file.read(4))
            for _ in range(tex_count2):
                sample_name = read_string(file, struct.unpack("<i", file.read(4))[0])
                sample_slot, = struct.unpack("<i", file.read(4))
                tex_name = read_string(file, struct.unpack("<i", file.read(4))[0])
                if sample_name == "txDiffuse": mat.txDiffuse = tex_name
                elif sample_name == "txNormal": mat.txNormal = tex_name
                elif sample_name == "txDetail": mat.txDetail = tex_name
                elif sample_name == "txDetailA": mat.txDetailA = tex_name
            materials.append(mat)
        
        nodes = read_nodes(file, [], -1)
    
    model_name = os.path.splitext(os.path.basename(tmp_path))[0]
    
    # Write OBJ
    obj_path = os.path.join(output_dir, f"{model_name}.obj")
    mtl_path = os.path.join(output_dir, f"{model_name}.mtl")
    
    with open(mtl_path, 'w') as f:
        for mat in materials:
            f.write(f'newmtl {mat.name.replace(" ", "_")}\r\n')
            f.write(f'Ka {mat.ksAmbient} {mat.ksAmbient} {mat.ksAmbient}\r\n')
            f.write(f'Kd {mat.ksDiffuse} {mat.ksDiffuse} {mat.ksDiffuse}\r\n')
            f.write(f'Ks {mat.ksSpecular} {mat.ksSpecular} {mat.ksSpecular}\r\n')
            f.write(f'Ns {mat.ksSpecularEXP}\r\n')
            f.write('illum 2\r\n')
            if transparant_shader(mat.shader):
                f.write('d 0.9999\r\n')
            if mat.useDetail == 1.0 and mat.txDetail:
                f.write(f'map_Kd texture\\{mat.txDetail}\r\n')
                if mat.txDiffuse:
                    f.write(f'map_Ks texture\\{mat.txDiffuse}\r\n')
                if transparant_shader(mat.shader):
                    f.write(f'map_d texture\\{mat.txDetailA}\r\n')
            elif mat.txDiffuse:
                f.write(f'map_Kd texture\\{mat.txDiffuse}\r\n')
                if transparant_shader(mat.shader):
                    f.write(f'map_d texture\\{mat.txDiffuse}\r\n')
            if mat.txNormal:
                f.write(f'bump texture\\{mat.txNormal}\r\n')
            f.write('\r\n')
    
    with open(obj_path, "w") as f:
        f.write(f"# Assetto Corsa model\n# Exported on {datetime.now()}\n\nmtllib {model_name}.mtl\n")
        vertex_pad = 1
        
        for node in nodes:
            if node.name.startswith("AC_") or node.type == 1:
                continue
            if node.type in [2, 3]:
                f.write(f"\ng {node.name.replace(' ', '_')}\n")
                for v in range(node.vertexCount):
                    x, y, z = node.position[v*3:v*3+3]
                    h = node.hmatrix
                    vx = h[0][0]*x + h[1][0]*y + h[2][0]*z + h[3][0]
                    vy = h[0][1]*x + h[1][1]*y + h[2][1]*z + h[3][1]
                    vz = h[0][2]*x + h[1][2]*y + h[2][2]*z + h[3][2]
                    f.write(f"v {vx} {vy} {vz}\n")
                for v in range(node.vertexCount):
                    x, y, z = node.normal[v*3:v*3+3]
                    h = node.hmatrix
                    nx = h[0][0]*x + h[1][0]*y + h[2][0]*z
                    ny = h[0][1]*x + h[1][1]*y + h[2][1]*z
                    nz = h[0][2]*x + h[1][2]*y + h[2][2]*z
                    f.write(f"vn {nx} {ny} {nz}\n")
                uv_mult = 1.0
                if node.materialID >= 0:
                    mat = materials[node.materialID]
                    uv_mult = mat.detailUVMultiplier if mat.useDetail == 1.0 else mat.diffuseMult
                for v in range(node.vertexCount):
                    tx, ty = node.texture0[v*2]*uv_mult, node.texture0[v*2+1]*uv_mult
                    f.write(f"vt {tx} {ty}\n")
                if node.materialID >= 0:
                    f.write(f"\r\nusemtl {materials[node.materialID].name.replace(' ', '_')}\r\n")
                else:
                    f.write("\r\nusemtl Default\r\n")
                for i in range(0, len(node.indices), 3):
                    i1, i2, i3 = node.indices[i]+vertex_pad, node.indices[i+1]+vertex_pad, node.indices[i+2]+vertex_pad
                    f.write(f"f {i1}/{i1}/{i1} {i2}/{i2}/{i2} {i3}/{i3}/{i3}\r\n")
                vertex_pad += node.vertexCount
    
    os.unlink(tmp_path)
    
    return {"model_name": model_name, "obj_path": obj_path, "mtl_path": mtl_path, "texture_dir": os.path.join(output_dir, "texture")}

# ==================== ОСНОВНОЙ ОБРАБОТЧИК ====================

@dp.message_handler(content_types=['document'])
async def handle_kn5_file(message: types.Message):
    user_id = message.from_user.id
    
    if not await ensure_subscribed(message):
        return
    
    if not has_full_consent(user_id):
        await message.answer(
            "⚠️ *ТРЕБУЕТСЯ СОГЛАСИЕ*\n\n"
            "ОТПРАВЬТЕ /start И ПРОЙДИТЕ 2 ШАГА",
            parse_mode="Markdown"
        )
        return
    
    document = message.document
    if not document.file_name.endswith('.kn5'):
        await message.answer("❌ *ОШИБКА*\n\nПожалуйста, отправьте файл с расширением `.kn5`", parse_mode="Markdown")
        return
    
    status_msg = await message.answer(
        "📦 *КОНВЕРТАЦИЯ .kn5 → .obj*\n\n"
        "▰▰▰▰▰▰▰▰▰▰ 0%\n"
        "⏳ Чтение файла...",
        parse_mode="Markdown"
    )
    
    try:
        file = await bot.get_file(document.file_id)
        file_data = await bot.download_file(file.file_path)
        
        await status_msg.edit_text(
            "📦 *КОНВЕРТАЦИЯ .kn5 → .obj*\n\n"
            "▰▰▰▰▰▰▰▰▰▰ 30%\n"
            "🔄 Обработка геометрии...",
            parse_mode="Markdown"
        )
        
        with tempfile.TemporaryDirectory() as tmpdir:
            result = convert_kn5_to_obj(file_data.read(), tmpdir)
            
            await status_msg.edit_text(
                "📦 *КОНВЕРТАЦИЯ .kn5 → .obj*\n\n"
                "▰▰▰▰▰▰▰▰▰▰ 70%\n"
                "📦 Сборка архива...",
                parse_mode="Markdown"
            )
            
            # Создаём ZIP-архив
            zip_path = os.path.join(tmpdir, f"{result['model_name']}.zip")
            with zipfile.ZipFile(zip_path, 'w') as zipf:
                zipf.write(result['obj_path'], arcname=f"{result['model_name']}.obj")
                zipf.write(result['mtl_path'], arcname=f"{result['model_name']}.mtl")
                if os.path.exists(result['texture_dir']):
                    for root, dirs, files in os.walk(result['texture_dir']):
                        for file_name in files:
                            file_path = os.path.join(root, file_name)
                            arcname = os.path.join("texture", file_name)
                            zipf.write(file_path, arcname=arcname)
            
            await status_msg.delete()
            
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="❌ ОТОЗВАТЬ ВСЕ СОГЛАСИЯ", callback_data="revoke_all")]
            ])
            
            with open(zip_path, 'rb') as zip_file:
                await message.answer_document(
                    document=InputFile(zip_file, filename=f"{result['model_name']}.zip"),
                    caption="✅ *КОНВЕРТАЦИЯ ЗАВЕРШЕНА*\n\n"
                            f"📦 Модель: `{result['model_name']}`\n"
                            "📄 Формат: .obj + .mtl + текстуры\n\n"
                            "⚠️ *НАПОМИНАНИЕ:* ОТОЗВАТЬ СОГЛАСИЕ МОЖНО В ЛЮБОЙ МОМЕНТ\n"
                            "➡️ /revoke ИЛИ КНОПКА НИЖЕ",
                    reply_markup=keyboard,
                    parse_mode="Markdown"
                )
        
    except Exception as e:
        await status_msg.edit_text(
            f"❌ *ОШИБКА КОНВЕРТАЦИИ*\n\n"
            f"Файл может быть повреждён или не является .kn5.\n\n"
            f"`{str(e)[:100]}`",
            parse_mode="Markdown"
        )

@dp.message_handler(commands=["help"])
async def cmd_help(message: types.Message):
    await message.answer(
        "📖 *ПОМОЩЬ*\n\n"
        "🔹 /start — НАЧАТЬ (2 ШАГА СОГЛАСИЯ)\n"
        "🔹 /revoke — ОТОЗВАТЬ СОГЛАСИЕ\n\n"
        "📦 *ЧТО ДЕЛАЕТ БОТ:*\n"
        "• ПРИНИМАЕТ .kn5 (Assetto Corsa)\n"
        "• КОНВЕРТИРУЕТ В .obj\n"
        "• СОХРАНЯЕТ ТЕКСТУРЫ\n"
        "• ОТПРАВЛЯЕТ ZIP-АРХИВОМ\n\n"
        "⚠️ *ВЫ МОЖЕТЕ ОТОЗВАТЬ СОГЛАСИЕ В ЛЮБОЙ МОМЕНТ*",
        parse_mode="Markdown"
    )

@dp.message_handler()
async def handle_unknown(message: types.Message):
    await message.answer(
        "❓ *НЕИЗВЕСТНАЯ КОМАНДА*\n\n"
        "📦 ОТПРАВЬТЕ .kn5 ФАЙЛ ДЛЯ КОНВЕРТАЦИИ В .obj\n"
        "ИЛИ /help ДЛЯ СПИСКА КОМАНД\n\n"
        "⚠️ *ОТОЗВАТЬ СОГЛАСИЕ:* /revoke",
        parse_mode="Markdown"
    )

if __name__ == "__main__":
    print("🚀 KN5 → OBJ CONVERTER БОТ ЗАПУЩЕН")
    print("📦 КОНВЕРТАЦИЯ .kn5 В .obj ВКЛЮЧЕНА")
    print("⚠️ ОТМЕНА СОГЛАСИЯ: /revoke")
    executor.start_polling(dp, skip_updates=True)
