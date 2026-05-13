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
                   r'^UP_06_\d{2}-\d{2}-\d{4}_[A-Za-z]+_[A-Za-z]+_32ISd$'),
    re.IGNORECASE
)
CHECKER_PATH = Path(__file__).parent / 'checker.py'
RULES_PATH   = Path(__file__).parent / 'check_rules.json'

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


def process_repo(repo_name: str) -> dict | None:
    """Клонирует репо, запускает checker, коммитит REVIEW.md. Возвращает dict со статусом."""
    parts = repo_name.split('_')
    first_name = parts[3] if len(parts) >= 5 else '?'
    last_name  = parts[4] if len(parts) >= 5 else '?'

    def make_result(status: str) -> dict:
        return {'repo': repo_name, 'first_name': first_name,
                'last_name': last_name, 'status': status}

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

        parser_path = Path(tmpdir) / 'parser.py'
        if not parser_path.exists():
            print(f'[{repo_name}] parser.py не найден — пропускаем')
            return make_result('⏳ Нет parser.py')

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
            return make_result('❓ Ошибка')

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

        return make_result(status)


# ─────────────────────────────────────────────────────────────────────────────

def update_readme_table(results: list[dict]) -> None:
    """Обновляет таблицу прогресса студентов в README.md основного репо."""
    readme_path = Path(__file__).parent / 'README.md'
    if not readme_path.exists():
        return

    content = readme_path.read_text(encoding='utf-8')

    now = datetime.datetime.utcnow().strftime('%d.%m.%Y %H:%M UTC')
    rows = []
    for r in sorted(results, key=lambda x: x['last_name']):
        repo_url = f'https://github.com/{ORG}/{r["repo"]}'
        rows.append(
            f'| {r["first_name"]} {r["last_name"]} '
            f'| [{r["repo"]}]({repo_url}) '
            f'| {r["status"]} |'
        )

    table = (
        '| Студент | Репозиторий | Статус |\n'
        '|---------|-------------|--------|\n'
        + ('\n'.join(rows) + '\n' if rows else '')
        + f'\n_Обновлено: {now}_'
    )

    new_section = (
        '<!-- STUDENTS_TABLE_START -->\n'
        + table
        + '\n<!-- STUDENTS_TABLE_END -->'
    )
    new_content = re.sub(
        r'<!-- STUDENTS_TABLE_START -->.*?<!-- STUDENTS_TABLE_END -->',
        new_section,
        content,
        flags=re.DOTALL
    )

    if new_content != content:
        readme_path.write_text(new_content, encoding='utf-8')
        print('README.md: таблица студентов обновлена.')
    else:
        print('README.md: таблица студентов не изменилась.')


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
