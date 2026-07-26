"""CLI Commands - all command handler functions extracted from chat_loop"""
import os
import re
import json
import asyncio
from datetime import datetime
from rich.console import Console
from rich.syntax import Syntax

from config import (
    NOTES_DIR, INSIGHTS_DIR, RESEARCH_DIR, PHOTOS_DIR,
    MODELS_CONFIG_PATH, CONFIG_AI_FILE,
)
from services.palace_bridge import (
    search_palace_context, sync_to_palace, palace_status, palace_mcp,
    palace_wake_up, palace_repair, palace_compact, palace_compress,
    search_with_kg, export_chat_verbatim
)
from services.palace_mcp import get_mcp
from services.ai_engine import get_ai_response_async, get_current_ai, invalidate_ai_cache
from services.memory import extract_and_store_facts, get_memory_context
from services.wing_classifier import classify_wing
from services.note_linker import link_note_async
from services.multimodal import list_photos, encode_image_to_base64, check_capability
from services.prompts import get_smart_prompt
from services.kg_enricher import enrich_all_notes
from cli.utils import (
    C, format_for_terminal, speak_text, save_chat, get_cli_voice,
    set_cli_voice, generate_summary_if_needed, export_chat_to_md,
)
from cli_extras import cli_yt, cli_pdfs, cli_remind, cli_tunnels, cli_kgadd, cli_transkript


async def cmd_photos():
    photos = list_photos()
    if not photos:
        print(f"{C.YELLOW}Папка photos пуста.{C.END}")
    else:
        print(f"{C.CYAN}Фото в базе ({len(photos)}):{C.END}")
        for i, p in enumerate(photos, 1):
            print(f"  {i}) {p}")


async def cmd_analyze_photo(engine, model, messages):
    if not check_capability(model, "multimodal"):
        print(f"{C.RED}Модель {model} не поддерживает анализ фото.{C.END}")
        return
    photos = list_photos()
    if not photos:
        print(f"{C.RED}Нет фото для анализа.{C.END}")
        return
    print(f"{C.CYAN}Анализирую последние фото...{C.END}")
    imgs = []
    for p in photos[:2]:
        try:
            b64 = encode_image_to_base64(os.path.join(PHOTOS_DIR, p))
            if b64:
                imgs.append(b64)
        except Exception as e:
            print(f"{C.YELLOW}Ошибка кодирования {p}: {e}{C.END}")
    if not imgs:
        print(f"{C.RED}Не удалось подготовить фото.{C.END}")
        return
    palace_context = await search_palace_context(
        "фото сон сюрреализм пиктореализм психология идеи образы", limit=7,
    )
    photo_sys = get_smart_prompt(
        context=palace_context,
        query="анализ фотографии, символика, связь с заметками",
        has_images=True,
    )
    photo_ctx = [{"role": "system", "content": photo_sys}]
    photo_ctx.extend(messages[-10:] if len(messages) > 10 else messages)
    photo_ctx.append({
        "role": "user",
        "content": (
            "Проанализируй прикрепленные фотографии. "
            "Есть ли здесь связь с моими снами или заметками?"
        ),
    })
    try:
        answer = await get_ai_response_async(engine, model, photo_ctx, context="", images=imgs)
        print(f"\n{C.GREEN}AI (Photo): {format_for_terminal(answer)}{C.END}\n")
    except Exception as e:
        print(f"{C.RED}Ошибка анализа: {e}{C.END}")


async def cmd_sound_toggle():
    vc = get_cli_voice()
    new_state = not vc.get("enabled", True)
    set_cli_voice("enabled", new_state)
    print(f"{C.GREEN}Озвучка: {'Вкл' if new_state else 'Выкл'}{C.END}")


async def cmd_sound_speed(cmd):
    try:
        spd = int(cmd)
        spd = max(100, min(300, spd))
        set_cli_voice("speed", spd)
        print(f"{C.GREEN}Скорость голоса: {spd} wpm{C.END}")
    except ValueError:
        print(f"{C.RED}Неверный формат. Используйте: звук-150 (100-300){C.END}")


