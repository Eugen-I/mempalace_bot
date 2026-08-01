
import logging
import os
import sys

# Hide INFO/WARNING from all modules, keep only ERROR
logging.basicConfig(level=logging.ERROR, format="%(levelname)s: %(message)s")
logger = logging.getLogger("CLI")
logger.setLevel(logging.INFO)

# 📂 Base paths
BASE_DIR = os.path.expanduser("~/Documents/mempalace")
BOT_DIR = os.path.expanduser("~/Documents/mempalace_bot")
VENV_DIR = os.path.join(BASE_DIR, "venv")
VENV_PYTHON = os.path.join(VENV_DIR, "bin", "python3")

# 🔄 AUTO-ACTIVATE VENV
if sys.executable != VENV_PYTHON and os.path.exists(VENV_PYTHON):
    os.environ["VIRTUAL_ENV"] = VENV_DIR
    os.environ["PATH"] = (
        os.path.join(VENV_DIR, "bin") + os.pathsep + os.environ.get("PATH", "")
    )
    os.execv(VENV_PYTHON, [VENV_PYTHON] + sys.argv)

sys.path.insert(0, BOT_DIR)
sys.path.insert(0, BASE_DIR)

import asyncio
from config import CHATS_DIR
from cli import list_chats, save_chat, chat_loop, create_new_chat
from cli.utils import C, format_for_terminal
from services.ai_engine import get_current_ai
from prompt_toolkit import PromptSession
from prompt_toolkit.history import FileHistory
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.formatted_text import HTML


async def main():
    """Main CLI entry point"""
    # History file
    hist_file = os.path.join(os.path.expanduser("~"), ".mempalace_cli_history")
    
    # Key bindings
    bindings = KeyBindings()
    
    @bindings.add('c-c')
    def _(event):
        event.app.exit(result=KeyboardInterrupt)
    
    @bindings.add('c-d')
    def _(event):
        event.app.exit(result=KeyboardInterrupt)
    
    # Prompt session with history
    session = PromptSession(
        history=FileHistory(hist_file),
        key_bindings=bindings,
    )
    
    while True:
        chats = list_chats()
        
        engine, model = get_current_ai()
        print(f"\n{C.CYAN}=========================================================={C.END}")
        print(f"{C.CYAN}    🦾 MemPalace CLI — Меню чатов{C.END}")
        print(f"{C.GREEN}    🤖 Модель: {model} ({engine}){C.END}")
        print(f"{C.CYAN}=========================================================={C.END}")
        
        if not chats:
            print(f"{C.YELLOW}📁 Чатов нет. Создайте новый.{C.END}")
        else:
            print(f"{C.GREEN}Доступные чаты:{C.END}")
            for i, chat in enumerate(chats, 1):
                display = chat.replace("ch_", "").replace(".json", "").replace("_", " ")
                print(f"  {C.YELLOW}{i}.{C.END} {display}")
        
        print(f"\n{C.CYAN}Команды:{C.END}")
        print(f"  {C.GREEN}N / new{C.END}     — Новый чат")
        print(f"  {C.GREEN}<номер>{C.END}      — Открыть чат")
        print(f"  {C.GREEN}D <номер>{C.END}    — Удалить чат")
        print(f"  {C.GREEN}Q / q{C.END}        — Выход")
        print(f"{C.CYAN}=========================================================={C.END}")
        
        try:
            choice = await session.prompt_async(
                HTML(f'<ansiyellow>Выбор: </ansiyellow>'),
            )
            choice = choice.strip().lower()
        except (EOFError, KeyboardInterrupt):
            print(f"\n{C.RED}👋 Выход.{C.END}")
            break
        
        if choice in ['q', 'quit', 'й', 'exit', 'выход']:
            break
        
        if choice in ['n', 'new', 'н', 'новый']:
            chat_path = create_new_chat()
        elif choice.startswith('d '):
            try:
                idx = int(choice.split()[1]) - 1
                if 0 <= idx < len(chats):
                    chat_path = os.path.join(CHATS_DIR, chats[idx])
                    os.remove(chat_path)
                    print(f"🗑️ Чат удален: {chats[idx]}")
                    continue
            except (ValueError, IndexError):
                pass
            print("❌ Неверный номер")
            continue
        elif choice.isdigit():
            idx = int(choice) - 1
            if 0 <= idx < len(chats):
                chat_path = os.path.join(CHATS_DIR, chats[idx])
            else:
                print("❌ Неверный номер")
                continue
        else:
            print("❌ Неверный ввод")
            continue
        
        # Run chat loop
        result = await chat_loop(chat_path, session)
        if result == "quit":
            break
        elif result in ("deleted", "new", "chats"):
            continue
    
    print(f"{C.GREEN}👋 До свидания!{C.END}")


if __name__ == "__main__":
    asyncio.run(main())