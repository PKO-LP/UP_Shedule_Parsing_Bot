#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Универсальный чекер учебных заданий.

Правила проверки читает из check_rules.json (в той же папке, что и checker.py).
Для нового задания достаточно написать новый check_rules.json — этот файл не трогать.

Использование:
    python checker.py [путь/к/student_file.py]

Выход:
    0  — все шаги верны
    1  — есть ошибки
    Файл REVIEW.md создаётся/перезаписывается в текущей рабочей папке.
"""

import ast
import json
import sys
from pathlib import Path
from datetime import datetime


def get_code_lines(source: str) -> str:
    """Возвращает только строки исходника, не являющиеся комментариями.
    Нормализует внутренние пробелы для устойчивого сравнения."""
    import re as _re
    result = []
    for line in source.splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith('#'):
            # Нормализуем множественные пробелы/табы → один пробел
            normalized = _re.sub(r'[ \t]+', ' ', stripped)
            result.append(normalized)
    return '\n'.join(result)


def check_step(code: str, step: dict) -> tuple:
    """
    Проверяет один шаг.
    Возвращает (ok, что нашли раскомментированным).
    """
    correct = step['correct']
    wrong   = step.get('wrong', '')

    correct_found = correct in code
    wrong_found   = bool(wrong) and wrong in code

    if correct_found and not wrong_found:
        return True, correct
    elif wrong_found:
        return False, wrong
    else:
        return False, ''


def main() -> None:
    checker_dir = Path(__file__).parent
    rules_path  = checker_dir / 'check_rules.json'
    filepath    = sys.argv[1] if len(sys.argv) > 1 else 'parser.py'

    if not rules_path.exists():
        print(f'Ошибка: check_rules.json не найден в {checker_dir}')
        sys.exit(1)

    with open(rules_path, encoding='utf-8') as f:
        rules = json.load(f)

    try:
        source = Path(filepath).read_text(encoding='utf-8')
    except FileNotFoundError:
        print(f'Файл {filepath} не найден')
        sys.exit(1)

    # Синтаксическая проверка
    try:
        ast.parse(source)
    except SyntaxError as exc:
        ts = datetime.now().strftime('%Y-%m-%d %H:%M')
        review = (
            "# FAIL Синтаксическая ошибка\n\n"
            f"_Проверено: {ts}_\n\n"
            f"Python не смог прочитать файл:\n```\n{exc}\n```\n\n"
            "Проверь правильность отступов и скобок.\n"
        )
        Path('REVIEW.md').write_text(review, encoding='utf-8')
        print(review)
        sys.exit(1)

    code    = get_code_lines(source)
    steps   = rules.get('steps', [])
    errors  = []
    ok_list = []

    for step in steps:
        ok, found = check_step(code, step)
        if ok:
            ok_list.append(step)
        else:
            errors.append({**step, '_found': found})

    # Генерация REVIEW.md
    ts    = datetime.now().strftime('%Y-%m-%d %H:%M')
    fname = Path(filepath).name
    lines = [
        f"# Автоматическая проверка — `{fname}`",
        "",
        f"_Проверено: {ts}_",
        "",
        f"**Ошибок: {len(errors)}** из {len(steps)} шагов",
        "",
        "---",
        "",
    ]

    for err in errors:
        found = err['_found']
        lines += [
            f"## FAIL {err['id']}",
            "",
            "```python",
            "# Раскомментировано (неверно):",
            f"... {found if found else '(не найдено)'} ...",
            "",
            "# Должно быть:",
            f"... {err['correct']} ...",
            "```",
            "",
            f"**Подсказка:** {err.get('hint', '')}",
            "",
            "---",
            "",
        ]

    if ok_list:
        lines += ["## OK — Верно выполненные шаги", ""]
        for step in ok_list:
            lines.append(f"- OK {step['id']}: `{step['correct']}`")
        lines.append("")

    review = '\n'.join(lines)
    Path('REVIEW.md').write_text(review, encoding='utf-8')
    print(review)
    sys.exit(1 if errors else 0)


if __name__ == '__main__':
    main()