async def cmd_history(messages):
    print(f"\n{C.CYAN}История чата:{C.END}")
    for m in messages:
        if m.get("role") == "system" and m.get("type") == "summary":
            print(f"\n{C.PURPLE}{'─' * 40}{C.END}")
            print(f"{C.PURPLE}САММАРИ ЭТАПА:{C.END}\n{format_for_terminal(m['content'])}")
            print(f"{C.PURPLE}{'─' * 40}{C.END}\n")
        elif m["role"] in ["user", "assistant"]:
            role_tag = f"{C.YELLOW}Вы:{C.END}" if m["role"] == "user" else f"{C.GREEN}ИИ:{C.END}"
            content_preview = m["content"][:200] + ("..." if len(m["content"]) > 200 else "")
            print(f"{role_tag} {format_for_terminal(content_preview)}")
    print()


async def cmd_export(chat_path):
    md_path = export_chat_to_md(chat_path)
    print(f"{C.GREEN}Экспортировано в: {md_path}{C.END}")


async def cmd_search(user_input):
    query_raw = user_input.strip()
    if not query_raw:
        print(f"{C.RED}Укажите запрос: /search <текст> или /search --wing dreams <текст>{C.END}")
        return
    wing = ""
    search_text = query_raw
    wing_match = re.match(r"^--wing\s+(\w+)\s+(.*)", query_raw)
    if wing_match:
        wing = wing_match.group(1).lower()
        search_text = wing_match.group(2)
        if wing not in ["dreams", "projects", "philosophy", "creative", "psychology"]:
            print(f"{C.YELLOW}Неизвестное крыло: {wing}. Ищу глобально.{C.END}")
            wing = ""
    print(f"{C.CYAN}Ищу в MemPalace{' (крыло: ' + wing + ')' if wing else ''}...{C.END}")
    res = await search_palace_context(search_text, limit=3, wing=wing)
    print(f"\n{C.GREEN}{res}{C.END}\n")


async def cmd_status():
    print(f"{C.CYAN}Получаю статус MemPalace...{C.END}")
    res = await palace_status()
    print(f"{C.GREEN}{res}{C.END}\n")


async def cmd_mcp():
    print(f"{C.CYAN}Получаю команду настройки MCP...{C.END}")
    res = await palace_mcp()
    print(f"{C.GREEN}{res}{C.END}\n")


async def cmd_wakeup():
    print(f"{C.CYAN}Загружаю дворец в контекст...{C.END}")
    res = await palace_wake_up()
    print(f"{C.GREEN}{res}{C.END}\n")


async def cmd_repair():
    print(f"{C.YELLOW}Перестройка векторного индекса может занять время...{C.END}")
    print(f"{C.CYAN}Запускаю repair...{C.END}")
    res = await palace_repair()
    print(f"{C.GREEN}{res}{C.END}\n")


async def cmd_compact():
    print(f"{C.CYAN}Запускаю compact (очистка сегментов БД)...{C.END}")
    res = await palace_compact()
    print(f"{C.GREEN}{res}{C.END}\n")


async def cmd_compress():
    print(f"{C.CYAN}Сжимаю текст хранилища...{C.END}")
    res = await palace_compress()
    print(f"{C.GREEN}{res}{C.END}\n")


async def cmd_palace():
    print(f"{C.CYAN}Дворец MemPalace — команды:{C.END}")
    for line in [
        "/status     — статистика дворца (крылья, комнаты, записи)",
        "/wings      — список всех крыльев",
        "/rooms      — список комнат",
        "/taxonomy   — полная таксономия",
        "/graph      — статистика графа",
        "/traverse   — траверс графа из комнаты",
        "/tunnels    — туннели между крыльями",
        "/follow     — пройти туннели из комнаты",
        "/kg         — поиск в графе знаний",
        "/kgstats    — статистика KG",
        "/mcp        — инструкция MCP",
        "/wakeup     — загрузить дворец в контекст",
        "/repair     — перестроить индекс",
        "/compact    — сжать БД (очистить старые сегменты)",
        "/compress   — сжать текст (AAAK Dialect)",
    ]:
        print(f"  {C.YELLOW}{line}{C.END}")
    print()


