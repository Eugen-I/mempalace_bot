"""shared.py — Shared state via ConversationFSM, constants, and helpers for palace handlers"""
import json
import logging

from aiogram import Router, types

from services.conversation_fsm import ConversationFSM
from services.text_formatter import safe_html_format

router = Router()
logger = logging.getLogger("Palace")

# ─── Central FSM ───
fsm: ConversationFSM = ConversationFSM()

KG_PAGE_SIZE = 5

KG_PREDICATES = [
    ("topic", "📌 тема"),
    ("related_to", "🔗 связано с"),
    ("wrote", "✍️ написал"),
    ("contains_idea", "💡 идея"),
    ("contains_quote", "💬 цитата"),
    ("author", "👤 автор"),
    ("influenced_by", "🎯 под влиянием"),
]

_LOCALE_ALIASES = {
    # Wing names (Russian → English)
    "мои заметки": "my_notes",
    "заметки": "my_notes",
    "сны": "dreams",
    "мечты": "dreams",
    "фотография": "photography",
    "фото": "photography",
    "фотографии": "photography",
    "фотографы": "photography",
    "личное": "personal",
    "персональное": "personal",
    "психология": "psychology",
    "технологии": "tech",
    "it": "tech",
    "айти": "tech",
    "разработка": "tech",
    "креатив": "creative",
    "творчество": "creative",
    "проекты": "projects",
    "философия": "philosophy",
    "общее": "general",
    "general": "general",
    # Room names within wings
    "сны и отрывки снов": "сны_и_отрывки_снов",
    "докторская": "заметки_для_докторской_диссертации",
    "идеи": "идеи",
    "архетипы": "проект_архитипы_юнга_социальная_маска",
    "названия фото": "названия_фото",
    "it разработка": "it_разработка",
    "цитаты": "цитаты_юнга_по_архитирам",
    "юнг": "цитаты_юнга_по_архитирам",
    "тренировки": "тренировки",
    "стихи": "мои_стихи",
    "сценарии": "сценарии",
    "манифесты": "манифесты",
    "кураторский": "кураторский_текст",
    "психоанализ": "психоаналитическая_модель_опыта_в_творчестве_фотографа",
    "экспликации": "экспликации_к_фотографиям",
    "мысли из книг": "мысли_из_книг",
    "высказывания": "высказывание",
    "дневник": "визуальный_дневник_b_элементов_и_a_функций",
    "выставка": "расходы_на_выставку",
}


def _normalize_query(text: str) -> str:
    t = text.strip().lower()
    if t in _LOCALE_ALIASES:
        return _LOCALE_ALIASES[t]
    t = t.replace(" ", "_")
    return t


# ─── FSM convenience accessors for named data keys ───

def _get_data(uid: int, key: str, default=None):
    return fsm.get_data(uid).get(key, default)


def _set_data(uid: int, **kwargs):
    fsm.update_data(uid, **kwargs)


def _pop_data(uid: int, key: str, default=None):
    return fsm.pop_data(uid, key, default)


# ─── Legacy state dict aliases for migration ───

class _FsmDict:
    """Dict-like wrapper reading from/writing to fsm data namespace."""
    def __init__(self, ns: str):
        self._ns = ns

    def get(self, uid: int, default=None):
        return fsm.get_data(uid).get(self._ns, default)

    def pop(self, uid: int, *args):
        return fsm.pop_data(uid, self._ns, *args)

    def __getitem__(self, uid: int):
        val = fsm.get_data(uid).get(self._ns)
        if val is None:
            raise KeyError(uid)
        return val

    def __setitem__(self, uid: int, value):
        fsm.update_data(uid, **{self._ns: value})

    def __contains__(self, uid: int) -> bool:
        return self._ns in fsm.get_data(uid)

    def setdefault(self, uid: int, default=None):
        data = fsm.get_data(uid)
        if self._ns not in data:
            fsm.update_data(uid, **{self._ns: default or {}})
        return fsm.get_data(uid).get(self._ns)


_pending_mcp_input = _FsmDict("_pending_mcp_input")
_kg_page_data = _FsmDict("_kg_page_data")
_kg_search_data = _FsmDict("_kg_search_data")
_kg_add_state = _FsmDict("_kg_add_state")
_save_state = _FsmDict("_save_state")
_wing_cache = _FsmDict("_wing_cache")
_room_cache = _FsmDict("_room_cache")
_tunnel_state = _FsmDict("_tunnel_state")
_create_tunnel_state = _FsmDict("_create_tunnel_state")
_drawer_state = _FsmDict("_drawer_state")
_read_state = _FsmDict("_read_state")
_room_session = _FsmDict("_room_session")
_tunnels_cache = _FsmDict("_tunnels_cache")
_user_context = _FsmDict("_user_context")


async def _send_kg_page(uid: int, edit_func):
    data = _kg_page_data.get(uid)
    if not data:
        return
    facts = data["facts"]
    page = data["page"]
    total = len(facts)
    start = page * KG_PAGE_SIZE
    end = min(start + KG_PAGE_SIZE, total)
    page_facts = facts[start:end]

    lines = [f"<b>🧠 Сущность: {data['entity']}</b>  <i>({total} фактов)</i>\n"]
    for i, f in enumerate(page_facts):
        if isinstance(f, dict):
            line = (
                f"  • {safe_html_format(f.get('subject', '?'))} → "
                f"{safe_html_format(f.get('predicate', '?'))} → "
                f"{safe_html_format(f.get('object', '?'))}"
            )
            src = f.get("source_closet", "")
            if src:
                short_src = src.rsplit("/", 1)[-1]
                line += f"\n    📄 {safe_html_format(short_src)}"
            if f.get("valid_from"):
                line += f" (с {f['valid_from']})"
        else:
            line = f"  • {safe_html_format(str(f))}"
        lines.append(line)

    nav_buttons = []
    if end < total:
        more = total - end
        nav_buttons.append(
            types.InlineKeyboardButton(
                text=f"▶️ Продолжить ({more})", callback_data="p_kgc",
            ),
        )
    elif page > 0:
        nav_buttons.append(
            types.InlineKeyboardButton(text="◀️ Начать сначала", callback_data="p_kgs"),
        )
    extra_rows = []
    if nav_buttons:
        extra_rows.append(nav_buttons)
    extra_rows.append([types.InlineKeyboardButton(
        text="📖 Читать записи", callback_data="p_kgr",
    )])

    from .action_bar import finalize_answer
    await finalize_answer(
        uid, edit_func, "\n".join(lines), is_html=True,
        ctx={"entity": data["entity"], "parent_cb": "p_kg"},
        extra_rows=extra_rows,
    )


async def _format_mcp_result(raw: str) -> str:
    try:
        data = json.loads(raw)
        if isinstance(data, dict):
            lines = []
            for k, v in data.items():
                if isinstance(v, dict):
                    sub = "\n".join(f"  • {sk}: {sv}" for sk, sv in v.items())
                    lines.append(f"**{k}:**\n{sub}")
                elif isinstance(v, list):
                    items = "\n".join(f"  • {i}" for i in v)
                    lines.append(f"**{k}:**\n{items}")
                else:
                    lines.append(f"**{k}:** {v}")
            return "\n".join(lines)
        return raw
    except (json.JSONDecodeError, TypeError):
        return raw
