#!/usr/bin/env python3
"""
Статическая проверка Telegram-бота студента.
Запускается в корне репо студента (или передаётся путь как аргумент).
Дополняет / создаёт REVIEW.md.

Проверки:
  1. Бот-файл найден (любой .py с TG-импортом)
  2. requirements.txt существует
  3. TG-библиотека в requirements.txt
  4. Обработчик /start в коде
  5. .gitignore содержит .env
  6. Токен НЕ захардкожен в коде
  7. Используются переменные окружения (os.environ / dotenv)
"""
import sys
import re
from pathlib import Path

ROOT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path('.')

TG_LIBS   = ['aiogram', 'telebot', 'python-telegram-bot', 'telegram']
TOKEN_RE  = re.compile(r'\d{8,10}:[A-Za-z0-9_-]{35,}')
SCHED_KW  = ['raspisanie', 'schedule', 'timetable', 'lesson', 'group',
             'kstu', 'college', '/api/', 'requests.get', 'urllib', 'parser']
CACHE_KW  = ['json.dump', 'json.load', 'pickle', 'cache', 'кеш', 'shelve',
             'open(', 'write(']

BOT_START = '<!-- BOT_CHECK_START -->'
BOT_END   = '<!-- BOT_CHECK_END -->'

_SKIP_FILES = {'checker.py', 'check_bot.py', 'check_rules.json'}


def _all_py(root: Path):
    return [f for f in root.glob('**/*.py')
            if f.is_file()
            and '.git' not in f.parts
            and f.name not in _SKIP_FILES]


def run_checks() -> dict:
    all_py   = _all_py(ROOT)
    all_code = '\n'.join(f.read_text(encoding='utf-8', errors='ignore') for f in all_py)
    code_low = all_code.lower()

    # 1. Бот-файл
    tg_file = next(
        (f for f in all_py
         if any(lib in f.read_text(encoding='utf-8', errors='ignore').lower()
                for lib in TG_LIBS)),
        None
    )

    # 2-3. requirements.txt + TG-библиотека
    req_files = [r for r in
                 list(ROOT.glob('requirements.txt')) + list(ROOT.glob('**/requirements.txt'))
                 if '.git' not in r.parts]
    req_text = req_files[0].read_text(encoding='utf-8', errors='ignore').lower() if req_files else ''

    # 5. .gitignore содержит .env
    gi = ROOT / '.gitignore'
    gi_text = gi.read_text(encoding='utf-8', errors='ignore') if gi.exists() else ''

    # 7. Переменные окружения
    uses_env = ('os.environ' in all_code or 'os.getenv' in all_code
                or 'dotenv' in code_low or 'load_dotenv' in code_low)

    # Авто-этапы
    has_tg   = tg_file is not None or any(lib in req_text for lib in TG_LIBS)
    has_start = 'start' in code_low
    demo1 = has_tg and has_start
    demo2 = demo1 and any(kw in code_low for kw in SCHED_KW)
    demo3 = demo2 and any(kw in code_low for kw in CACHE_KW)

    return {
        'bot_file':      tg_file is not None,
        'requirements':  bool(req_files),
        'tg_in_req':     any(lib in req_text for lib in TG_LIBS),
        'has_start':     'start' in code_low,
        'gitignore_env': gi.exists() and '.env' in gi_text,
        'no_token':      not bool(TOKEN_RE.search(all_code)),
        'uses_env':      uses_env,
        'demo1': demo1,
        'demo2': demo2,
        'demo3': demo3,
    }


CHECK_LABELS = [
    ('bot_file',      '📁 Бот-файл найден'),
    ('requirements',  '📋 requirements.txt'),
    ('tg_in_req',     '📦 TG-библиотека в requirements'),
    ('has_start',     '▶️  Обработчик /start'),
    ('gitignore_env', '🛡️  .gitignore содержит .env'),
    ('no_token',      '🔑 Токен не в коде'),
    ('uses_env',      '🔐 Переменные окружения'),
]

STAGE_LABELS = [
    ('demo1', '🚀 Этап 1 — Бот запущен'),
    ('demo2', '📅 Этап 2 — Расписание'),
    ('demo3', '💾 Этап 3 — Кеширование'),
]


def build_section(r: dict, stage_override: dict | None = None) -> str:
    """
    stage_override: {'demo1': bool, 'demo2': bool, 'demo3': bool}
    Если передан — используется вместо авто (для grades.json со стороны препода).
    """
    stages = stage_override or {k: r[k] for k, _ in STAGE_LABELS}

    warn = (
        '> ⚠️ **КРИТИЧНО: токен найден в коде!**  \n'
        '> Немедленно отзови у @BotFather (`/revoke`), получи новый и убери в `.env`.\n\n'
        if not r['no_token'] else ''
    )

    check_rows = '\n'.join(
        f'| {lbl} | {"✅" if r[key] else "❌"} |'
        for key, lbl in CHECK_LABELS
    )
    stage_rows = '\n'.join(
        f'| {lbl} | {"✅ Реализовано" if stages[key] else "⏳ Не выполнено"} |'
        for key, lbl in STAGE_LABELS
    )

    return (
        f'{BOT_START}\n'
        '## 🤖 Проверка Telegram-бота\n\n'
        + warn
        + '| Проверка | Результат |\n'
          '|----------|-----------|\n'
        + check_rows + '\n\n'
        + '| Этап | Статус |\n'
          '|------|--------|\n'
        + stage_rows + '\n'
        + f'{BOT_END}'
    )


def update_review(section: str) -> None:
    review = ROOT / 'REVIEW.md'
    if review.exists():
        text = review.read_text(encoding='utf-8')
        if BOT_START in text:
            # Заменяем существующий блок
            text = re.sub(
                re.escape(BOT_START) + r'.*?' + re.escape(BOT_END),
                section, text, flags=re.DOTALL
            )
        else:
            # Убираем старый блок без маркеров (если был)
            text = re.sub(r'\n\n---\n## 🤖 Проверка Telegram-бота.*$', '',
                          text, flags=re.DOTALL)
            text = text.rstrip() + '\n\n---\n' + section
    else:
        text = '# Результаты проверки бота\n\n---\n' + section

    review.write_text(text, encoding='utf-8')


if __name__ == '__main__':
    r = run_checks()
    section = build_section(r)
    update_review(section)

    issues = [lbl for key, lbl in CHECK_LABELS if not r[key]]
    if issues:
        print('Проблемы с ботом:')
        for i in issues:
            print(f'  ✗ {i}')
        sys.exit(1)
    else:
        print('✅ Все проверки бота пройдены')
        sys.exit(0)