async def cmd_wings():
    print(f"{C.CYAN}Загружаю список крыльев...{C.END}")
    try:
        mcp = get_mcp()
        await mcp.start()
        raw = await mcp.call_tool("mempalace_list_wings")
        parsed = json.loads(raw)
        wings = parsed.get("wings", {})
        for name, count in sorted(wings.items(), key=lambda x: -x[1]):
            display = name.replace("mempalace_", "").replace("_", " ").title()
            print(f"  {C.GREEN}{display}:{C.END} {count} записей")
    except Exception as e:
        print(f"{C.RED}Ошибка: {e}{C.END}")
    print()


async def cmd_rooms(cmd):
    wing = cmd.split(maxsplit=1)[1] if cmd and len(cmd.split()) > 1 else None
    print(f"{C.CYAN}Загружаю комнаты{' крыла ' + wing if wing else ''}...{C.END}")
    try:
        mcp = get_mcp()
        await mcp.start()
        args = {"wing": wing} if wing else {}
        raw = await mcp.call_tool("mempalace_list_rooms", args)
        parsed = json.loads(raw)
        rooms = parsed.get("rooms", {})
        wing_name = parsed.get("wing", wing or "все")
        print(f"  {C.BOLD}{C.YELLOW}Комнаты «{wing_name}»:{C.END}\n")
        for idx, (room, count) in enumerate(sorted(rooms.items()), 1):
            print(f"  {idx}. {C.BOLD}{room}{C.END} — {count}")
    except Exception as e:
        print(f"{C.RED}Ошибка: {e}{C.END}")
    print()


async def cmd_taxonomy():
    print(f"{C.CYAN}Загружаю таксономию...{C.END}")
    try:
        mcp = get_mcp()
        await mcp.start()
        raw = await mcp.call_tool("mempalace_get_taxonomy")
        parsed = json.loads(raw)
        tax = parsed.get("taxonomy", {})
        for wing, rooms in sorted(tax.items()):
            display = wing.replace("_", " ").title()
            total = sum(rooms.values())
            print(f"  {C.YELLOW}{display}:{C.END} {total} записей, {len(rooms)} комнат")
    except Exception as e:
        print(f"{C.RED}Ошибка: {e}{C.END}")
    print()


async def cmd_graph():
    print(f"{C.CYAN}Загружаю статистику графа...{C.END}")
    try:
        mcp = get_mcp()
        await mcp.start()
        raw = await mcp.call_tool("mempalace_graph_stats")
        parsed = json.loads(raw)
        print(f"  {C.GREEN}Комнат всего:{C.END} {parsed.get('total_rooms', 0)}")
        print(f"  {C.GREEN}Комнат с туннелями:{C.END} {parsed.get('tunnel_rooms', 0)}")
        print(f"  {C.GREEN}Связей:{C.END} {parsed.get('total_edges', 0)}")
    except Exception as e:
        print(f"{C.RED}Ошибка: {e}{C.END}")
    print()


async def cmd_traverse(cmd):
    parts = cmd.split(maxsplit=2)
    if len(parts) < 2:
        print(f"{C.RED}Укажите команду: /traverse <комната> [шаги]{C.END}")
        return
    room = parts[1]
    hops = int(parts[2]) if len(parts) > 2 else 2
    print(f"{C.CYAN}Траверс из комнаты «{room}» ({hops} шагов)...{C.END}")
    try:
        mcp = get_mcp()
        await mcp.start()
        raw = await mcp.call_tool("mempalace_traverse", {"start_room": room, "max_hops": hops})
        print(f"{C.GREEN}{raw}{C.END}")
    except Exception as e:
        print(f"{C.RED}Ошибка: {e}{C.END}")
    print()


async def cmd_tunnels(user_input):
    result = await cli_tunnels(user_input)
    print(f"{C.CYAN}{result}{C.END}")


async def cmd_follow(cmd):
    parts = cmd.split(maxsplit=2)
    if len(parts) < 3:
        print(f"{C.RED}Укажите крыло и комнату: /follow <крыло> <комната>{C.END}")
        return
    wing, room = parts[1], parts[2]
    print(f"{C.CYAN}Следую туннелям из {wing}/{room}...{C.END}")
    try:
        mcp = get_mcp()
        await mcp.start()
        raw = await mcp.call_tool("mempalace_follow_tunnels", {"wing": wing, "room": room})
        print(f"{C.GREEN}{raw}{C.END}")
    except Exception as e:
        print(f"{C.RED}Ошибка: {e}{C.END}")
    print()


