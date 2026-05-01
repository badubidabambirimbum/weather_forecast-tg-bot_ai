"""Политика Cursor hook для проверок git commit/push.

Хук работает до выполнения shell-команды и блокирует потенциально рискованные
действия (секреты в staged, невалидный commit message, падающие тесты).
"""

from __future__ import annotations

import json
import re
import shlex
import subprocess
import sys
import os
from typing import Any

CONVENTIONAL_RE = re.compile(
    r"^(feat|fix|docs|style|refactor|test|chore|ci|build|perf|revert)(\([a-zA-Z0-9_.-]+\))?: .+$"
)
FORBIDDEN_FILE_RE = re.compile(r"(^|/)(\.env(\..+)?|.*\.pyc|__pycache__/.*)$")
ALLOWED_COMMIT_TYPES = "feat, fix, docs, style, refactor, test, chore, ci, build, perf, revert"
README_FILE = "README.md"
README_RELEVANT_PREFIXES = ("backend/", "bot/", "miniapp/")


def _respond(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=True))


def _allow() -> None:
    _respond({"permission": "allow"})


def _deny(message: str) -> None:
    _respond({"permission": "deny", "user_message": message, "agent_message": message})


def _run(command: list[str]) -> subprocess.CompletedProcess[str]:
    """Безопасно запускает подпроцесс и возвращает результат."""
    try:
        return subprocess.run(command, capture_output=True, text=True, check=False)
    except OSError as exc:
        # Возвращаем управляемую ошибку, чтобы пользователь видел понятную причину блокировки.
        raise RuntimeError(f"Не удалось запустить команду: {' '.join(command)} ({exc})") from exc


def _get_staged_files() -> list[str]:
    proc = _run(["git", "diff", "--cached", "--name-only", "--diff-filter=ACMR"])
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or "failed to list staged files")
    return [line.strip() for line in proc.stdout.splitlines() if line.strip()]


def _get_diff_files(diff_range: str) -> list[str]:
    """Возвращает список измененных файлов для заданного git diff range."""
    proc = _run(["git", "diff", "--name-only", diff_range])
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or f"failed to list files for range: {diff_range}")
    return [line.strip() for line in proc.stdout.splitlines() if line.strip()]


def _is_readme_sync_required(files: list[str]) -> bool:
    """Проверяет, затронуты ли части проекта, требующие актуализации README."""
    normalized = [f.replace("\\", "/") for f in files]
    return any(path.startswith(README_RELEVANT_PREFIXES) for path in normalized)


def _has_readme_update(files: list[str]) -> bool:
    """Проверяет, присутствует ли README.md среди измененных файлов."""
    normalized = [f.replace("\\", "/") for f in files]
    return README_FILE in normalized


def _validate_commit_message(tokens: list[str]) -> tuple[bool, str]:
    """Проверяет commit message из аргументов git commit.

    Ограничение: проверяем только случаи, когда сообщение передано через
    -m/--message/--message=... . Если сообщение задается через редактор, на этом
    этапе оно недоступно в beforeShellExecution.
    """
    for idx, token in enumerate(tokens):
        if token in ("-m", "--message"):
            if idx + 1 >= len(tokens):
                return False, "Команда git commit: после -m/--message нет текста сообщения."
            message = tokens[idx + 1].strip()
            if not CONVENTIONAL_RE.match(message):
                return (
                    False,
                    "Неверный формат commit message. Используй: <type>(optional-scope): <description>.",
                )
            return True, ""
        if token.startswith("--message="):
            message = token.split("=", 1)[1].strip()
            if not CONVENTIONAL_RE.match(message):
                return (
                    False,
                    "Неверный формат commit message. Используй: <type>(optional-scope): <description>.",
                )
            return True, ""
    return True, ""


def _handle_git_commit(tokens: list[str]) -> None:
    staged_files = _get_staged_files()
    for file_name in staged_files:
        normalized = file_name.replace("\\", "/")
        if normalized == ".env.example":
            continue
        if FORBIDDEN_FILE_RE.search(normalized):
            _deny(f"Коммит заблокирован: запрещенный файл в staged: {file_name}")
            return

    is_valid, message = _validate_commit_message(tokens)
    if not is_valid:
        _deny(message + f" Допустимые типы: {ALLOWED_COMMIT_TYPES}.")
        return

    # Можно явно отключить проверку в редких случаях через переменную окружения.
    if os.getenv("SKIP_README_SYNC_CHECK", "").strip() != "1":
        if _is_readme_sync_required(staged_files) and not _has_readme_update(staged_files):
            _deny(
                "Коммит заблокирован: изменены backend/bot/miniapp, но не обновлен README.md.\n"
                "Обнови README.md или задай SKIP_README_SYNC_CHECK=1 для осознанного пропуска."
            )
            return

    tests = _run([sys.executable, "-m", "pytest", "tests/test_api.py", "-q"])
    if tests.returncode != 0:
        details = (tests.stdout + "\n" + tests.stderr).strip()
        _deny("pre-commit проверка не пройдена (tests/test_api.py).\n" + details[-3000:])
        return

    _allow()


def _handle_git_push() -> None:
    if os.getenv("SKIP_README_SYNC_CHECK", "").strip() != "1":
        ahead_files = _get_diff_files("@{u}..HEAD")
        if _is_readme_sync_required(ahead_files) and not _has_readme_update(ahead_files):
            _deny(
                "Push заблокирован: в коммитах для отправки есть изменения backend/bot/miniapp "
                "без обновления README.md.\nОбнови README.md или задай SKIP_README_SYNC_CHECK=1."
            )
            return

    tests = _run([sys.executable, "-m", "pytest", "-q"])
    if tests.returncode != 0:
        details = (tests.stdout + "\n" + tests.stderr).strip()
        _deny("pre-push проверка не пройдена (pytest).\n" + details[-3000:])
        return
    _allow()


def _fail_safe(message: str) -> None:
    """Блокирует действие при внутренней ошибке hook с понятным сообщением."""
    _deny("Внутренняя ошибка git policy hook. Команда заблокирована.\n" + message)


def main() -> int:
    try:
        try:
            payload = json.loads(sys.stdin.read() or "{}")
        except json.JSONDecodeError:
            _allow()
            return 0

        command = str(payload.get("command", "")).strip()
        if not command:
            _allow()
            return 0

        try:
            tokens = shlex.split(command, posix=False)
        except ValueError:
            _allow()
            return 0

        lower = [t.lower() for t in tokens]
        if len(lower) < 2 or lower[0] != "git":
            _allow()
            return 0

        if lower[1] == "commit":
            _handle_git_commit(tokens)
            return 0
        if lower[1] == "push":
            _handle_git_push()
            return 0

        _allow()
        return 0
    except Exception as exc:  # noqa: BLE001
        _fail_safe(str(exc))
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
