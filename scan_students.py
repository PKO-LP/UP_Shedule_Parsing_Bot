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
# Загружаем .env если есть (локальный запуск без ручного export)
_env_file = Path(__file__).parent / '.env'
if _env_file.exists():
    for _line in _env_file.read_text(encoding='utf-8').splitlines():
        _line = _line.strip()
        if _line and not _line.startswith('#') and '=' in _line:
            _k, _v = _line.split('=', 1)
            os.environ[_k.strip()] = _v.strip()

ORG          = os.environ.get('ORG', 'PKO-LP')
TOKEN        = os.environ.get('GH_TOKEN', '')
REPO_PATTERN = re.compile(
    os.environ.get('REPO_PATTERN',
                   r'^UP_06_\d{2}-\d{2}-\d{4}_[A-Za-z][A-Za-z0-9-]*_[A-Za-z][A-Za-z0-9-]*_32ISd$'),
    re.IGNORECASE
)
CHECKER_PATH   = Path(__file__).parent / 'checker.py'
RULES_PATH     = Path(__file__).parent / 'check_rules.json'
CHECK_BOT_PATH = Path(__file__).parent / 'assets' / 'check_bot.py'
GRADES_PATH    = Path(__file__).parent / 'grades.json'
SNAPSHOT_PATH  = Path(__file__).parent / 'stages_snapshot.json'