async def cmd_kg(user_input):
    from handlers.palace import _normalize_query
    entity = user_input.strip()
    if not entity:
        print(f"{C.RED}Укажите сущность для поиска в KG.{C.END}")
        return
    norm_entity = _normalize_query(entity)
    print(f"{C.CYAN}Ищу «{norm_entity}» в графе знаний...{C.END}")
    try:
        mcp = get_mcp()
        await mcp.start()
        raw = await mcp.call_tool("mempalace_kg_query", {"entity": norm_entity})
        parsed = json.loads(raw)
        facts = parsed if isinstance(parsed, list) else parsed.get("facts", [])
        if not facts:
            print(f"{C.YELLOW}Нет фактов о «{norm_entity}» в графе знаний.{C.END}")
        else:
            for f in facts:
                if isinstance(f, dict):
                    line = (
                        f"  • {f.get('subject', '?')} → "
                        f"{f.get('predicate', '?')} → {f.get('object', '?')}"
                    )
                    if f.get("valid_from"):
                        line += f" (с {f['valid_from']})"
                    print(f"{C.GREEN}{line}{C.END}")
                else:
                    print(f"  • {f}")
    except Exception as e:
        print(f"{C.RED}Ошибка: {e}{C.END}")
    print()


async def cmd_kgstats():
    print(f"{C.CYAN}Загружаю статистику графа знаний...{C.END}")
    try:
        mcp = get_mcp()
        await mcp.start()
        raw = await mcp.call_tool("mempalace_kg_stats")
        parsed = json.loads(raw)
        print(f"  {C.GREEN}Сущностей:{C.END} {parsed.get('entities', 0)}")
        print(f"  {C.GREEN}Связей:{C.END} {parsed.get('triples', 0)}")
        print(f"  {C.GREEN}Актуальных фактов:{C.END} {parsed.get('current_facts', 0)}")
        print(f"  {C.GREEN}Устаревших фактов:{C.END} {parsed.get('expired_facts', 0)}")
    except Exception as e:
        print(f"{C.RED}Ошибка: {e}{C.END}")
    print()


async def cmd_enrich():
    notes_count = sum(
        1
        for r, d, fs in os.walk(NOTES_DIR)
        for f in fs
        if f.endswith((".txt", ".md"))
    )
    print(f"{C.YELLOW}Запускаю enrichment заметок в Knowledge Graph...{C.END}")
    print(f"{C.YELLOW}Найдено {notes_count} файлов. Продолжить? (y/n):{C.END}")
    try:
        confirm = input().strip().lower()
        if confirm != "y":
            print(f"{C.RED}Отменено.{C.END}")
            return
    except (EOFError, KeyboardInterrupt):
        return
    print(f"{C.CYAN}Обогащаю заметки...{C.END}")

    async def _progress(curr, total, stats):
        print(
            f"{C.CYAN}  [{curr}/{total}] {stats['processed']} "
            f"обработано, {stats['kg_added']} фактов добавлено{C.END}"
        )

    try:
        result = await enrich_all_notes(_progress)
        if "error" in result:
            print(f"{C.RED}{result['error']}{C.END}")
        else:
            print(f"\n{C.GREEN}Enrichment завершён:{C.END}")
            print(f"  • Обработано файлов: {result['processed']}")
            print(f"  • Не удалось: {result['failed']}")
            print(f"  • Фактов добавлено в KG: {result['kg_added']}")
            print(f"  • Найдено авторов: {len(result.get('authors', []))}")
            print(f"  • Найдено книг: {len(result.get('books', []))}")
            for a in result.get("authors", [])[:5]:
                print(f"    - {a}")
            if len(result.get("authors", [])) > 5:
                print(f"    ... и ещё {len(result['authors']) - 5}")
    except Exception as e:
        print(f"{C.RED}Ошибка: {e}{C.END}")


