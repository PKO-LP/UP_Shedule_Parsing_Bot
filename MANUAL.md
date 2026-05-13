# Руководство: система автопроверки учебных заданий через GitHub Actions

Это инструкция для преподавателя, который хочет повторить систему с нуля под своё задание.

---

## Что получится в итоге

- Репозиторий с заданием для студентов (шаблон кода + README с ТЗ)
- Студент пушит своё решение → через ~2 часа в его репо автоматически появляется `REVIEW.md` с разбором ошибок
- Всё работает на серверах GitHub 24/7 — твой ноутбук не нужен

---

## Шаг 1 — Создать организацию на GitHub

> Если организация уже есть — переходи к шагу 2.

1. Зайди на https://github.com
2. Нажми на аватар (правый верхний угол) → **Your organizations**
3. Нажми **New organization**
4. Выбери план **Free**
5. Введи имя организации (например `PKO-LP`) → **Create organization**
6. Остальные шаги можно пропустить (Skip)

---

## Шаг 2 — Создать главный репозиторий с заданием

1. Зайди на страницу организации: `https://github.com/ИМЯ_ОРГАНИЗАЦИИ`
2. Нажми **New repository** (зелёная кнопка)
3. Заполни:
   - **Repository name**: любое, например `UP_Shedule_Parsing_Bot`
   - **Description**: краткое описание задания
   - **Public** (чтобы студенты могли читать)
   - Поставь галочку **Add a README file**
4. Нажми **Create repository**

---

## Шаг 3 — Склонировать репо на ноутбук и наполнить содержимым

```bash
git clone https://github.com/ИМЯ_ОРГАНИЗАЦИИ/ИМЯ_РЕПО.git
cd ИМЯ_РЕПО
```

Что положить в репо:

| Файл | Содержимое |
|------|-----------|
| `README.md` | ТЗ для студентов: что делать, API, требования, шаблон имени репо |
| `parser.py` | Шаблон кода с задачами для студента (см. раздел «Формат задания» ниже) |
| `checker.py` | Скрипт автопроверки (см. раздел «Написать checker.py» ниже) |
| `scan_students.py` | Скрипт сканирования всех репо студентов (копируй из этого проекта, меняй только `REPO_PATTERN`) |
| `assets/` | Скриншоты для README (необязательно) |

```bash
git add .
git commit -m "initial: задание и автопроверка"
git push
```

---

## Шаг 4 — Формат задания для студентов (parser.py)

Лучший формат — **два варианта на выбор**, один верный, один нет. Студент раскомментирует правильный:

```python
# Пример структуры данных от API:
# { "data": { "id": 123 } }
#
# Раскомментируй ОДНУ правильную строку:
# result = response.json()["result"]["id"]   # вариант А
# result = response.json()["data"]["id"]     # вариант Б
```

Почему это лучше чем `????`:
- Студент не может угадать синтаксис — только осмыслить
- Checker однозначно проверяет: какой вариант раскомментирован
- Понятна цена ошибки: неверный вариант — сразу видно почему

---

## Шаг 5 — Написать checker.py

`checker.py` анализирует код студента **без его запуска** — через AST (дерево разбора Python).

Базовая структура:

```python
import ast, sys
from pathlib import Path
from datetime import datetime

_errors = []
_ok = []

def check(tree):
    # Пример: проверить что используется ключ "data", а не "result"
    for node in ast.walk(tree):
        if isinstance(node, ast.Subscript):
            if isinstance(node.slice, ast.Constant):
                key = node.slice.value
                if key == "data":
                    _ok.append({"step": "Шаг 1", "value": 'response["data"]'})
                elif key == "result":
                    _errors.append({
                        "step": "Шаг 1", "line": node.lineno,
                        "found": '["result"]',
                        "expected": '["data"]',
                        "hint": 'Верхний ключ называется "data". Раскомментируй вариант Б.'
                    })

def main():
    filepath = sys.argv[1] if len(sys.argv) > 1 else 'solution.py'
    source = Path(filepath).read_text(encoding='utf-8')
    tree = ast.parse(source)
    check(tree)
    # ... генерация REVIEW.md ...
    sys.exit(1 if _errors else 0)

if __name__ == '__main__':
    main()
```

