#!/usr/bin/env python3
"""
Автоматическая проверка parser.py студентов (UP_03/05/06).

Использование:
    python checker.py parser.py

Выход:
    0  — ошибок нет
    1  — найдены ошибки (GitHub Actions покажет "failed")
    Файл REVIEW.md создаётся/перезаписывается в рабочей папке.
"""

import ast
import sys
from pathlib import Path
from datetime import datetime

# ─────────────────────────────────────────────────────────────────────────────
# Хранилище найденных ошибок
# ─────────────────────────────────────────────────────────────────────────────

_errors: list[dict] = []


def _add(num: int, line: int, found: str, expected: str, explanation: str) -> None:
    _errors.append(
        dict(num=num, line=line, found=found, expected=expected, explanation=explanation)
    )


# ─────────────────────────────────────────────────────────────────────────────
# AST-проверки
# ─────────────────────────────────────────────────────────────────────────────

def _source_line(lines: list[str], lineno: int) -> str:
    try:
        return lines[lineno - 1].strip()
    except IndexError:
        return '?'


def _check_subscripts(tree: ast.AST) -> None:
    """
    Ошибки 2–3, 5: f[8491]  или  f["/attach_files/..."]
    вместо f["id"] / f["src"].
    """
    seen_int = False
    seen_path = False

    for node in ast.walk(tree):
        if not isinstance(node, ast.Subscript):
            continue
        sl = node.slice
        if not isinstance(sl, ast.Constant):
            continue

        val = sl.value

        if isinstance(val, int) and not seen_int:
            seen_int = True
            _add(
                2, node.lineno,
                found=f'f[{val}]',
                expected='f["id"]',
                explanation=(
                    f'{val} — это значение ключа "id", а не имя ключа. '
                    'Обращаться к словарю нужно по строковому имени: f["id"].'
                ),
            )

        elif isinstance(val, str) and val.startswith('/') and not seen_path:
            seen_path = True
            short = val[:40] + ('...' if len(val) > 40 else '')
            _add(
                3, node.lineno,
                found=f'f["{short}"]',
                expected='f["src"]',
                explanation=(
                    f'"{short}" — это значение ключа "src", а не имя ключа. '
                    'Правильно: f["src"].'
                ),
            )


def _check_get_with_int(tree: ast.AST) -> None:
    """
    Ошибка 4: f.get(8491, 'xlsx')  →  f.get("ext", "xlsx")
    """
    seen = False
    for node in ast.walk(tree):
        if seen:
            break
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not (isinstance(func, ast.Attribute) and func.attr == 'get'):
            continue
        if not node.args:
            continue
        first = node.args[0]
        if isinstance(first, ast.Constant) and isinstance(first.value, int):
            seen = True
            _add(
                4, node.lineno,
                found=f'.get({first.value}, ...)',
                expected='.get("ext", ...)',
                explanation=(
                    f'{first.value} — это значение, а не имя ключа. '
                    'Правильно: f.get("ext", "xlsx").'
                ),
            )


def _check_id_in_title_search(tree: ast.AST) -> None:
    """
    Ошибка 1: 'расписание учебных' in str(folder["id"]).lower()
    вместо    'расписание учебных' in folder["title"].lower()

    Ищем Compare, где в comparators есть Call(.lower()→Call(str()→Subscript("id")))
    """
    seen = False
    for node in ast.walk(tree):
        if seen:
            break
        if not isinstance(node, ast.Compare):
            continue
        for comp in node.comparators:
            # comp должен быть: str(x["id"]).lower()  или  x["id"].lower()
            if not (isinstance(comp, ast.Call) and
                    isinstance(comp.func, ast.Attribute) and
                    comp.func.attr == 'lower'):
                continue

            # две формы: str(x["id"]).lower()  и  x["id"].lower()
            inner_val = comp.func.value  # объект, у которого вызываем .lower()

            # форма 1: str(subscript).lower()
            if (isinstance(inner_val, ast.Call) and
                    isinstance(inner_val.func, ast.Name) and
                    inner_val.func.id == 'str' and
                    inner_val.args):
                subscript = inner_val.args[0]
            # форма 2: subscript.lower()
            elif isinstance(inner_val, ast.Subscript):
                subscript = inner_val
            else:
                continue

            if not isinstance(subscript, ast.Subscript):
                continue
            sl = subscript.slice
            if isinstance(sl, ast.Constant) and sl.value == 'id':
                seen = True
                _add(
                    1, node.lineno,
                    found='folder["id"]',
                    expected='folder["title"]',
                    explanation=(
                        'Название папки хранится в ключе "title", а не "id". '
                        '"id" содержит число — строка "расписание учебных" никогда '
                        'не будет найдена в числе.'
                    ),
                )
                break


# ─────────────────────────────────────────────────────────────────────────────
# Генерация REVIEW.md
# ─────────────────────────────────────────────────────────────────────────────

def _generate_review(filepath: str) -> str:
    now = datetime.now().strftime('%Y-%m-%d %H:%M')

    if not _errors:
        return (
            f"# ✅ Проверка пройдена — `{filepath}`\n\n"
            f"_Проверено: {now}_\n\n"
            "Ошибок не найдено. Код соответствует ожидаемому решению.\n"
        )

    parts = [
        f"# 🔍 Автоматическая проверка — `{filepath}`",
        f"\n_Проверено: {now}_\n",
        f"## Итого: **{len(_errors)} ошибок**\n",
        "---\n",
    ]

    for i, err in enumerate(_errors, 1):
        parts += [
            f"## Ошибка {i} — строка {err['line']}\n",
            "```python",
            f"# ❌ Написано:",
            f"... {err['found']} ...",
            "",
            f"# ✅ Должно быть:",
            f"... {err['expected']} ...",
            "```\n",
            f"**Пояснение:** {err['explanation']}\n",
            "---\n",
        ]

    parts += [
        "\n## Общая причина всех ошибок\n",
        "Все ошибки вызваны одним непониманием: **значения JSON-ключей "
        "использованы вместо имён ключей**.\n",
        "Пример структуры файла из API:",
        "```json",
        '{',
        '  "id":    8491,',
        '  "title": "1 курс",',
        '  "src":   "/attach_files/.../file.xlsx",',
        '  "ext":   "xlsx"',
        '}',
        "```",
        "",
        "| Нужно получить | Правильно | Неправильно |",
        "|----------------|-----------|-------------|",
        "| ID файла       | `f[\"id\"]`  | `f[8491]`   |",
        "| Путь к файлу   | `f[\"src\"]` | `f[\"/attach_files/...\"]` |",
        "| Расширение     | `f.get(\"ext\", \"xlsx\")` | `f.get(8491, \"xlsx\")` |",
        "| Название папки | `folder[\"title\"]` | `folder[\"id\"]` |",
    ]

    return '\n'.join(parts) + '\n'


# ─────────────────────────────────────────────────────────────────────────────
# Точка входа
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    filepath = sys.argv[1] if len(sys.argv) > 1 else 'parser.py'

    source = Path(filepath).read_text(encoding='utf-8')
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        print(f'СИНТАКСИЧЕСКАЯ ОШИБКА в {filepath}: {exc}')
        sys.exit(1)

    _check_id_in_title_search(tree)
    _check_subscripts(tree)
    _check_get_with_int(tree)

    review = _generate_review(filepath)
    Path('REVIEW.md').write_text(review, encoding='utf-8')
    print(review)

    sys.exit(1 if _errors else 0)


if __name__ == '__main__':
    main()
