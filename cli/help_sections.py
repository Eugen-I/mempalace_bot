"""Help sections for CLI - extracted from cli_ask.py"""

from cli.utils import C

HELP_SECTIONS = {
    "1": {
        "title": "📝 Запись и библиотека",
        "items": [
            ("! текст", "Быстрая заметка в my_notes"),
            ("!!", "Сохранить последний ответ ИИ в Insights"),
            ("???", "Сохранить в Research"),
            ("/transkript", "Список транскриптов YouTube"),
            ("/transkript N", "Прочитать транскрипт по номеру"),
        ],
    },
    "2": {
        "title": "💬 Управление чатами",
        "items": [
            ("/history", "Показать историю текущего чата"),
            ("/export", "Экспорт чата в .md"),
            ("~ / #ctx", "Показать последнее саммари"),
            ("/new", "Новый чат"),
            ("/del", "Удалить текущий чат"),
            ("/chats", "Вернуться в меню чатов"),
        ],
    },
    "3": {
        "title": "🔍 Поиск и синхронизация",
        "items": [
            ("/search <запрос>", "Поиск по всей базе MemPalace"),
            ("/search --wing dreams ...", "Поиск по конкретному крылу"),
            ("sync", "Синхронизировать чат с MemPalace"),
            ("/photos", "Список фото"),
            ("/analyze_photo", "Анализ фото ИИ"),
        ],
    },
    "4": {
        "title": "🎬 Медиа (YouTube, PDF, напоминания)",
        "items": [
            ("/yt <url> [кач]", "Скачать видео с YouTube"),
            ("/ytaudio <url>", "Скачать аудио + транскрипция"),
            ("/pdfs [N]", "Список/просмотр PDF"),
            ("/remind <текст>", "Создать напоминание"),
        ],
    },
    "5": {
        "title": "🏰 Дворец знаний",
        "items": [
            ("/palace", "Список команд дворца"),
            ("/status", "Статистика MemPalace"),
            ("/wings", "Список всех крыльев"),
            ("/rooms [крыло]", "Комнаты крыла"),
            ("/taxonomy", "Полная таксономия"),
            ("/graph", "Статистика графа"),
            ("/traverse <комната> [шаги]", "Обход графа"),
            ("/tunnels", "Туннели между крыльями"),
            ("/follow <крыло> <комната>", "Пройти туннели из комнаты"),
            ("/kg <сущность>", "Поиск в графе знаний"),
            ("/kgadd суб пред об", "Добавить факт"),
            ("/kgstats", "Статистика KG"),
            ("/enrich", "Enrichment заметок → KG"),
            ("/mcp", "Инструкция MCP"),
            ("/wakeup", "Загрузить дворец в контекст"),
            ("/repair", "Перестроить индекс"),
            ("/compact", "Сжать БД"),
            ("/compress", "Сжать текст"),
        ],
    },
    "6": {
        "title": "⚙️ Системные",
        "items": [
            ("/settings", "Сменить модель ИИ"),
            ("Звук", "Вкл/Выкл озвучку"),
            ("Звук-150", "Скорость голоса (100-300)"),
            ("q / й / Ctrl+C", "Выход с сохранением"),
        ],
    },
}


def show_help():
    """Показать главное меню справки"""
    print(f"{C.CYAN}==========================================================")
    print("    🦾 MemPalace CLI | Справка")
    print(f"{'=' * 58}{C.END}")
    for key, sec in HELP_SECTIONS.items():
        print(f"  {C.YELLOW}{key}. {sec['title']}{C.END}")
    print(f"\n  {C.PURPLE}0) {C.END}Вся справка разом")
    print(f"  {C.YELLOW}h) {C.END}Это меню")
    print(f"  {'=' * 58}{C.END}")
    print("  Введите номер раздела для подробностей.")


def show_section(key: str):
    """Показать конкретный раздел справки"""
    sec = HELP_SECTIONS.get(key)
    if not sec:
        return
    print(f"\n{C.YELLOW}--- {sec['title']} ---{C.END}")
    for cmd, desc in sec["items"]:
        print(f"  {C.GREEN}{cmd}{C.END}")
        print(f"    {desc}")


def show_all_help():
    """Показать всю справку"""
    for key in sorted(HELP_SECTIONS):
        show_section(key)
    print()
