#!/usr/bin/env python3
"""Проверка staged-файлов и исходящих коммитов:
Секреты, ключи, персональные данные и чувствительные файлы не должны попасть в репозиторий.

Используется как pre-commit и pre-push hook.
"""
import re
import subprocess
import sys
from pathlib import Path

FORBIDDEN_FILENAMES = [
    r"\.sqlite(-wal|-shm)?$",
    r"\.db$",
    r"\.env(\..+)?$",  # blocks .env, .env.local, etc. (except .env.example)
    r"\.pem$",
    r"\.p12$",
    r"\.key$",
    r"\.log$",
    r"bot\.pid$",
    r"nohup\.out$",
    r"palace_graph_data\.json$",
    r"palace-graph\.html$",
    r"^my_notes/",
    r"^chats/",
    r"^Takeout/",
    r"^exports/",
    r"_behave_media/?$",
    r"_behave_tr/?$",
]

STATIC_SECRET_PATTERNS = [
    (r"(?<![0-9])([0-9]{8,11}:[A-Za-z0-9_-]{35})(?![A-Za-z0-9_-])", "Telegram Bot Token"),
    (r"bot([0-9]{8,11}[A-Za-z0-9_-]{35})", "Telegram Bot Token (bot prefix)"),
    (r"(?<![A-Za-z0-9])(AIza[0-9A-Za-z\-_]{35})(?![A-Za-z0-9])", "Google / Gemini API Key"),
    (r"(?<![A-Za-z0-9])(sk-[A-Za-z0-9_\-]{20,})(?![A-Za-z0-9])", "OpenAI API Key"),
    (r"(?<![A-Za-z0-9])(sk-ant-[A-Za-z0-9_\-]{20,})(?![A-Za-z0-9])", "Anthropic API Key"),
    (r"(?<![A-Za-z0-9])(tvly-[A-Za-z0-9_\-]{20,})(?![A-Za-z0-9])", "Tavily API Key"),
    (r"(?<![A-Za-z0-9])(gh[pousr]_[A-Za-z0-9]{36,}|github_pat_[A-Za-z0-9_]{30,})", "GitHub Token"),
    (r"-----BEGIN [A-Z0-9_\- ]+PRIVATE KEY", "Private Key"),
    (r"(?i)(api_id|app_id)\s*[:=]\s*([0-9]{5,10})", "Telegram App ID / API ID"),
    (r"(?i)(api_hash|app_hash)\s*[:=]\s*['\"]([a-f0-9]{32})['\"]", "Telegram API Hash"),
    (r"(?i)(ADMIN_ID|ALLOWED_USERS)\s*[:=]\s*['\"]?([0-9]{6,})['\"]?", "Telegram User ID"),
    (r"(?i)(password|passwd|client_secret)\s*[:=]\s*['\"]([^'\"]{6,})['\"]",
     "Hardcoded Password/Secret"),
    (r"(?i)bearer\s+[A-Za-z0-9._-]{25,}", "Authorization Bearer Token"),
]

ALLOWLIST = [
    "AIzaSyDummyKeyForTestingPurposes12345",
    "sk-dummy-test-key-for-testing-purposes",
    "dummy_hash",
    "dummy_token",
    "your_telegram_bot_token",
    "your_gemini_api_key",
    "your_openai_api_key",
    "0000000000:AAFgDummyTokenForTesting12345678",
    "123456789:ABCdefGhIJKlmNoPQRsTUVwxyZ_1234567",
    "1234567890:AA",
    "ALLOWED_IDS",
    "example.com",
    "test@example.com",
    "foo@bar.com",
]

MAX_FILE_SIZE = 5 * 1024 * 1024


def load_local_env_secrets() -> dict[str, str]:
    """Загружает реальные секреты из локального .env для гарантированной блокировки утечки."""
    secrets = {}
    repo_root = Path(__file__).resolve().parent.parent
    for env_name in [".env", ".env.local"]:
        env_file = repo_root / env_name
        if env_file.is_file():
            try:
                for line in env_file.read_text(encoding="utf-8", errors="replace").splitlines():
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        k = k.strip()
                        v = v.strip().strip("'\"")
                        if len(v) >= 5 and k not in (
                            "MEMPALACE_DATA_DIR", "GARMIN_DB_PATH", "GARMIN_COACH_OUTPUT_PATH"
                        ):
                            secrets[k] = v
            except Exception:
                pass
    return secrets


def get_files_to_check() -> list[str]:
    repo_root = str(Path(__file__).resolve().parent.parent)
    is_pre_push = "--pre-push" in sys.argv
    if is_pre_push:
        # При pre-push проверяем все добавленные/изменённые файлы относительно origin
        res = subprocess.run(
            ["git", "diff", "--name-only", "--diff-filter=d", "@{push}..HEAD"],
            cwd=repo_root, capture_output=True, text=True, errors="replace"
        )
        if res.returncode != 0:
            res = subprocess.run(
                ["git", "diff", "--name-only", "--diff-filter=d", "origin/main..HEAD"],
                cwd=repo_root, capture_output=True, text=True, errors="replace"
            )
        return [f.strip() for f in res.stdout.splitlines() if f.strip()]
    else:
        # При pre-commit проверяем добавленные/изменённые staged файлы
        out = subprocess.run(
            ["git", "diff", "--cached", "--name-only", "--diff-filter=d", "-z"],
            cwd=repo_root, capture_output=True, text=True, errors="replace"
        )
        return [f for f in out.stdout.split("\0") if f]


def check_filenames(files: list[str]) -> list[str]:
    violations = []
    for f in files:
        if f.endswith(".example"):
            continue
        for pat in FORBIDDEN_FILENAMES:
            if re.search(pat, f, re.IGNORECASE):
                violations.append(f"запрещённый файл в репозитории: {f}")
                break
    return violations


def check_contents(files: list[str], dynamic_secrets: dict[str, str]) -> list[str]:
    violations = []
    repo_root = Path(__file__).resolve().parent.parent

    for rel_path in files:
        f_path = repo_root / rel_path
        if not f_path.is_file():
            continue
        try:
            size = f_path.stat().st_size
        except OSError:
            continue

        if size > MAX_FILE_SIZE:
            violations.append(f"файл слишком большой ({size // (1024 * 1024)} MB): {rel_path}")
            continue
        if size > 2 * 1024 * 1024:
            continue

        try:
            content = f_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue

        # 1. Проверка на точное совпадение с боевыми значениями из .env
        for secret_name, secret_val in dynamic_secrets.items():
            if secret_val in content:
                violations.append(
                    f"боевое значение {secret_name} из локального .env обнаружено в {rel_path}"
                )

        # 2. Проверка по статическим регулярным выражениям
        for pat_str, pat_desc in STATIC_SECRET_PATTERNS:
            rx = re.compile(pat_str)
            for m in rx.finditer(content):
                val = m.group(0)
                if any(allowed in val for allowed in ALLOWLIST):
                    continue
                violations.append(f"потенциальный секрет ({pat_desc}) в {rel_path}")
                break

    return violations


def main():
    files = get_files_to_check()
    if not files:
        return 0

    dynamic_secrets = load_local_env_secrets()
    violations = check_filenames(files) + check_contents(files, dynamic_secrets)
    if violations:
        print("\n⛔ [SECURITY GUARD] Заблокировано! Обнаружены конфиденциальные данные:")
        for v in sorted(set(violations)):
            print(f"  ❌ {v}")
        print("\nУдалите секреты или личные файлы перед коммитом/пушем.\n")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