async def cmd_sync(chat_path):
    print(f"{C.CYAN}Подготовка verbatim-экспорта текущего чата...{C.END}")
    exported = export_chat_verbatim(chat_path, os.path.basename(chat_path))
    if not exported:
        print(f"{C.YELLOW}Чат пуст или не найден.{C.END}")
        return
    print(f"{C.CYAN}Запускаю mempalace mine...{C.END}")
    result = await sync_to_palace(exported)
    print(f"{C.GREEN}{result}{C.END}")


async def cmd_remind(user_input):
    text = user_input.replace("/remind", "", 1).strip() if user_input else ""
    result = await cli_remind(text, 0)
    print(f"{C.GREEN}{result}{C.END}")


async def cmd_pdfs(user_input):
    result = await cli_pdfs(user_input)
    if result:
        print(f"{C.CYAN}{result}{C.END}")


async def cmd_yt(user_input, mode):
    result = await cli_yt(user_input, mode)
    print(f"{C.CYAN}{result}{C.END}")


async def cmd_transkript(user_input):
    result = await cli_transkript(user_input)
    if result:
        print(f"{C.CYAN}{result}{C.END}")


async def cmd_kgadd(user_input):
    result = await cli_kgadd(user_input)
    print(f"{C.CYAN}{result}{C.END}")


async def cmd_settings(messages, data, chat_path):
    if not os.path.exists(MODELS_CONFIG_PATH):
        print(f"{C.RED}models.json не найден.{C.END}")
        return
    with open(MODELS_CONFIG_PATH) as f:
        models = json.load(f)
    all_m = [
        (m.get("name", m["tag"]), m["tag"])
        for eng in ["ollama", "openai", "gemini"]
        for m in models.get(eng, [])
    ]
    print(f"\n{C.CYAN}Модели:{C.END}")
    for i, (n, t) in enumerate(all_m, 1):
        print(f"  {i}) {n} ({t})")
    print("  0) Отмена")
    try:
        ch = int(input(f"{C.YELLOW}Выбор: {C.END}"))
        if ch == 0:
            return
        if 1 <= ch <= len(all_m):
            with open(CONFIG_AI_FILE, "w") as f:
                f.write(all_m[ch - 1][1])
            invalidate_ai_cache()
            engine, model = get_current_ai()
            print(f"{C.GREEN}Модель: {model}{C.END}")
    except ValueError:
        print(f"{C.RED}Неверный ввод.{C.END}")


async def save_quick_note(clean_q):
    fn = f"nt_cli_{datetime.now().strftime('%Y%m%d_%H%M')}.txt"
    note_path = os.path.join(NOTES_DIR, fn)
    with open(note_path, "w", encoding="utf-8") as f:
        f.write(clean_q)
    print(f"{C.GREEN}Сохранено в my_notes.{C.END}")
    try:
        print(f"{C.YELLOW}Поиск связанных записей...{C.END}")
        await link_note_async(note_path, clean_q, prefix="!")
        print(f"{C.GREEN}Связывание завершено.{C.END}")
    except Exception as e:
        print(f"{C.YELLOW}Ошибка связывания: {e}{C.END}")


async def save_extraction(prefix, clean_q, messages, answer, engine, model):
    if prefix == "!!":
        content = answer
        folder = INSIGHTS_DIR
        label = "Insights"
        fn_prefix = "ins"
    elif prefix == "???":
        content = answer
        folder = RESEARCH_DIR
        label = "Research"
        fn_prefix = "res"
    else:
        return
    if not content:
        print(f"{C.YELLOW}Нет ответа для сохранения.{C.END}")
        return
    fn = f"{fn_prefix}_cli_{datetime.now().strftime('%Y%m%d_%H%M')}.txt"
    note_path = os.path.join(folder, fn)
    with open(note_path, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"{C.GREEN}Сохранено в {label}.{C.END}")