_STAGE_KEYS   = ('demo1', 'demo2', 'demo3')
_STAGE_LABELS = ('🚀 Этап 1', '📅 Этап 2', '💾 Этап 3')

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
    Работает с любым именем файла бота (bot.py / main.py / app.py / etc.)
    """
    base     = Path(tmpdir)
    all_py   = [f for f in base.glob('**/*.py') if f.is_file()]
    all_code = '\n'.join(f.read_text(encoding='utf-8', errors='ignore') for f in all_py)
    code_low = all_code.lower()

    TG_LIBS = ['aiogram', 'telebot', 'python-telegram-bot', 'telegram']

    # Ищем любой .py с импортом TG-библиотеки — это и есть бот-файл
    tg_file = None
    for f in all_py:
        text = f.read_text(encoding='utf-8', errors='ignore').lower()
        if any(lib in text for lib in TG_LIBS):
            tg_file = f
            break

    if tg_file is None:
        req_files = list(base.glob('requirements.txt')) + list(base.glob('**/requirements.txt'))
        if not req_files:
            return '⏳ Нет бот-файла', '—'
        req_text = req_files[0].read_text(encoding='utf-8', errors='ignore').lower()
        if not any(lib in req_text for lib in TG_LIBS):
            return '⏳ Нет бот-файла', '—'
        return '❌ Нет TG-импорта', '—'

    # TG-файл найден — стандартные проверки
    req_files = list(base.glob('requirements.txt')) + list(base.glob('**/requirements.txt'))
    if not req_files:
        struct = '❌ Нет requirements.txt'
    elif not any(lib in req_files[0].read_text(encoding='utf-8', errors='ignore').lower()
                 for lib in TG_LIBS):
        struct = '❌ Нет TG-библиотеки'
    elif 'start' not in code_low:
        struct = '❌ Нет /start'
    else:
        struct = '✅ OK'

    leaked_file = _check_token_leak(base)
    security = f'🔑 Токен в коде!' if leaked_file else '✅ OK'

    return struct, security


def auto_detect_stages(tmpdir: str) -> dict[str, bool]:
    """
    Статический анализ репо студента — автодетект выполненных этапов бота.

    Этап 1 (demo1): bot.py есть + TG-библиотека + /start обработчик
    Этап 2 (demo2): есть обращение к API расписания или подключён parser.py
    Этап 3 (demo3): есть кеширование (json.dump/load + файл/переменная кеша)
    """
    base = Path(tmpdir)
    all_py = [f for f in base.glob('**/*.py') if f.is_file()]
    all_code = '\n'.join(
        f.read_text(encoding='utf-8', errors='ignore') for f in all_py
    )
    code_lower = all_code.lower()

    # ── Этап 1: бот запущен, отвечает на /start ──────────────────────────────
    # Любой .py с TG-импортом считается бот-файлом (bot.py / main.py / app.py / etc.)
    tg_libs = ['aiogram', 'telebot', 'python-telegram-bot', 'telegram']
    has_tg_in_code = any(
        lib in f.read_text(encoding='utf-8', errors='ignore').lower()
        for f in all_py for lib in tg_libs
    )
    req_files = list(base.glob('requirements.txt')) + list(base.glob('**/requirements.txt'))
    has_tg_in_req = bool(req_files) and any(
        lib in req_files[0].read_text(encoding='utf-8', errors='ignore').lower()
        for lib in tg_libs
    )
    has_tg_lib = has_tg_in_code or has_tg_in_req
    has_start  = 'start' in code_lower
    demo1 = has_tg_lib and has_start

    # ── Этап 2: бот выводит расписание ───────────────────────────────────────
    schedule_keywords = [
        'spo-13', 'raspisanie', 'расписание', 'schedule',
        'folder_and_file', 'parse_schedule', 'parser.py',
        'import parser', 'from parser'
    ]
    demo2 = demo1 and any(kw in code_lower for kw in schedule_keywords)

    # ── Этап 3: кеширование работает ─────────────────────────────────────────
    cache_keywords = [
        'json.dump', 'json.load', 'cache', 'кеш',
        'is_new_file', 'cache_file', 'cache_index'
    ]
    demo3 = demo2 and any(kw in code_lower for kw in cache_keywords)

    return {'demo1': demo1, 'demo2': demo2, 'demo3': demo3}


def load_grades() -> dict:
    """Загружает ручные отметки этапов из grades.json."""
    if not GRADES_PATH.exists():
        return {}
    with open(GRADES_PATH, encoding='utf-8') as f:
        data = json.load(f)
    return data.get('grades', {})


def load_snapshot() -> dict:
    """Загружает снимок этапов с прошлого скана для сравнения."""
    if not SNAPSHOT_PATH.exists():
        return {}
    with open(SNAPSHOT_PATH, encoding='utf-8') as f:
        return json.load(f)


def save_snapshot(snapshot: dict) -> None:
    """Сохраняет текущие этапы как базу для следующего скана."""
    with open(SNAPSHOT_PATH, 'w', encoding='utf-8') as f:
        json.dump(snapshot, f, ensure_ascii=False, indent=2)


def _run_check_bot(tmpdir: str, repo_name: str, auto_stages: dict) -> None:
    """
    Копирует check_bot.py в tmpdir, запускает его.
    После запуска — заменяет строки этапов в REVIEW.md с учётом grades.json.
    """
    if not CHECK_BOT_PATH.exists():
        return

    bot_script = Path(tmpdir) / 'check_bot.py'
    shutil.copy(CHECK_BOT_PATH, bot_script)

    subprocess.run(
        [sys.executable, 'check_bot.py'],
        capture_output=True, text=True, cwd=tmpdir
    )
    bot_script.unlink(missing_ok=True)

    # Переопределяем строки этапов с учётом grades.json
    review_path = Path(tmpdir) / 'REVIEW.md'
    if not review_path.exists():
        return

    eff = _effective_stages({'repo': repo_name, 'auto_stages': auto_stages}, load_grades())
    text = review_path.read_text(encoding='utf-8')
    for key, lbl in zip(_STAGE_KEYS,
                        ('🚀 Этап 1 — Бот запущен',
                         '📅 Этап 2 — Расписание',
                         '💾 Этап 3 — Кеширование')):
        status_auto   = '✅ Реализовано' if eff[key] else '⏳ Не выполнено'
        status_manual = '✅ Реализовано' if eff[key] else '⏳ Не выполнено'
        # Заменяем строку этапа (авто-значение → grades-значение)
        text = re.sub(
            rf'\| {re.escape(lbl)} \| .+? \|',
            f'| {lbl} | {status_manual} |',
            text
        )
    review_path.write_text(text, encoding='utf-8')


def process_repo(repo_name: str) -> dict | None:
    """Клонирует репо, запускает checker, коммитит REVIEW.md. Возвращает dict со статусом."""
    parts = repo_name.split('_')
    first_name = parts[3] if len(parts) >= 5 else '?'
    last_name  = parts[4] if len(parts) >= 5 else '?'

    def make_result(status: str, bot_struct: str = '—', bot_security: str = '—',
                    auto_stages: dict | None = None) -> dict:
        return {'repo': repo_name, 'first_name': first_name,
                'last_name': last_name, 'status': status,
                'bot_struct': bot_struct, 'bot_security': bot_security,
                'auto_stages': auto_stages or {}}

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
        auto_stages = auto_detect_stages(tmpdir)

        # Ищем parser.py рекурсивно — студент мог положить в подпапку
        parser_paths = list(Path(tmpdir).glob('parser.py')) + list(Path(tmpdir).glob('**/parser.py'))
        parser_path = parser_paths[0] if parser_paths else None
        if not parser_path:
            print(f'[{repo_name}] parser.py не найден — создаём REVIEW.md без проверки парсера')
            # Настраиваем git
            subprocess.run(['git', 'config', 'user.name', 'teacher-bot[bot]'],
                           cwd=tmpdir, capture_output=True)
            subprocess.run(['git', 'config', 'user.email',
                            '41898282+github-actions[bot]@users.noreply.github.com'],
                           cwd=tmpdir, capture_output=True)
            # Создаём REVIEW.md с пояснением + запускаем check_bot.py
            review_path = Path(tmpdir) / 'REVIEW.md'
            review_path.write_text(
                '# Результаты проверки\n\n'
                '> ⏳ **`parser.py` не найден в репозитории.**  \n'
                '> Добавь файл `parser.py` в корень репо (или любую подпапку) и дождись следующего скана.\n',
                encoding='utf-8'
            )
            _run_check_bot(tmpdir, repo_name, auto_stages)
            subprocess.run(['git', 'add', 'REVIEW.md'], cwd=tmpdir, capture_output=True)
            diff = subprocess.run(['git', 'diff', '--cached', '--quiet'], cwd=tmpdir, capture_output=True)
            if diff.returncode != 0:
                subprocess.run(['git', 'commit', '-m', 'auto-review: нет parser.py [skip ci]'],
                               cwd=tmpdir, capture_output=True)
                push = subprocess.run(['git', 'push'], cwd=tmpdir, capture_output=True, text=True)
                if push.returncode == 0:
                    print(f'[{repo_name}] ✅ REVIEW.md создан (нет parser.py)')
                else:
                    print(f'[{repo_name}] ❌ Ошибка push: {push.stderr}')
            return make_result('⏳ Нет parser.py', bot_struct, bot_security, auto_stages)

        # Копируем checker.py и check_rules.json в папку репо
        shutil.copy(CHECKER_PATH, Path(tmpdir) / 'checker.py')
        if RULES_PATH.exists():
            shutil.copy(RULES_PATH, Path(tmpdir) / 'check_rules.json')

        # Запускаем checker — передаём относительный путь к parser.py
        rel_parser = str(parser_path.relative_to(Path(tmpdir)))
        check_result = subprocess.run(
            [sys.executable, 'checker.py', rel_parser],
            capture_output=True, text=True, cwd=tmpdir
        )

        review_path = Path(tmpdir) / 'REVIEW.md'
        if not review_path.exists():
            print(f'[{repo_name}] REVIEW.md не создан — пропускаем')
            return make_result('❓ Ошибка', bot_struct, bot_security, auto_stages)

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

        # Запускаем check_bot.py — он пишет детальный бот-блок в REVIEW.md
        _run_check_bot(tmpdir, repo_name, auto_stages)

        # Коммитим REVIEW.md
        subprocess.run(['git', 'add', 'REVIEW.md'], cwd=tmpdir, capture_output=True)
        diff = subprocess.run(
            ['git', 'diff', '--cached', '--quiet'],
            cwd=tmpdir, capture_output=True
        )
        if diff.returncode == 0:
            print(f'[{repo_name}] REVIEW.md не изменился')
            return make_result(status, bot_struct, bot_security, auto_stages)

        commit_msg = f'auto-review: {errors_word} в parser.py [skip ci]'
        subprocess.run(['git', 'commit', '-m', commit_msg],
                       cwd=tmpdir, capture_output=True)
        push = subprocess.run(['git', 'push'], cwd=tmpdir, capture_output=True, text=True)

        if push.returncode == 0:
            print(f'[{repo_name}] ✅ REVIEW.md обновлён ({errors_word})')
        else:
            print(f'[{repo_name}] ❌ Ошибка push: {push.stderr}')

        return make_result(status, bot_struct, bot_security, auto_stages)


# ─────────────────────────────────────────────────────────────────────────────

def update_readme_table(results: list[dict]) -> None:
    """Обновляет таблицы прогресса студентов в README.md основного репо."""
    readme_path = Path(__file__).parent / 'README.md'
    if not readme_path.exists():
        return

    content      = readme_path.read_text(encoding='utf-8')
    grades       = load_grades()
    prev_snapshot = load_snapshot()
    now          = datetime.datetime.utcnow().strftime('%d.%m.%Y %H:%M UTC')

    def grade_mark(r: dict, stage: str) -> str:
        manual = grades.get(r['repo'], {}).get(stage)
        if manual is True:
            return '✅'
        if r.get('auto_stages', {}).get(stage):
            return '🔍'
        return '⏳'

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
            f'| {grade_mark(r, "demo1")} '
            f'| {grade_mark(r, "demo2")} '
            f'| {grade_mark(r, "demo3")} |'
        )

    legend = (
        '> **Столбцы:**\n'
        '> | Столбец | Что проверяется |\n'
        '> |---------|----------------|\n'
        '> | Структура | Найден ли бот-файл (.py с TG-импортом), есть ли `requirements.txt` и обработчик `/start` |\n'
        '> | 🔒 Безопасность | Нет ли хардкода Telegram-токена в коде или конфигах |\n'
        '> | Этап 1 🚀 | **Бот запущен** — бот-файл + TG-библиотека + `/start` |\n'
        '> | Этап 2 📅 | **Расписание** — бот обращается к API spo-13 или использует `parser.py` |\n'
        '> | Этап 3 💾 | **Кеширование** — повторный вызов не скачивает файл заново (`json.dump/load`, `cache_index`) |\n'
        '>\n'
        '> **Статусы:**  \n'
        '> ✅ Подтверждено преподавателем &nbsp;·&nbsp; '
        '🔍 Авто-обнаружено по коду &nbsp;·&nbsp; '
        '⏳ Ещё не сделано\n'
    )

    progress_block = _progress_block(results, grades, prev_snapshot, now)
    bot_table = (
        legend + '\n'
        '| Студент | Репозиторий | Структура | 🔒 Безопасность | Этап 1 🚀 | Этап 2 📅 | Этап 3 💾 |\n'
        '|---------|-------------|-----------|-----------------|-----------|-----------|----------|\n'
        + ('\n'.join(bot_rows) + '\n' if bot_rows else '')
        + f'\n_Обновлено: {now}_\n\n'
        + progress_block
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

    # Сохраняем снимок текущих этапов для следующего скана
    new_snapshot = {
        r['repo']: _effective_stages(r, grades)
        for r in results
    }
    save_snapshot(new_snapshot)
    print('README.md: таблицы обновлены.')


def _effective_stages(r: dict, grades: dict) -> dict[str, bool]:
    """Итоговые этапы студента: ручной grades.json имеет приоритет над автодетектом."""
    out = {}
    for stage in _STAGE_KEYS:
        manual = grades.get(r['repo'], {}).get(stage)
        auto   = r.get('auto_stages', {}).get(stage, False)
        out[stage] = bool(manual is True or auto)
    return out


def _stage_level(r: dict, grades: dict) -> int:
    """Наивысший последовательный пройденный этап (0..3)."""
    eff = _effective_stages(r, grades)
    level = 0
    for i, stage in enumerate(_STAGE_KEYS, start=1):
        if eff[stage]:
            level = i
        else:
            break
    return level


def _progress_block(results: list[dict], grades: dict, prev: dict, now: str) -> str:
    """Генерирует блок прогресса: новые достижения + прогресс-бар + распределение."""
    n_total = len(results) * len(_STAGE_KEYS)

    # Эффективные этапы для каждого студента
    eff = {r['repo']: _effective_stages(r, grades) for r in results}

    # Что нового с прошлого скана
    new_ach: dict[str, list[str]] = {}
    for r in results:
        repo = r['repo']
        name = f'{r["first_name"]} {r["last_name"]}'
        for stage, label in zip(_STAGE_KEYS, _STAGE_LABELS):
            was  = prev.get(repo, {}).get(stage, False)
            is_now = eff[repo][stage]
            if is_now and not was:
                new_ach.setdefault(name, []).append(label)

    # Общий прогресс
    n_done  = sum(1 for e in eff.values() for v in e.values() if v)
    pct     = round(n_done / n_total * 100) if n_total else 0
    filled  = round(pct / 5)
    bar     = '█' * filled + '░' * (20 - filled)

    lines: list[str] = []

    # ── Новые достижения ────────────────────────────────────────────────────
    if new_ach:
        lines += [f'### 🆕 Новые достижения — {now}', '']
        for name, stages_list in new_ach.items():
            lines.append(f'- **{name}** → {", ".join(stages_list)}')
        lines.append('')

    # ── Групповые вехи ──────────────────────────────────────────────────────
    for stage, label in zip(_STAGE_KEYS, _STAGE_LABELS):
        all_now  = results and all(eff[r['repo']][stage] for r in results)
        all_prev = results and all(prev.get(r['repo'], {}).get(stage, False) for r in results)
        if all_now and not all_prev:
            lines += [f'> 🏆 Вся группа сдала **{label}**!', '']

    # ── Прогресс к ТЗ ───────────────────────────────────────────────────────
    lines += [
        f'### 📈 Прогресс группы к ТЗ — {pct}%',
        '',
        f'`{bar}` {n_done}/{n_total} этапов',
        '',
    ]

    # Мини-прогресс по каждому студенту
    for r in sorted(results, key=lambda x: x['last_name']):
        repo = r['repo']
        name = f'{r["first_name"]} {r["last_name"]}'
        icons   = ''.join('✅' if eff[repo][s] else '⬜' for s in _STAGE_KEYS)
        s_done  = sum(1 for v in eff[repo].values() if v)
        s_pct   = round(s_done / len(_STAGE_KEYS) * 100)
        # Пометить тех, у кого новое достижение
        badge = ' 🆕' if name in new_ach else ''
        lines.append(f'- {icons} **{name}** — {s_pct}%{badge}')

    lines.append('')

    # ── Распределение по уровням ─────────────────────────────────────────────
    _LEVEL_LABELS = {
        3: '💾 Уровень 3 — Кеширование',
        2: '📅 Уровень 2 — Расписание',
        1: '🚀 Уровень 1 — Бот запущен',
        0: '⏳ Ещё не начали',
    }
    level_groups: dict[int, list[str]] = {}
    for r in results:
        lvl = _stage_level(r, grades)
        level_groups.setdefault(lvl, []).append(f'{r["first_name"]} {r["last_name"]}')

    lines.append('**Распределение:**')
    for lvl in (3, 2, 1, 0):
        names = level_groups.get(lvl, [])
        if names:
            lines.append(f'> {_LEVEL_LABELS[lvl]}: {", ".join(names)} ({len(names)})')

    return '\n'.join(lines) + '\n'


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
