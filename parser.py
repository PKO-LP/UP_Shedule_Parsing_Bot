import os
import json
from typing import Any
import requests


BASE_URL   = 'https://spo-13.mskobr.ru'
PAGE_PATH  = '/uchashimsya/raspisanie-kanikuly'
KORPUS     = 'Корпус Ярославский'
CACHE_FILE = 'cache_index.json'


# ══════════════════════════════════════════════════════════════════════════════
# ФУНКЦИЯ 1 — parse_schedule_files
#
# ✏️  ТВОЯ ЗАДАЧА: раскомментировать правильные строки в каждом шаге.
#     Закомментированных вариантов два — только один верный.
#     Неверный оставь закомментированным, верный — раскомментируй.
# ══════════════════════════════════════════════════════════════════════════════

def parse_schedule_files() -> list[dict[str, Any]]:

    # ── Шаг 1: получаем ID страницы ───────────────────────────────────────────
    response = requests.post(BASE_URL + '/v1/api/page/id', json={'path': PAGE_PATH})

    # Сервер возвращает:
    # { "data": { "id": 30190, "title": "Расписание..." } }
    #
    # Раскомментируй ОДНУ правильную строку:
    # page_id = response.json()["result"]["id"]   # вариант А
    # page_id = response.json()["data"]["id"]     # вариант Б

    # ── Шаг 2: получаем дерево папок и файлов ────────────────────────────────
    response = requests.get(BASE_URL + f'/v1/api/folder_and_file/list/{page_id}')

    # Сервер возвращает:
    # { "data": { "folders": [ ... ], "files": [ ... ] } }
    #
    # Раскомментируй ОДНУ правильную строку:
    # folders = response.json()["data"]["items"]    # вариант А
    # folders = response.json()["data"]["folders"]  # вариант Б

    # ── Шаг 3: ищем папку «Расписание учебных занятий» ───────────────────────
    schedule_folder: dict[str, Any] | None = None

    for folder in folders:
        # Каждая папка выглядит так:
        # { "id": 778, "title": "Расписание учебных занятий", "folders": [...] }
        #
        # Раскомментируй ОДНУ правильную строку:
        # if 'расписание учебных' in str(folder["id"]).lower():     # вариант А
        # if 'расписание учебных' in folder["title"].lower():       # вариант Б
            schedule_folder = folder
            break

    if schedule_folder is None:
        return []

    # ── Шаг 4: внутри папки расписания ищем нужный корпус ────────────────────
    files: list[dict[str, Any]] = []

    # Структура папки расписания:
    # { "title": "Расписание учебных занятий", "folders": [ {корпус1}, {корпус2} ... ] }
    #
    # Раскомментируй ОДНУ правильную строку:
    # for korpus in schedule_folder["files"]:    # вариант А
    # for korpus in schedule_folder["folders"]:  # вариант Б

        # Каждый корпус выглядит так:
        # { "id": 790, "title": "Корпус Ярославский", "files": [...] }
        #
        # Раскомментируй ОДНУ правильную строку:
        # if korpus["id"] != KORPUS:      # вариант А
        # if korpus["title"] != KORPUS:   # вариант Б
            continue

        # Каждый файл внутри корпуса выглядит так:
        # {
        #   "id":    8491,
        #   "title": "1 курс",
        #   "src":   "/attach_files/upload_users_files/6998081244da6.xlsx",
        #   "ext":   "xlsx"
        # }
        #
        # Раскомментируй ОДНУ правильную строку:
        # for f in korpus["folders"]:   # вариант А
        # for f in korpus["files"]:     # вариант Б

            # f["title"] == "1 курс" → берём первый символ → int("1") == 1
            #
            # Раскомментируй ОДНУ правильную строку:
            # course = int(str(f["id"])[0])     # вариант А
            # course = int(str(f["title"])[0])  # вариант Б

            files.append({
                # Раскомментируй ОДНУ правильную строку в каждой паре:

                # 'file_id': int(f["title"]),   # вариант А — числовой ID файла
                # 'file_id': int(f["id"]),       # вариант Б — числовой ID файла
                'course':  course,

                # 'src': str(f["id"]),           # вариант А — путь к файлу на сервере
                # 'src': str(f["src"]),          # вариант Б — путь к файлу на сервере

                # 'ext': str(f.get("id",  'xlsx')),   # вариант А — расширение файла
                # 'ext': str(f.get("ext", 'xlsx')),   # вариант Б — расширение файла

                # 'url': BASE_URL + str(f["ext"]),    # вариант А — полный URL файла
                # 'url': BASE_URL + str(f["src"]),    # вариант Б — полный URL файла
            })

    return files


# ══════════════════════════════════════════════════════════════════════════════
# ФУНКЦИЯ 2 — is_new_file
# ✅ ГОТОВА — ничего менять не нужно, просто разберись как работает
# ══════════════════════════════════════════════════════════════════════════════

def is_new_file(file_id: int, src: str) -> bool:

    if not os.path.exists(CACHE_FILE):
        return True

    with open(CACHE_FILE, encoding='utf-8') as f:
        cache = json.load(f)

    # Кеш выглядит так: { "8491": "/attach_files/.../6998081244da6.xlsx", ... }
    #                       ↑ ключ (ID файла)        ↑ значение (src — путь к файлу)
    #
    # cache.get(str(file_id)) — берём из кеша сохранённый src по ID файла
    # Если он не совпадает с текущим src из API — значит файл на сайте обновился → True
    # Если совпадает — файл не менялся → False
    return bool(cache.get(str(file_id)) != src)


# ══════════════════════════════════════════════════════════════════════════════
# ФУНКЦИЯ 3 — cache_file
# ✅ ГОТОВА — ничего менять не нужно, просто разберись как работает
# ══════════════════════════════════════════════════════════════════════════════

def cache_file(file_id: int, course: int, src: str, url: str, ext: str) -> str:

    folder = f'c{course}'
    os.makedirs(folder, exist_ok=True)

    file_path: str = os.path.join(folder, f'kurs{course}.{ext}')

    response = requests.get(url)
    with open(file_path, 'wb') as f:
        f.write(response.content)

    cache = {}
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, encoding='utf-8') as f:
            cache = json.load(f)

    cache[str(file_id)] = src

    with open(CACHE_FILE, 'w', encoding='utf-8') as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)

    return file_path


# ══════════════════════════════════════════════════════════════════════════════
# ТОЧКА ВХОДА
# ══════════════════════════════════════════════════════════════════════════════

files = parse_schedule_files()
print(f'Найдено файлов ({KORPUS}): {len(files)}\n')

for f in files:
    if is_new_file(f['file_id'], f['src']):
        path = cache_file(f['file_id'], f['course'], f['src'], f['url'], f['ext'])
        print(f'Скачан: {path}  ({f["url"]})')
    else:
        print(f'Без изменений: c{f["course"]}/kurs{f["course"]}.{f["ext"]}')
