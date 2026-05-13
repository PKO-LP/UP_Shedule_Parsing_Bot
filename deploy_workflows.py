#!/usr/bin/env python3
"""
Разворачивает актуальный check_parser.yml во все студенческие репо.
Требует GH_TOKEN с scope: repo + workflow
"""
import os, re, sys, base64, json, tempfile, shutil, subprocess
from pathlib import Path
import urllib.request, urllib.error

ORG     = os.environ.get('ORG', 'PKO-LP')
TOKEN   = os.environ.get('GH_TOKEN', '')
PATTERN = re.compile(
    os.environ.get('REPO_PATTERN',
                   r'^UP_06_\d{2}-\d{2}-\d{4}_[A-Za-z][A-Za-z0-9-]*_[A-Za-z][A-Za-z0-9-]*_32ISd$'),
    re.IGNORECASE
)
WORKFLOW_SRC = Path(__file__).parent / 'assets' / 'check_parser.yml'


def gh_api(path: str, method='GET', body=None):
    url = f'https://api.github.com{path}'
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(url, data=data, method=method, headers={
        'Authorization': f'Bearer {TOKEN}',
        'Accept': 'application/vnd.github+json',
        'X-GitHub-Api-Version': '2022-11-28',
        'Content-Type': 'application/json',
    })
    try:
        with urllib.request.urlopen(req) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        return {'_error': e.code, '_msg': e.read().decode()}


def get_student_repos():
    page, repos = 1, []
    while True:
        data = gh_api(f'/orgs/{ORG}/repos?per_page=100&page={page}')
        if not isinstance(data, list) or not data:
            break
        repos += [r['name'] for r in data if PATTERN.match(r['name'])]
        page += 1
    return repos


correct_content = WORKFLOW_SRC.read_text(encoding='utf-8')
correct_b64 = base64.b64encode(correct_content.encode()).decode()


def deploy_to(repo_name: str):
    wf_path = '.github/workflows/check_parser.yml'
    api_path = f'/repos/{ORG}/{repo_name}/contents/{wf_path}'

    existing = gh_api(api_path)
    if '_error' not in existing:
        # Уже есть — проверяем содержимое
        remote = base64.b64decode(existing['content'].replace('\n', '')).decode()
        if remote.strip() == correct_content.strip():
            print(f'  [{repo_name}] check_parser.yml актуален ✓')
            return
        sha = existing['sha']
        msg = 'fix: обновить check_parser.yml до актуальной версии'
    else:
        sha = None
        msg = 'feat: добавить check_parser.yml для самопроверки'

    body = {'message': msg, 'content': correct_b64}
    if sha:
        body['sha'] = sha

    result = gh_api(api_path, method='PUT', body=body)
    if '_error' in result:
        print(f'  [{repo_name}] ❌ Ошибка {result["_error"]}: {result["_msg"][:120]}')
    else:
        print(f'  [{repo_name}] ✅ check_parser.yml задеплоен')


if __name__ == '__main__':
    if not TOKEN:
        print('Нужен GH_TOKEN с scope: repo + workflow')
        sys.exit(1)

    repos = get_student_repos()
    print(f'Студентов: {len(repos)}')
    for r in repos:
        deploy_to(r)
    print('Готово.')
