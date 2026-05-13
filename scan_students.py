#!/usr/bin/env python3
"""
Автосканер студенческих репозиториев организации PKO-LP.

Находит все репо по шаблону UP_06_DD-MM-YYYY_Name_Surname_32ISd,
скачивает parser.py каждого студента, запускает checker.py,
коммитит REVIEW.md обратно в репо студента.

Требует: переменную окружения GH_TOKEN с правами:
  - repo (read/write для студенческих репо)
  - read:org
"""

import os
import re
import sys
import json
import subprocess
import tempfile
import shutil
import datetime
from pathlib import Path

import urllib.request
import urllib.error

# ─────────────────────────────────────────────────────────────────────────────

ORG          = os.environ.get('ORG', 'PKO-LP')
TOKEN        = os.environ.get('GH_TOKEN', '')
REPO_PATTERN = re.compile(
    os.environ.get('REPO_PATTERN',
                   r'^UP_06_\d{2}-\d{2}-\d{4}_[A-Za-z][A-Za-z0-9-]*_[A-Za-z][A-Za-z0-9-]*_32ISd$'),
    re.IGNORECASE
)
CHECKER_PATH = Path(__file__).parent / 'checker.py'
RULES_PATH   = Path(__file__).parent / 'check_rules.json'
GRADES_PATH  = Path(__file__).parent / 'grades.json'

# ─────────────────────────────────────────────────────────────────────────────

def gh_api(path: str) -> list | dict:
    """Запрос к GitHub REST API с поддержкой пагинации."""
    results = []
    url = f'https://api.github.com{path}?per_page=100&page=1'
    while url:
        req = urllib.request.Request(url, headers={
            'Authorization': f'Bearer {TOKEN}',
            'Accept': 'application/vnd.github+json',
            'X-GitHub-Api-Version': '2022-11-28',
        })
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read())
                # Если это список — собираем постранично
                if isinstance(data, list):
                    results.extend(data)
                    link = resp.headers.get('Link', '')
                    # Ищем rel="next"
                    nxt = re.search(r'<([^>]+)>;\s*rel="next"', link)
                    url = nxt.group(1) if nxt else None
                else:
                    return data
        except urllib.error.HTTPError as e:
            print(f'GitHub API error {e.code}: {path}')
            sys.exit(1)
    return results


def get_student_repos() -> list[str]:
    """Возвращает список имён репо, подходящих под шаблон."""
    repos = gh_api(f'/orgs/{ORG}/repos')
    matched = [r['name'] for r in repos if REPO_PATTERN.match(r['name'])]
    print(f'Найдено репо студентов: {len(matched)}')
    for name in matched:
        print(f'  • {name}')
    return matched


# Регулярка для поиска Telegram bot token
_TOKEN_RE = re.compile(r'\d{9,12}:[A-Za-z0-9_-]{35,}')


def _check_token_leak(base: Path) -> str | None:
    """
    Ищет хардкод Telegram-токена рекурсивно во всех .py, .env, .txt, .cfg, .ini файлах.
    Возвращает имя файла где найден токен, или None.
    """
    patterns = ['**/*.py', '**/.env', '**/*.env', '**/config.py',
                '**/settings.py', '**/config.ini', '**/config.cfg',
                '**/*.txt', '**/*.cfg', '**/*.ini']
    checked = set()
    for pat in patterns:
        for f in base.glob(pat):
            if f in checked or not f.is_file():
                continue
            checked.add(f)
            # Пропускаем requirements.txt
            if f.name == 'requirements.txt':
                continue
            try:
                content = f.read_text(encoding='utf-8', errors='ignore')
            except Exception:
                continue
            if _TOKEN_RE.search(content):
                return f.relative_to(base).as_posix()
    return None


def check_bot_structure(tmpdir: str) -> tuple[str, str]:
    """
    Автоматическая проверка структуры бота в репо студента.
    Возвращает (статус_структуры, статус_безопасности).
    """
    base = Path(tmpdir)

    # Ищем файл бота рекурсивно
    bot_files = (list(base.glob('bot.py')) + list(base.glob('main.py'))
                 + list(base.glob('**/bot.py')) + list(base.glob('**/main.py'))
                 + list(base.glob('**/*bot*.py')))
    bot_files = [f for f in bot_files if f.is_file()]

    if not bot_files:
        return '⏳ Нет bot.py', '—'

    # Проверяем requirements.txt
    req_files = list(base.glob('requirements.txt')) + list(base.glob('**/requirements.txt'))
    if not req_files:
        struct = '❌ Нет requirements.txt'
    else:
        req_text = req_files[0].read_text(encoding='utf-8', errors='ignore').lower()
        tg_libs = ['aiogram', 'telebot', 'python-telegram-bot', 'telegram']
        if not any(lib in req_text for lib in tg_libs):
            struct = '❌ Нет TG-библиотеки'
        else:
            # Проверяем наличие /start
            all_code = '\n'.join(
                f.read_text(encoding='utf-8', errors='ignore')
                for f in base.glob('**/*.py') if f.is_file()
            )
            struct = '✅ Структура OK' if 'start' in all_code.lower() else '❌ Нет /start'

    # Проверяем хардкод токена (безопасность) — отдельно от структуры
    leaked_file = _check_token_leak(base)
    if leaked_file:
        security = f'🔑 Токен в {leaked_file}!'
    else:
        security = '✅ Токен OK'

    return struct, security


