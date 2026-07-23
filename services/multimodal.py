import os, base64, json, shutil
from datetime import datetime
from config import PHOTOS_DIR, MODELS_CONFIG_PATH

# 🔹 Кэш capabilities
_model_caps_cache = {}

def load_model_capabilities():
    global _model_caps_cache
    if _model_caps_cache: 
        return _model_caps_cache
    try:
        with open(MODELS_CONFIG_PATH, "r") as f:
            data = json.load(f)
        for eng in ["ollama", "openai", "gemini"]:
            for m in data.get(eng, []):
                _model_caps_cache[m["tag"]] = {
                    "multimodal": m.get("multimodal", False),
                    "supports_audio": m.get("supports_audio", False)
                }
    except Exception: 
        pass
    return _model_caps_cache

def check_capability(model_tag: str, feature: str) -> bool:
    caps = load_model_capabilities()
    return caps.get(model_tag, {}).get(feature, False)

def encode_image_to_base64(img_path: str) -> str:
    """Кодирует JPEG/PNG/HEIC в base64 для Ollama/OpenAI API"""
    if not os.path.exists(img_path):
        print(f"⚠️ Файл не найден для кодирования: {img_path}")
        return ""
    try:
        with open(img_path, "rb") as f:
            raw = f.read()
        if not raw: 
            return ""
        b64 = base64.b64encode(raw).decode("utf-8")
        # Очистка от переносов строк
        return b64.replace("\n", "").replace("\r", "")
    except Exception as e:
        print(f"❌ Ошибка кодирования {img_path}: {e}")
        return ""

def save_bot_photo(file_path: str, user_id: int) -> str:
    """Сохраняет фото из бота в общую папку (КОПИРОВАНИЕ + УДАЛЕНИЕ)"""
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    fname = f"bot_{user_id}_{ts}.jpg"
    os.makedirs(PHOTOS_DIR, exist_ok=True)
    dest = os.path.join(PHOTOS_DIR, fname)
    
    try:
        # ✅ Используем copy вместо move (надёжнее на macOS между томами)
        shutil.copy2(file_path, dest)
        # Удаляем временный файл, если он ещё существует
        if os.path.exists(file_path):
            os.remove(file_path)
        print(f"✅ [SAVE_PHOTO] Saved: {fname}")
        return dest
    except Exception as e:
        # ✅ Используем print вместо logger (чтобы не зависеть от импортов)
        print(f"❌ [SAVE_PHOTO] Error: {e}")
        return ""

def list_photos() -> list:
    if not os.path.exists(PHOTOS_DIR):
        print(f"⚠️ Photos directory does not exist: {PHOTOS_DIR}")
        return []
    valid_ext = ('.jpg', '.jpeg', '.png', '.heic', '.webp')
    try:
        files = [f for f in os.listdir(PHOTOS_DIR) if f.lower().endswith(valid_ext)]
        # Сортировка по дате изменения (новые первыми)
        #return sorted(files, key=lambda x: os.path.getmtime(os.path.join(PHOTOS_DIR, x)), reverse=True)[:10]
        return sorted(files, key=lambda x: x, reverse=True)[:10]
    except Exception as e:
        print(f"❌ Error listing photos: {e}")
        return []

def delete_photo(fname: str) -> bool:
    path = os.path.join(PHOTOS_DIR, fname)
    if os.path.exists(path):
        try:
            os.remove(path)
            print(f"🗑 [DELETE] Deleted: {fname}")
            return True
        except Exception as e:
            print(f"❌ [DELETE] Error: {e}")
    return False