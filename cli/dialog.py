"""CLI Dialog - main chat loop with prompt_toolkit"""
import os

from prompt_toolkit import PromptSession
from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.formatted_text import HTML

from services.ai_engine import get_current_ai
from cli.menu import load_chat, save_chat
from cli.commands import (
    cmd_photos, cmd_analyze_photo, cmd_sound_toggle, cmd_sound_speed,
    cmd_history, cmd_export, cmd_search,
    cmd_status, cmd_mcp, cmd_wakeup, cmd_repair, cmd_compact, cmd_compress, cmd_palace,
    cmd_wings, cmd_rooms, cmd_taxonomy, cmd_graph, cmd_traverse,
    cmd_tunnels, cmd_follow, cmd_kg, cmd_kgstats, cmd_enrich, cmd_sync,
    cmd_remind, cmd_pdfs, cmd_yt, cmd_transkript, cmd_kgadd,
    cmd_settings, save_quick_note, save_extraction, process_ai_query,
)
from cli.utils import C, format_for_terminal, get_cli_voice
from cli.help_sections import HELP_SECTIONS


# CLI Completer for commands
class CLICompleter(Completer):
    def __init__(self):
        self.commands = [
            '/help', '/h', '/search', '/history', '/export', '/new', '/del', '/chats',
            '/sync', '/photos', '/analyze_photo', '/status', '/mcp', '/wakeup',
            '/repair', '/compact', '/compress', '/palace', '/wings', '/rooms',
            '/taxonomy', '/graph', '/traverse', '/tunnels', '/follow', '/kg',
            '/kgadd', '/kgstats', '/enrich', '/settings', '/pdfs', '/transkript',
            '/yt', '/ytaudio', '/remind', 'звук', 'звук-',
        ]
        self.palace_subcommands = [
            'list', 'create', 'delete', 'analyze', 'between',
        ]

    def get_completions(self, document, complete_event):
        text = document.text_before_cursor

        if text.startswith('/tunnels '):
            sub = text[9:]
            for cmd in self.palace_subcommands:
                if cmd.startswith(sub):
                    yield Completion(cmd, start_position=-len(sub))
            return

        if text.startswith('/'):
            for cmd in self.commands:
                if cmd.startswith(text):
                    yield Completion(cmd, start_position=-len(text))
        elif text.startswith('звук'):
            for cmd in ['звук', 'звук-100', 'звук-150', 'звук-200', 'звук-250', 'звук-300']:
                if cmd.startswith(text):
                    yield Completion(cmd, start_position=-len(text))


# Key bindings
bindings = KeyBindings()


@bindings.add('c-c')
def _(event):
    event.app.exit(result=KeyboardInterrupt)


@bindings.add('c-r')
def _(event):
    pass


# generate_summary_if_needed is imported from cli.utils


