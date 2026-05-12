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
# ✏️  НУЖНО ДОПИСАТЬ — замени все ???? на правильные ключи из JSON
# ══════════════════════════════════════════════════════════════════════════════

def parse_schedule_files() -> list[dict[str, Any]]:

    # ── Шаг 1: получаем ID страницы ───────────────────────────────────────────
    response = requests.post(BASE_URL + '/v1/api/page/id', json={'path': PAGE_PATH})

    # Ответ сервера выглядит так:
    # { "data": { "id": 30190, "title": "Расписание..." } }
    #              ↑                ↑
    #          первый ключ      второй ключ
    page_id = response.json()[????][????]

    # ── Шаг 2: получаем дерево папок и файлов ────────────────────────────────
    response = requests.get(BASE_URL + f'/v1/api/folder_and_file/list/{page_id}')

    # Ответ сервера выглядит так:
    # { "data": { "folders": [ ... ], "files": [ ... ] } }
    #              ↑              ↑
    #          первый ключ    второй ключ
    folders = response.json()[????][????]

    # ── Шаг 3: ищем папку «Расписание учебных занятий» ───────────────────────
    schedule_folder: dict[str, Any] | None = None

    for folder in folders:
        # Каждая папка в списке выглядит так:
        # { "id": 778, "title": "Расписание учебных занятий", "folders": [...] }
        #                ↑
        #             этот ключ
        if 'расписание учебных' in str(folder[????]).lower():
            schedule_folder = folder
            break

    if schedule_folder is None:
        return []

    # ── Шаг 4: внутри папки расписания ищем нужный корпус ────────────────────
    files: list[dict[str, Any]] = []

    # Каждая папка расписания содержит вложенные папки корпусов:
    # { "title": "Расписание учебных занятий", "folders": [ {корпус1}, {корпус2} ... ] }
    #                                              ↑
    #                                           этот ключ
    for korpus in schedule_folder[????]:

        # Каждый корпус выглядит так:
        # { "id": 790, "title": "Корпус Ярославский", "files": [...] }
        #                ↑
        #             этот ключ
        if korpus[????] != KORPUS:
            continue

        # Внутри каждого корпуса список файлов:
        # { "title": "Корпус Ярославский", "files": [ {файл1}, {файл2} ... ] }
        #                                      ↑
        #                                   этот ключ
        for f in korpus[????]:

            # Каждый файл выглядит так:
            # {
            #   "id":    8491,
            #   "title": "1 курс",
            #   "src":   "/attach_files/upload_users_files/6998081244da6.xlsx",
            #   "ext":   "xlsx"
            # }
            #     ↑         ↑             ↑                                  ↑
            #  id файла  название      путь к файлу                     расширение

            # f["title"] == "1 курс" → берём первый символ → int("1") == 1
            #       ↑
            #   этот ключ
            course = int(str(f[????])[0])

            files.append({
                'file_id': int(f[????]),       # ключ: числовой ID файла
                'course':  course,
                'src':     str(f[????]),        # ключ: путь к файлу на сервере (меняется при обновлении)
                'ext':     str(f.get(????, 'xlsx')),  # ключ: расширение файла; если его нет — по умолчанию xlsx
                'url':     BASE_URL + str(f[????]),   # ключ: тот же путь, только добавляем к нему BASE_URL
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