def load_grades() -> dict:
    """Загружает ручные отметки этапов из grades.json."""
    if not GRADES_PATH.exists():
        return {}
    with open(GRADES_PATH, encoding='utf-8') as f:
        data = json.load(f)
    return data.get('grades', {})


def process_repo(repo_name: str) -> dict | None:
    """Клонирует репо, запускает checker, коммитит REVIEW.md. Возвращает dict со статусом."""
    parts = repo_name.split('_')
    first_name = parts[3] if len(parts) >= 5 else '?'
    last_name  = parts[4] if len(parts) >= 5 else '?'

    def make_result(status: str, bot_struct: str = '—', bot_security: str = '—') -> dict:
        return {'repo': repo_name, 'first_name': first_name,
                'last_name': last_name, 'status': status,
                'bot_struct': bot_struct, 'bot_security': bot_security}

    repo_url = f'https://x-access-token:{TOKEN}@github.com/{ORG}/{repo_name}.git'

    with tempfile.TemporaryDirectory() as tmpdir:
        # Клонируем
        clone = subprocess.run(
            ['git', 'clone', '--depth=1', repo_url, tmpdir],
            capture_output=True, text=True
        )
        if clone.returncode != 0:
            print(f'[{repo_name}] Ошибка клонирования: {clone.stderr}')
            return make_result('❓ Ошибка')

        bot_struct, bot_security = check_bot_structure(tmpdir)

        parser_path = Path(tmpdir) / 'parser.py'
        if not parser_path.exists():
            print(f'[{repo_name}] parser.py не найден — пропускаем')
            return make_result('⏳ Нет parser.py', bot_struct, bot_security)

        # Копируем checker.py и check_rules.json в папку репо
        shutil.copy(CHECKER_PATH, Path(tmpdir) / 'checker.py')
        if RULES_PATH.exists():
            shutil.copy(RULES_PATH, Path(tmpdir) / 'check_rules.json')

        # Запускаем checker
        check_result = subprocess.run(
            [sys.executable, 'checker.py', 'parser.py'],
            capture_output=True, text=True, cwd=tmpdir
        )

        review_path = Path(tmpdir) / 'REVIEW.md'
        if not review_path.exists():
            print(f'[{repo_name}] REVIEW.md не создан — пропускаем')
            return make_result('❓ Ошибка', bot_struct)

        # Настраиваем git
        subprocess.run(['git', 'config', 'user.name', 'teacher-bot[bot]'],
                       cwd=tmpdir, capture_output=True)
        subprocess.run(['git', 'config', 'user.email',
                        '41898282+github-actions[bot]@users.noreply.github.com'],
                       cwd=tmpdir, capture_output=True)

        # Удаляем checker.py из репо студента (он там не нужен)
        (Path(tmpdir) / 'checker.py').unlink(missing_ok=True)

        errors_word = 'ошибки' if check_result.returncode != 0 else 'OK'
        status = '❌ Есть ошибки' if check_result.returncode != 0 else '✅ Сдано'

        # Если токен найден — добавляем предупреждение в REVIEW.md
        if leaked_file := _check_token_leak(Path(tmpdir)):
            security_warning = (
                '\n\n---\n'
                '## ⚠️ КРИТИЧЕСКАЯ ОШИБКА БЕЗОПАСНОСТИ\n\n'
                f'**В файле `{leaked_file}` обнаружен хардкод Telegram bot token!**\n\n'
                '❌ Это означает, что твой токен виден всем кто смотрит репо.\n'
                'Злоумышленник может захватить управление ботом.\n\n'
                '**Как исправить:**\n'
                '1. Немедленно отзови токен у @BotFather (`/revoke`)\n'
                '2. Получи новый токен\n'
                '3. Вынеси токен в переменную окружения: `os.environ["BOT_TOKEN"]`\n'
                '   или в файл `.env` (добавь `.env` в `.gitignore`)\n'
            )
            review_text = review_path.read_text(encoding='utf-8') + security_warning
            review_path.write_text(review_text, encoding='utf-8')

        # Коммитим REVIEW.md
        subprocess.run(['git', 'add', 'REVIEW.md'], cwd=tmpdir, capture_output=True)
        diff = subprocess.run(
            ['git', 'diff', '--cached', '--quiet'],
            cwd=tmpdir, capture_output=True
        )
        if diff.returncode == 0:
            print(f'[{repo_name}] REVIEW.md не изменился')
            return make_result(status)

        commit_msg = f'auto-review: {errors_word} в parser.py [skip ci]'
        subprocess.run(['git', 'commit', '-m', commit_msg],
                       cwd=tmpdir, capture_output=True)
        push = subprocess.run(['git', 'push'], cwd=tmpdir, capture_output=True, text=True)

        if push.returncode == 0:
            print(f'[{repo_name}] ✅ REVIEW.md обновлён ({errors_word})')
        else:
            print(f'[{repo_name}] ❌ Ошибка push: {push.stderr}')

        return make_result(status, bot_struct, bot_security)