async def process_ai_query(clean_q, messages, data, chat_path, engine, model):
    target_wing = None
    explicit_match = re.match(r"^/(\w+):\s*(.+)", clean_q)
    if explicit_match:
        possible_wing = explicit_match.group(1).lower()
        if possible_wing in ["dreams", "projects", "philosophy", "creative", "psychology"]:
            target_wing = possible_wing
            clean_q = explicit_match.group(2)
            print(f"{C.CYAN}Явное крыло: {target_wing}{C.END}")

    if not target_wing:
        auto_wing = classify_wing(clean_q)
        if auto_wing:
            target_wing = auto_wing
            print(f"{C.CYAN}Авто-крыло: {target_wing}{C.END}")

    palace_context = await search_with_kg(clean_q, limit=3, wing=target_wing)
    latest_summary = data.get("summaries", [])[-1] if data.get("summaries") else ""

    from services.code_mode import (
        is_coding_context, ensure_project_dir, load_coding_prompt, read_project_files,
    )
    is_code = is_coding_context(clean_q, messages)
    if is_code and not data.get("is_coding_mode"):
        data["is_coding_mode"] = True
        data["project_dir"] = ensure_project_dir(os.path.basename(chat_path))
        save_chat(chat_path, data)
        print(
            f"\n{C.YELLOW}Активирован режим программирования. "
            f"Проект: {data['project_dir']}{C.END}"
        )

    has_images_cli = False
    system_instruction = get_smart_prompt(
        context=palace_context, query=clean_q, has_images=has_images_cli,
    )

    if latest_summary:
        system_instruction += f"\nКонтекст текущего диалога:\n{latest_summary}"

    try:
        uid = hash(chat_path)
        memory_ctx = get_memory_context(clean_q, uid)
        if memory_ctx:
            system_instruction += "\n" + memory_ctx
    except Exception:
        pass

    if data.get("is_coding_mode"):
        system_instruction += f"\nСПЕЦИАЛИЗАЦИЯ: РАЗРАБОТКА\n{load_coding_prompt()}"
        proj_files = read_project_files(data.get("project_dir"))
        if proj_files:
            system_instruction += f"\nФайлы текущего проекта:\n{proj_files}"

    context_msgs = [{"role": "system", "content": system_instruction}]
    context_msgs.extend(messages[-10:] if len(messages) > 10 else messages)
    context_msgs.append({"role": "user", "content": clean_q})

    photo_keywords = [
        "фото", "фотку", "картинк", "изображен", "снимок", "визуал",
        "проанализируй фото", "что на фото", "опиши фото", "разбор фото",
        "photo", "image", "picture",
    ]
    wants_photo = any(kw in clean_q.lower() for kw in photo_keywords)
    if wants_photo and check_capability(model, "multimodal"):
        recent_photos = list_photos()[:1]
        for p in recent_photos:
            b64 = encode_image_to_base64(os.path.join(PHOTOS_DIR, p))
            if b64:
                for m in reversed(context_msgs):
                    if m["role"] == "user" and isinstance(m["content"], str):
                        m["content"] = [
                            {"type": "text", "text": m["content"]},
                            {
                                "type": "image_url",
                                "image_url": {"url": f"data:image/jpeg;base64,{b64}"},
                            },
                        ]
                        break
                break

    print(f"{C.CYAN}{model} думает...{C.END}")
    try:
        answer = await get_ai_response_async(engine, model, context_msgs, context="")

        console = Console()
        if "```" in answer:
            parts = answer.split("```")
            for i, part in enumerate(parts):
                if i % 2 == 0:
                    if part.strip():
                        print(f"{C.GREEN}AI: {format_for_terminal(part)}{C.END}")
                else:
                    lines = part.split('\n')
                    lang = lines[0].strip() if lines else ""
                    code = '\n'.join(lines[1:]) if len(lines) > 1 else part
                    syntax = Syntax(code, lang or "python", theme="monokai", line_numbers=True)
                    console.print(syntax)
        else:
            print(f"{C.GREEN}AI: {format_for_terminal(answer)}{C.END}")

        voice_cfg = get_cli_voice()
        messages.append({"role": "user", "content": clean_q})
        messages.append({"role": "assistant", "content": answer})

        speak_text(
            answer,
            voice_cfg.get("speed", 160),
            voice_cfg.get("voice", "Milena"),
            voice_cfg.get("enabled", True),
        )

        asyncio.create_task(extract_and_store_facts(messages, hash(chat_path)))
        await generate_summary_if_needed(messages, data, chat_path)

        save_chat(chat_path, data)

        return answer

    except Exception as e:
        print(f"{C.RED}Ошибка ИИ: {e}{C.END}")
        import traceback
        traceback.print_exc()
        return None