async def chat_loop(chat_path: str, session: PromptSession):
    """Main chat loop for a single chat session"""
    data = load_chat(chat_path)
    messages = data.get("messages", [])
    voice_cfg = get_cli_voice()
    engine, model = get_current_ai()

    print(f"\n{C.CYAN}=========================================================={C.END}")
    print(f"{C.CYAN}💬 Активен чат: {C.BOLD}{os.path.basename(chat_path)}{C.END}")
    voice_status = 'Вкл' if voice_cfg['enabled'] else 'Выкл'
    print(
        f"{C.GREEN}🤖 Модель: {model} ({engine}) | "
        f"🎤 Голос: {voice_status} ({voice_cfg['voice']}, {voice_cfg['speed']} wpm){C.END}"
    )
    print(f"{C.YELLOW}Введите h для справки. q или й для выхода.{C.END}")
    print(f"{C.CYAN}==========================================================\n{C.END}")

    while True:
        try:
            user_input = await session.prompt_async(
                HTML('<ansiyellow>Вы: </ansiyellow>'),
                completer=CLICompleter(),
            )
            user_input = user_input.strip()
        except (EOFError, KeyboardInterrupt):
            print(f"\n{C.RED}👋 Завершение...{C.END}")
            break

        if not user_input:
            continue

        cmd = user_input.lower()

        # --- Commands ---
        if cmd == "/photos":
            await cmd_photos()
            continue

        if cmd == "/analyze_photo":
            await cmd_analyze_photo(engine, model, messages)
            continue

        if cmd == "звук":
            await cmd_sound_toggle()
            continue

        if cmd.startswith("звук-"):
            await cmd_sound_speed(cmd.split("-", 1)[1])
            continue

        if cmd in ["q", "й", "quit", "exit", "выход"]:
            print(f"{C.GREEN}Сохраняю диалог...{C.END}")
            save_chat(chat_path, data)
            return "quit"

        if cmd in ["/help", "/h", "-h", "h", "help"]:
            from cli.help_sections import show_help
            show_help()
            continue

        if cmd.startswith("h ") or cmd.startswith("help "):
            key = user_input.split(maxsplit=1)[1]
            if key in HELP_SECTIONS:
                from cli.help_sections import show_section
                show_section(key)
            elif key == "0":
                from cli.help_sections import show_all_help
                show_all_help()
            else:
                print(f"{C.RED}Неизвестный раздел. Введите h для списка.{C.END}")
            continue

        if cmd == "/history":
            await cmd_history(messages)
            continue

        if cmd == "/export":
            await cmd_export(chat_path)
            continue

        if cmd.startswith("/search "):
            await cmd_search(user_input[8:])
            continue

        if cmd == "/status":
            await cmd_status()
            continue
        if cmd == "/mcp":
            await cmd_mcp()
            continue
        if cmd == "/wakeup":
            await cmd_wakeup()
            continue
        if cmd == "/repair":
            await cmd_repair()
            continue
        if cmd == "/compact":
            await cmd_compact()
            continue
        if cmd == "/compress":
            await cmd_compress()
            continue

        if cmd == "/palace":
            await cmd_palace()
            continue

        if cmd == "/wings":
            await cmd_wings()
            continue

        if cmd.startswith("/rooms"):
            await cmd_rooms(cmd)
            continue

        if cmd == "/taxonomy":
            await cmd_taxonomy()
            continue

        if cmd == "/graph":
            await cmd_graph()
            continue

        if cmd.startswith("/traverse"):
            await cmd_traverse(cmd)
            continue

        if cmd.startswith("/tunnels "):
            await cmd_tunnels(user_input[9:].strip())
            continue

        if cmd.startswith("/follow"):
            await cmd_follow(cmd)
            continue

        if cmd.startswith("/kg ") and not cmd.startswith("/kgstats"):
            await cmd_kg(user_input[4:])
            continue

        if cmd == "/enrich":
            await cmd_enrich()
            continue

        if cmd == "/kgstats":
            await cmd_kgstats()
            continue

        if cmd in ["sync", "/sync"]:
            await cmd_sync(chat_path)
            continue

        if cmd in ("/remind",) or cmd.startswith("/remind "):
            await cmd_remind(user_input)
            continue

        if cmd in ("/pdfs",) or cmd.startswith("/pdfs "):
            await cmd_pdfs(user_input[5:].strip())
            continue

        if cmd in ("/transkript",) or cmd.startswith("/transkript "):
            await cmd_transkript(user_input[11:].strip())
            continue

        if cmd in ("/yt",) or cmd.startswith("/yt "):
            await cmd_yt(user_input[3:].strip(), "video")
            continue

        if cmd in ("/ytaudio",) or cmd.startswith("/ytaudio "):
            await cmd_yt(user_input[8:].strip(), "audio")
            continue

        if cmd.startswith("/kgadd "):
            await cmd_kgadd(user_input[7:].strip())
            continue

        if cmd == "/settings":
            await cmd_settings(messages, data, chat_path)
            engine, model = get_current_ai()
            continue

        if cmd == "/del":
            if os.path.exists(chat_path):
                os.remove(chat_path)
                print(f"{C.GREEN}Чат удален. Возврат в меню...{C.END}")
                return "deleted"

        if cmd == "/new":
            return "new"

        if cmd == "/chats":
            return "chats"

        if cmd in ["~", "#ctx"]:
            summaries = data.get("summaries", [])
            existing_summary = summaries[-1] if summaries else ""
            if existing_summary and len(existing_summary.strip()) > 20:
                preview = (
                    existing_summary[:500] + "..."
                    if len(existing_summary) > 500
                    else existing_summary
                )
                print(f"\n{C.CYAN}Контекст чата:{C.END}\n{format_for_terminal(preview)}")
            else:
                print(f"{C.YELLOW}Саммари пусто.{C.END}")
            print()
            continue

        # --- Note prefixes ---
        prefix = next(
            (p for p in ["!!!", "!!", "!", "???", "??", "?"] if user_input.startswith(p)),
            "",
        )
        clean_q = user_input[len(prefix):].strip() if prefix else user_input

        if prefix == "!":
            await save_quick_note(clean_q)
            continue
        elif prefix and prefix in ("!!", "???"):
            last_ai = next(
                (m["content"] for m in reversed(messages) if m["role"] == "assistant"), ""
            )
            if last_ai:
                await save_extraction(prefix, clean_q, messages, last_ai, engine, model)
            continue
        elif prefix:
            continue

        # --- AI Query Processing ---
        await process_ai_query(clean_q, messages, data, chat_path, engine, model)

    return "quit"