# ─────────────────────────────────────────────────────────────────────────────

def update_readme_table(results: list[dict]) -> None:
    """Обновляет таблицы прогресса студентов в README.md основного репо."""
    readme_path = Path(__file__).parent / 'README.md'
    if not readme_path.exists():
        return

    content = readme_path.read_text(encoding='utf-8')
    grades  = load_grades()
    now     = datetime.datetime.utcnow().strftime('%d.%m.%Y %H:%M UTC')

    def grade_mark(repo: str, stage: str) -> str:
        g = grades.get(repo, {})
        return '✅' if g.get(stage) else '⏳'

    sorted_results = sorted(results, key=lambda x: x['last_name'])

    # ── Таблица 1: парсер ────────────────────────────────────────────────────
    parser_rows = []
    for r in sorted_results:
        repo_url = f'https://github.com/{ORG}/{r["repo"]}'
        parser_rows.append(
            f'| {r["first_name"]} {r["last_name"]} '
            f'| [{r["repo"]}]({repo_url}) '
            f'| {r["status"]} |'
        )

    parser_table = (
        '| Студент | Репозиторий | Статус |\n'
        '|---------|-------------|--------|\n'
        + ('\n'.join(parser_rows) + '\n' if parser_rows else '')
        + f'\n_Обновлено: {now}_'
    )
    new_parser_section = (
        '<!-- STUDENTS_TABLE_START -->\n'
        + parser_table
        + '\n<!-- STUDENTS_TABLE_END -->'
    )
    content = re.sub(
        r'<!-- STUDENTS_TABLE_START -->.*?<!-- STUDENTS_TABLE_END -->',
        new_parser_section, content, flags=re.DOTALL
    )

    # ── Таблица 2: этапы бота ───────────────────────────────────────────────
    bot_rows = []
    for r in sorted_results:
        repo_url = f'https://github.com/{ORG}/{r["repo"]}'
        bot_rows.append(
            f'| {r["first_name"]} {r["last_name"]} '
            f'| [{r["repo"]}]({repo_url}) '
            f'| {r.get("bot_struct", "—")} '
            f'| {r.get("bot_security", "—")} '
            f'| {grade_mark(r["repo"], "demo1")} '
            f'| {grade_mark(r["repo"], "demo2")} '
            f'| {grade_mark(r["repo"], "demo3")} |'
        )

    bot_table = (
        '| Студент | Репозиторий | Структура | 🔒 Безопасность | Этап 1 🚀 | Этап 2 📅 | Этап 3 💾 |\n'
        '|---------|-------------|-----------|-----------------|-----------|-----------|----------|\n'
        + ('\n'.join(bot_rows) + '\n' if bot_rows else '')
        + f'\n_Обновлено: {now}_'
    )
    new_bot_section = (
        '<!-- BOT_TABLE_START -->\n'
        + bot_table
        + '\n<!-- BOT_TABLE_END -->'
    )

    if '<!-- BOT_TABLE_START -->' in content:
        content = re.sub(
            r'<!-- BOT_TABLE_START -->.*?<!-- BOT_TABLE_END -->',
            new_bot_section, content, flags=re.DOTALL
        )
    else:
        # Вставляем перед таблицей парсера
        content = content.replace(
            '## Прогресс — Парсер',
            '## Прогресс — Telegram-бот\n\n' + new_bot_section + '\n\n---\n\n## Прогресс — Парсер'
        )

    readme_path.write_text(content, encoding='utf-8')
    print('README.md: таблицы обновлены.')


def main() -> None:
    if not TOKEN:
        print('Ошибка: переменная GH_TOKEN не задана')
        sys.exit(1)

    repos = get_student_repos()
    if not repos:
        print('Репозиториев студентов не найдено.')
        update_readme_table([])
        return

    results = []
    for repo in repos:
        r = process_repo(repo)
        if r:
            results.append(r)

    update_readme_table(results)
    print('\nСканирование завершено.')


if __name__ == '__main__':
    main()
