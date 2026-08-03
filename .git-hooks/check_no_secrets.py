#!/usr/bin/env python3
"""Проверка staged-файлов: секреты и чувствительные файлы не должны попасть в коммит.

Используется как pre-commit hook (см. .pre-commit-config.yaml).
Возвращает 1 и список нарушений, если найдено что-то запрещённое.
"""
import os
import re
import subprocess
import sys

FORBIDDEN_PATTERNS = [
    r"\.sqlite(-wal|-shm)?$",
    r"\.db$",
    r"\.env$",
    r"\.pem$",
    r"\.p12$",
    r"\.key$",
    r"\.log$",
    r"bot\.pid$",
    r"nohup\.out$",
    r"_behave_media/?$",
    r"_behave_tr/?$",
]

SECRET_PATTERNS = [
    (r"TELEGRAM_BOT_TOKEN\s*=\s*[0-9]{8,}", "Telegram bot token"),
    (r"GEMINI_API_KEY\s*=\s*[A-Za-z0-9_-]{20,}", "Gemini API key"),
    (r"OPENAI_API_KEY\s*=\s*sk-[A-Za-z0-9]{10,}", "OpenAI API key"),
    (r"AIza[A-Za-z0-9_-]{30,}", "Google API key"),
    (r"sk-[A-Za-z0-9]{20,}", "OpenAI-style key"),
    (r"-----BEGIN (RSA|OPENSSH|EC|DSA|PGP) PRIVATE KEY", "private key"),
    (r"password\s*[=:]\s*[^\"'\s]{6,}", "password"),
    (r"Bearer\s+[A-Za-z0-9._-]{20,}", "Bearer token"),
]

MAX_FILE_SIZE = 5 * 1024 * 1024


def get_staged_files():
    out = subprocess.run(
        ["git", "diff", "--cached", "--name-only", "-z"],
        capture_output=True, text=True,
    )
    return [f for f in out.stdout.split("\0") if f]


def check_filenames(files):
    violations = []
    for f in files:
        for pat in FORBIDDEN_PATTERNS:
            if re.search(pat, f, re.IGNORECASE):
                violations.append(f"запрещённое имя файла: {f}")
                break
    return violations


def check_contents(files):
    violations = []
    for f in files:
        try:
            size = os.path.getsize(f)
        except OSError:
            continue
        if size > MAX_FILE_SIZE:
            violations.append(f"файл слишком большой ({size // 1024 // 1024} MB): {f}")
            continue
        if size > 2 * 1024 * 1024:
            continue
        try:
            with open(f, "r", encoding="utf-8", errors="replace") as fh:
                content = fh.read()
        except OSError:
            continue
        for pat, name in SECRET_PATTERNS:
            if re.search(pat, content):
                violations.append(f"секрет в {f}: {name}")
    return violations


def main():
    files = get_staged_files()
    if not files:
        return 0
    violations = check_filenames(files) + check_contents(files)
    if violations:
        print("⛔ Коммит заблокирован. Найдено:")
        for v in sorted(set(violations)):
            print(f"  - {v}")
        print("Уберите секреты и чувствительные файлы перед коммитом.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
