"""CLI Menu - chat selection, creation, deletion"""
import os
import json
from config import CHATS_DIR


def list_chats() -> list[str]:
    if not os.path.exists(CHATS_DIR):
        return []
    return sorted(
        [f for f in os.listdir(CHATS_DIR) if f.endswith(".json")],
        key=lambda x: os.path.getmtime(os.path.join(CHATS_DIR, x)),
        reverse=True,
    )


def load_chat(path: str) -> dict:
    if not os.path.exists(path):
        return {"summary": "", "messages": [], "summaries": []}
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, list):
        data = {"summary": "", "messages": data, "summaries": []}
        save_chat(path, data)
    return data


def save_chat(path: str, data: dict) -> None:
    import tempfile
    try:
        dirpath = os.path.dirname(path)
        with tempfile.NamedTemporaryFile(
            "w", dir=dirpath, delete=False, encoding="utf-8",
        ) as tmp:
            json.dump(data, tmp, ensure_ascii=False, indent=2)
            tmp_path = tmp.name
        os.replace(tmp_path, path)
    except Exception as e:
        print(f"❌ Ошибка сохранения чата {path}: {e}")


def create_new_chat() -> str:
    """Create a new chat file and return its path"""
    from datetime import datetime
    name = input("📝 Название чата (Enter для авто): ").strip()
    if not name:
        name = f"chat_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    fname = f"ch_{name.replace(' ', '_')}.json"
    chat_path = os.path.join(CHATS_DIR, fname)
    save_chat(chat_path, {"summary": "", "messages": [], "summaries": []})
    print(f"✅ Создан чат: {fname}")
    return chat_path
