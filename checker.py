#!/usr/bin/env python3
"""
Автоматическая проверка parser.py студентов (UP_06).

Формат задания: студент раскомментирует правильный вариант из двух.
Checker проверяет через AST — какой вариант раскомментирован и верен ли он.

Использование:
    python checker.py parser.py

Выход:
    0  — всё верно
    1  — найдены ошибки
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
_ok:     list[dict] = []


def _add_err(step: str, line: int, found: str, expected: str, hint: str) -> None:
    _errors.append(dict(step=step, line=line, found=found, expected=expected, hint=hint))


def _add_ok(step: str, value: str) -> None:
    _ok.append(dict(step=step, value=value))


# ─────────────────────────────────────────────────────────────────────────────
# Вспомогательные функции для AST
# ─────────────────────────────────────────────────────────────────────────────

def _subscript_key(node: ast.Subscript) -> str | None:
    """Возвращает строковый ключ подписки, если он есть."""
    sl = node.slice
    if isinstance(sl, ast.Constant) and isinstance(sl.value, str):
        return sl.value
    return None


def _collect_subscript_keys(tree: ast.AST) -> list[tuple[int, str]]:
    """Список (lineno, key) всех subscript-обращений к словарю по строке."""
    result = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Subscript):
            k = _subscript_key(node)
            if k:
                result.append((node.lineno, k))
    return result


def _collect_get_keys(tree: ast.AST) -> list[tuple[int, str]]:
    """Список (lineno, key) всех .get("key", ...) вызовов."""
    result = []
    for node in ast.walk(tree):
        if (isinstance(node, ast.Call) and
                isinstance(node.func, ast.Attribute) and
                node.func.attr == 'get' and
                node.args):
            first = node.args[0]
            if isinstance(first, ast.Constant) and isinstance(first.value, str):
                result.append((node.lineno, first.value))
    return result


# ─────────────────────────────────────────────────────────────────────────────
# Проверки по шагам
# ─────────────────────────────────────────────────────────────────────────────

def _check_step1_page_id(tree: ast.AST) -> None:
    """response.json()["data"]["id"]"""
    keys = {k for _, k in _collect_subscript_keys(tree)}
    if 'data' in keys and 'id' in keys:
        _add_ok('Шаг 1', 'response.json()["data"]["id"]')
    elif 'result' in keys:
        _add_err('Шаг 1', 0,
                 found='response.json()["result"]["id"]',
                 expected='response.json()["data"]["id"]',
                 hint='Верхний ключ ответа называется "data", а не "result". '
                      'Раскомментируй вариант Б.')
    else:
        _add_err('Шаг 1', 0,
                 found='(не найдено)',
                 expected='response.json()["data"]["id"]',
                 hint='Раскомментируй строку: page_id = response.json()["data"]["id"]')


def _check_step2_folders(tree: ast.AST) -> None:
    """response.json()["data"]["folders"]"""
    keys = {k for _, k in _collect_subscript_keys(tree)}
    if 'folders' in keys:
        _add_ok('Шаг 2', 'response.json()["data"]["folders"]')
    elif 'items' in keys:
        _add_err('Шаг 2', 0,
                 found='response.json()["data"]["items"]',
                 expected='response.json()["data"]["folders"]',
                 hint='Ключ называется "folders", а не "items". '
                      'Раскомментируй вариант Б.')
    else:
        _add_err('Шаг 2', 0,
                 found='(не найдено)',
                 expected='response.json()["data"]["folders"]',
                 hint='Раскомментируй строку: folders = response.json()["data"]["folders"]')


def _check_step3_title(tree: ast.AST) -> None:
    """folder["title"] в условии поиска папки"""
    # Ищем Compare с .lower() внутри
    for node in ast.walk(tree):
        if not isinstance(node, ast.Compare):
            continue
        for comp in node.comparators:
            if not (isinstance(comp, ast.Call) and
                    isinstance(comp.func, ast.Attribute) and
                    comp.func.attr == 'lower'):
                continue
            inner = comp.func.value
            # str(x["..."]).lower()  или  x["..."].lower()
            sub = None
            if (isinstance(inner, ast.Call) and
                    isinstance(inner.func, ast.Name) and
                    inner.func.id == 'str' and inner.args):
                sub = inner.args[0]
            elif isinstance(inner, ast.Subscript):
                sub = inner
            if sub and isinstance(sub, ast.Subscript):
                k = _subscript_key(sub)
                if k == 'title':
                    _add_ok('Шаг 3', 'folder["title"]')
                    return
                elif k == 'id':
                    _add_err('Шаг 3', node.lineno,
                             found='folder["id"]',
                             expected='folder["title"]',
                             hint='"id" — это число (778), в нём нельзя найти текст '
                                  '"расписание учебных". Раскомментируй вариант Б.')
                    return
    _add_err('Шаг 3', 0,
             found='(не найдено)',
             expected='folder["title"]',
             hint='Раскомментируй строку с вариантом Б: if "расписание учебных" in folder["title"].lower()')


def _check_step4_corpus_loop(tree: ast.AST) -> None:
    """schedule_folder["folders"] — цикл по корпусам"""
    keys = {k for _, k in _collect_subscript_keys(tree)}
    if 'files' in keys and 'folders' not in keys:
        _add_err('Шаг 4 (цикл корпусов)', 0,
                 found='schedule_folder["files"]',
                 expected='schedule_folder["folders"]',
                 hint='Корпуса хранятся в ключе "folders", а не "files". '
                      'Раскомментируй вариант Б.')
    elif 'folders' in keys:
        _add_ok('Шаг 4 (цикл корпусов)', 'schedule_folder["folders"]')
    else:
        _add_err('Шаг 4 (цикл корпусов)', 0,
                 found='(не найдено)',
                 expected='schedule_folder["folders"]',
                 hint='Раскомментируй строку: for korpus in schedule_folder["folders"]')


def _check_step4_korpus_title(tree: ast.AST) -> None:
    """korpus["title"] != KORPUS"""
    keys = {k for _, k in _collect_subscript_keys(tree)}
    if 'title' in keys:
        _add_ok('Шаг 4 (сравнение корпуса)', 'korpus["title"]')
    else:
        _add_err('Шаг 4 (сравнение корпуса)', 0,
                 found='korpus["id"]',
                 expected='korpus["title"]',
                 hint='Название корпуса хранится в ключе "title". '
                      'Раскомментируй вариант Б.')


def _check_step4_files_loop(tree: ast.AST) -> None:
    """for f in korpus["files"]"""
    keys = {k for _, k in _collect_subscript_keys(tree)}
    if 'files' in keys:
        _add_ok('Шаг 4 (цикл файлов)', 'korpus["files"]')
    else:
        _add_err('Шаг 4 (цикл файлов)', 0,
                 found='korpus["folders"]',
                 expected='korpus["files"]',
                 hint='Файлы расписания хранятся в ключе "files". '
                      'Раскомментируй вариант Б.')


def _check_step4_file_keys(tree: ast.AST) -> None:
    """
    Проверяем что в files.append() используются правильные ключи:
    f["id"], f["title"], f["src"], f.get("ext", ...)
    """
    sub_keys = {k for _, k in _collect_subscript_keys(tree)}
    get_keys = {k for _, k in _collect_get_keys(tree)}

    # f["id"]
    if 'id' in sub_keys:
        _add_ok('Шаг 4 (file_id)', 'f["id"]')
    else:
        _add_err('Шаг 4 (file_id)', 0,
                 found='f["title"]',
                 expected='f["id"]',
                 hint='ID файла хранится в ключе "id". Раскомментируй вариант Б.')

    # f["title"] для course
    if 'title' in sub_keys:
        _add_ok('Шаг 4 (course)', 'f["title"]')
    else:
        _add_err('Шаг 4 (course)', 0,
                 found='f["id"]',
                 expected='f["title"]',
                 hint='Название курса хранится в ключе "title". Раскомментируй вариант Б.')

    # f["src"]
    if 'src' in sub_keys:
        _add_ok('Шаг 4 (src)', 'f["src"]')
    else:
        _add_err('Шаг 4 (src)', 0,
                 found='f["id"]',
                 expected='f["src"]',
                 hint='Путь к файлу хранится в ключе "src". Раскомментируй вариант Б.')

    # f.get("ext", ...)
    if 'ext' in get_keys:
        _add_ok('Шаг 4 (ext)', 'f.get("ext", "xlsx")')
    else:
        _add_err('Шаг 4 (ext)', 0,
                 found='f.get("id", "xlsx")',
                 expected='f.get("ext", "xlsx")',
                 hint='Расширение файла хранится в ключе "ext". Раскомментируй вариант Б.')


# ─────────────────────────────────────────────────────────────────────────────
# Генерация REVIEW.md
# ─────────────────────────────────────────────────────────────────────────────

def _generate_review(filepath: str) -> str:
    now = datetime.now().strftime('%Y-%m-%d %H:%M')
    total = len(_errors) + len(_ok)

    if not _errors:
        ok_list = '\n'.join(f'- ✅ {item["step"]}: `{item["value"]}`' for item in _ok)
        return (
            f"# ✅ Проверка пройдена — `{filepath}`\n\n"
            f"_Проверено: {now}_\n\n"
            f"Все {total} шагов выполнены верно:\n\n"
            f"{ok_list}\n\n"
            "Отлично! Можно двигаться дальше — интегрировать парсер в Telegram-бота.\n"
        )

    parts = [
        f"# 🔍 Автоматическая проверка — `{filepath}`",
        f"\n_Проверено: {now}_\n",
        f"**Ошибок: {len(_errors)}** из {total} шагов\n",
        "---\n",
    ]

    for i, err in enumerate(_errors, 1):
        line_str = f" (строка {err['line']})" if err['line'] else ''
        parts += [
            f"## ❌ {err['step']}{line_str}\n",
            "```python",
            f"# Раскомментировано (неверно):",
            f"... {err['found']} ...",
            "",
            f"# Должно быть (вариант Б):",
            f"... {err['expected']} ...",
            "```\n",
            f"**Подсказка:** {err['hint']}\n",
            "---\n",
        ]

    if _ok:
        parts.append("\n## ✅ Верно выполненные шаги\n")
        for item in _ok:
            parts.append(f'- ✅ {item["step"]}: `{item["value"]}`')
        parts.append('')

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
        review = (
            f"# ❌ Синтаксическая ошибка — `{filepath}`\n\n"
            f"_Проверено: {datetime.now().strftime('%Y-%m-%d %H:%M')}_\n\n"
            f"Python не смог прочитать файл:\n```\n{exc}\n```\n\n"
            "Проверь правильность отступов и скобок.\n"
        )
        Path('REVIEW.md').write_text(review, encoding='utf-8')
        print(review)
        sys.exit(1)

    _check_step1_page_id(tree)
    _check_step2_folders(tree)
    _check_step3_title(tree)
    _check_step4_corpus_loop(tree)
    _check_step4_korpus_title(tree)
    _check_step4_files_loop(tree)
    _check_step4_file_keys(tree)

    review = _generate_review(filepath)
    Path('REVIEW.md').write_text(review, encoding='utf-8')
    print(review)

    sys.exit(1 if _errors else 0)


if __name__ == '__main__':
    main()