Полный рабочий пример — смотри `checker.py` в этом проекте.

**Что умеет AST:**
- Находить обращения к словарю: `node["key"]` → `ast.Subscript`
- Находить вызовы метода: `.get("key", ...)` → `ast.Call` с `ast.Attribute`
- Находить условия: `if "text" in x.lower()` → `ast.Compare`
- Находить присваивания, импорты, функции, циклы — всё

---

## Шаг 6 — Добавить GitHub Actions workflow (автосканер)

Создай файл `.github/workflows/scan_students.yml` в главном репо:

```yaml
name: Автосканер репозиториев студентов

on:
  schedule:
    - cron: '0 */2 * * *'   # каждые 2 часа
  workflow_dispatch:         # вручную

permissions:
  contents: read

jobs:
  scan:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      - name: Сканировать студентов
        env:
          GH_TOKEN: ${{ secrets.ORG_REVIEW_TOKEN }}
          ORG: ИМЯ_ОРГАНИЗАЦИИ
          REPO_PATTERN: '^UP_06_\d{2}-\d{2}-\d{4}_[A-Za-z]+_[A-Za-z]+_32ISd$'
        run: python scan_students.py
```

Поменяй `ORG` и `REPO_PATTERN` под своё задание.

**Шаблон имени репо студента** — рекомендуемый формат:
```
UP_NN_ДД-ММ-ГГГГ_Name_Surname_ГруппаЛатиницей
```
Где `NN` — номер практики. Например: `UP_06_12-05-2026_Ivan_Petrov_32ISd`

---

## Шаг 7 — Создать Personal Access Token

1. Зайди на https://github.com/settings/tokens
2. Нажми **Generate new token (classic)**
3. Название: `org-review-bot` (или любое)
4. Срок: **No expiration** (или 1 год)
5. Галочки:
   - ✅ `repo` (весь блок)
   - ✅ `read:org` (подпункт в блоке `admin:org`)
6. Нажми **Generate token**
7. **Скопируй токен** — он показывается один раз

---

## Шаг 8 — Добавить токен как секрет репо

### Вариант А — через браузер (ручной)

1. Открой главное репо → **Settings** → **Secrets and variables** → **Actions**
2. Нажми **New repository secret**
3. Name: `ORG_REVIEW_TOKEN`
4. Secret: вставь токен
5. Нажми **Add secret**

### Вариант Б — через скрипт (автоматический)

Установи PyNaCl:
```bash
pip install PyNaCl
```

Запусти (подставь свои данные):
```python
import os, json, base64, urllib.request
from nacl import encoding, public

TOKEN       = "ghp_ВАШ_ТОКЕН"
OWNER       = "ИМЯ_ОРГАНИЗАЦИИ"
REPO        = "ИМЯ_РЕПО"
SECRET_NAME = "ORG_REVIEW_TOKEN"

def api(method, path, data=None):
    url = f'https://api.github.com{path}'
    req = urllib.request.Request(
        url, data=json.dumps(data).encode() if data else None,
        method=method,
        headers={
            'Authorization': f'Bearer {TOKEN}',
            'Accept': 'application/vnd.github+json',
            'X-GitHub-Api-Version': '2022-11-28',
            'Content-Type': 'application/json',
        }
    )
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read())

pk = api('GET', f'/repos/{OWNER}/{REPO}/actions/secrets/public-key')
pub = public.PublicKey(pk['key'].encode(), encoding.Base64Encoder())
encrypted = base64.b64encode(public.SealedBox(pub).encrypt(TOKEN.encode())).decode()

api('PUT', f'/repos/{OWNER}/{REPO}/actions/secrets/{SECRET_NAME}', {
    'encrypted_value': encrypted,
    'key_id': pk['key_id'],
})
print('Секрет добавлен')
```

---

## Шаг 9 — Добавить студентов в организацию

Чтобы студенты могли создавать репозитории в организации:

1. Зайди на страницу организации → вкладка **Members**  
   `https://github.com/orgs/ИМЯ_ОРГАНИЗАЦИИ/people`
2. Нажми **Invite member**
3. Введи GitHub-логин студента → **Send invitation**
4. Студент принимает приглашение

Или выдай студенту права создания репо без вступления:
- Settings организации → **Member privileges** → **Repository creation** → выбери **Public**

---

## Шаг 10 — Инструктировать студентов

Студент должен:

1. Создать репозиторий в организации по шаблону имени:
   ```
   UP_06_12-05-2026_Ivan_Petrov_32ISd
   ```
2. Склонировать главное репо и скопировать `parser.py` себе:
   ```bash
   git clone https://github.com/ИМЯ_ОРГАНИЗАЦИИ/ИМЯ_РЕПО.git
   ```
3. Дописать/раскомментировать код в `parser.py`
4. Запушить в своё репо:
   ```bash
   git add parser.py
   git commit -m "solution"
   git push
   ```
5. Через ~2 часа в его репо появится `REVIEW.md` — открыть и прочитать результат

---

## Шаг 11 — Дать студентам кнопку самопроверки

Студент может в любой момент запустить проверку **прямо в своём репо** через вкладку Actions — без ожидания 2 часов.

### Что нужно студенту сделать один раз:

1. В своём репо создать папки `.github/workflows/`
2. Скопировать туда файл `assets/check_parser.yml` из главного репо под именем `check_parser.yml`
3. Закоммитить и запушить:
   ```bash
   git add .github/
   git commit -m "add: self-check workflow"
   git push
   ```
4. Открыть свой репо → вкладка **Actions** → **"Проверить parser.py"** → **Run workflow**

Через ~30 секунд в репо появится обновлённый `REVIEW.md` с результатом.

> Workflow скачивает актуальный `checker.py` и `check_rules.json` из главного репо, поэтому студенту ничего обновлять не нужно — правила всегда свежие.

---

## Структура файлов итогового проекта

```
главное-репо/
├── .github/
│   └── workflows/
│       └── scan_students.yml   ← автосканер всех студентов
├── assets/
│   └── check_parser.yml        ← workflow для самопроверки студента (Шаг 11)
├── parser.py                   ← шаблон задания для студентов
├── checker.py                  ← скрипт автопроверки (AST)
├── scan_students.py            ← скрипт сканирования репо
└── README.md                   ← ТЗ и инструкция для студентов
```

Репо каждого студента (добавляется автоматически):
```
студенческое-репо/
├── .github/
│   └── workflows/
│       └── check_parser.yml    ← кнопка самопроверки (студент добавляет сам, Шаг 11)
├── parser.py                   ← решение студента
└── REVIEW.md                   ← автоматически добавляется checker'ом
```

---

## Часто задаваемые вопросы

**Q: Нужен ли мой ноутбук для работы проверки?**  
A: Нет. GitHub Actions работает на серверах GitHub 24/7. После настройки система полностью автономна.

**Q: Что если студент неправильно назвал репо?**  
A: Сканер его просто не найдёт — `REVIEW.md` не появится. В README чётко написан шаблон имени.

**Q: Можно ли запустить проверку вручную не дожидаясь 2 часов?**  
A: Да. Зайди в главное репо → вкладка **Actions** → **Автосканер репозиториев студентов** → **Run workflow**.

**Q: Как обновить логику проверки для всех студентов сразу?**  
A: Просто обнови `checker.py` в главном репо и запуши. При следующем запуске Actions скачает новую версию.

**Q: Токен истёк — что делать?**  
A: Создай новый токен (Шаг 7), удали старый секрет и добавь новый (Шаг 8).

**Q: Могут ли студенты сами проверить своё задание не дожидаясь сканера?**  
A: Да — если они добавили `check_parser.yml` в своё репо (Шаг 11). Открывают своё репо → **Actions** → **«Проверить parser.py»** → **Run workflow**. Через ~30 секунд REVIEW.md обновится.
