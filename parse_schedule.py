# -*- coding: utf-8 -*-
"""
parse_schedule.py — выгрузка расписания из источников в формат хаба.

ДВА ИСТОЧНИКА (выбираются автоматически по домену, --nikasoft — принудительно):

ГЛАВНЫЙ — Google Таблицы (URL с docs.google.com), доступ «по ссылке»:
  Реальные расписания лежат во вкладках с датами: «понедельник 6.09»,
  «вторник 22.09.2026», «Среда 23.09.2026», «пятница 25.09.26», «Суббота 26.09.26».
  Скрипт:
    1) берёт текущую дату (datetime.now) или --date YYYY-MM-DD,
    2) вычисляет понедельник этой недели,
    3) парсит дату из названий вкладок (форматы: 6.09, 28.09.26, 22.09.2026,
       24,09 — с запятой вместо точки; год может отсутствовать),
    4) отбирает вкладки за неделю (пн..сб), проверяя, что день недели
       в названии совпадает с реальной датой (отсекает «старые»/дубли-вкладки),
    5) собирает колонку класса (по умолчанию 7А) по дням,
    6) если вкладок на неделю нет — печатает «Не найдено расписание на текущую
       неделю. Доступные даты: ...».

ВТОРОЙ — raspisanie.nikasoft.ru (URL вида https://raspisanie.nikasoft.ru/{id}.html):
  1) качает HTML страницы, регуляркой достаёт initial_schedule_id,
  2) качает файл данных /static/public/{schedule_id} (JSON-объект в var NIKA=),
  3) если JSON не парсится — пробует js2py, затем headless-рендер (Playwright)
     и читает window.NIKA,
  4) ищет класс по имени в NIKA.CLASSES и берёт его шаблон недели
     из CLASS_SCHEDULE[период][class] (ключи «день+урок», напр. «106»),
     на даты применяет замены CLASS_EXCHANGE[class][дата] («F» — урок отменён,
     урок пропускается), каникулы HOLIDAY_TRANSFER[дата].type=vacation,
  5) для каждого дня выбирается свой период (PERIODS с датами b/e),
     время урока — из LESSON_TIMES[номер урока].
  --list с URL nikasoft печатает доступные классы.

ОБЩЕЕ ДЛЯ ОБОИХ ИСТОЧНИКОВ:
  Каждый урок получает время начала-конца из источника
  (формат «08:15-08:55 Геометрия 35», для nikasoft «12:15-12:55 Литература 35»);
  уроки-«окна» (клетки «окно») в расписание не попадают.

  ЗАГРУЗКА В FIREBASE — ПО УМОЛЧАНИЮ: каждая обработка (обычный режим,
  --all-classes/--grade/--classes, старый --sheet) заливает расписание в
  Firebase (cities/{cid}/schools/{sid}/classes/{clid}/schedule). Узел
  ПЕРЕЗАПИСЫВАЕТСЯ целиком (PUT) — старые данные удаляются, чтобы не копить
  место. Флаг --no-push отключает загрузку (например для пробы).

  РАЗНЫЕ ШКОЛЫ (--school): расписания из Google-листа и из raspisanie.nikasoft.ru
  принадлежат РАЗНЫМ школам (Google — «Школа №12», nikasoft — «Школа №25»);
  в Firebase классы могут называться одинаково. Чтобы не писать расписание
  одной школы в класс другой, укажите --school "<подстрока названия школы>"
  (например --school "Школа №25"). Узел в этом случае ищется только внутри
  выбранной школы; классы, которых в ней нет, пропускаются. Без --school
  совпадение имени в нескольких школах считается неоднозначным и пропускается
  с предупреждением. Домашние названия можно узнать: python parse_schedule.py
  --school "<любое>" ... (выводится ошибка со списком существующих школ).
  В расписании из nikasoft имя школы берётся из его данных.

  СЛЕЖЕНИЕ (--watch): периодическая перепроверка. --watch [СЕКУНД] собирает
  расписание каждые N секунд (по умолчанию 900 = 15 минут) и загружает в
  Firebase ТОЛЬКО если данные изменились (по дайджесту записанных файлов).
  Работает с обоими источниками; прерывается по Ctrl+C. Пример:
      python parse_schedule.py --watch 900 --school "Школа №25"
      python parse_schedule.py --watch 900 --school "Школа №12" --create-classes

  URL источника можно задать позиционно либо флагом --nikasoft-url:
      python parse_schedule.py --all-classes --nikasoft-url "https://..."
  Если URL не передан вовсе, по умолчанию берётся расписание школы №25
  «Гелиос» (https://raspisanie.nikasoft.ru/86111512.html). Примеры без URL:
      python parse_schedule.py --all-classes --school "Школа №25" --create-classes
      python parse_schedule.py --grade 7 --school "Школа №25"

  АВТО-СОЗДАНИЕ КЛАССОВ (--create-classes): используется вместе с --school.
  Если класс из расписания не найден в Firebase-школе — его узел создаётся
  автоматически (класы-имя + /schedule) вместо пропуска с предупреждением.
  ВАЖНО: применимо обычно к nikasoft (где список классов берётся из данных
  сайта); для Google-листа --all-classes найдёт все параллели из вкладок, и
  без фильтрации (--grade/--classes) создаст классы всех этих параллелей.

  --week   принудительно взять текущую неделю,
  --date YYYY-MM-DD — взять неделю, содержащую указанную дату,
  --sheet "<подстрока>" — старый режим Google: разбирать конкретную «недельную»
       вкладку (например "неделя (2 четверть)") из таблицы.

РЕЖИМ ВСЕХ КЛАССОВ (--all-classes / --grade / --classes) — оба источника:
  За один проход собирает расписания нескольких классов (для Google — из
  вкладок недели, для nikasoft — из CLASSES) и сохраняет: 
    schedule_all.json            — { "week": "...", "classes": { "7А": {...}, ... } }
    schedule_<КЛАСС>.json        — по одному файлу на класс
  --all-classes — все классы, найденные в шапках вкладок недели,
  --grade 7     — только параллель (находит классы и фильтрует по номеру),
  --classes 7А,7Б,7В — явный список (через запятую).
  Если колонка класса не найдена ни в одной вкладке — класс пропускается
  с предупреждением. Нельзя комбинировать multi-режим с --sheet.
  Все найденные классы заливаются в Firebase отдельными узлами /schedule
  (узел ищется по имени класса); классы, отсутствующие в Firebase,
  пропускаются с предупреждением. Отключить загрузку — --no-push.

Источники (по порядку):
  0. requests -> export?format=xlsx (все листы воркбука, без авторизации)
  1. requests -> pandas.read_html (/edit, /htmlview ...)
  2. Selenium headless (Edge/Chrome, инкогнито, свежий профиль)
  3. Playwright headless (свежий контекст)

Результат: schedule.json в формате хаба
    { "class": "7А", "days": { "mon": ["08:15-08:55 Геометрия 35", ...],
                               "tue": [...], ... } }

Примеры:
    python parse_schedule.py "URL"
    python parse_schedule.py --date 2026-09-18 --class 7Б --out s7b.json "URL"
    python parse_schedule.py --week --no-push "URL"
    python parse_schedule.py --list "URL"
    python parse_schedule.py --sheet "2 четверть" "URL"
    python parse_schedule.py --all-classes "URL"
    python parse_schedule.py --all-classes --grade 7 "URL"
    python parse_schedule.py --classes 7А,7Б,7В --no-push "URL"
    python parse_schedule.py --local schedule.csv
    # nikasoft
    python parse_schedule.py --list https://raspisanie.nikasoft.ru/86111512.html
    python parse_schedule.py --class 7А https://raspisanie.nikasoft.ru/86111512.html
    python parse_schedule.py --class 7А --no-push https://raspisanie.nikasoft.ru/86111512.html
    # все классы школы №25 одним запуском (URL по умолчанию; без URL тоже работает):
    python parse_schedule.py --all-classes --school "Школа №25" --create-classes
    python parse_schedule.py --all-classes --school "Школа №25" --no-push
    python parse_schedule.py --grade 6 --school "Школа №25" --no-push
    # разделение школ и слежение
    python parse_schedule.py --watch --school "Школа №25"
    python parse_schedule.py --watch --school "Школа №12"
"""

import argparse
import datetime
import io
import json
import os
import re
import sys
import tempfile
import time

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

DAY_MAP = [
    (re.compile(r"понед", re.I), "mon"),
    (re.compile(r"вторн", re.I), "tue"),
    (re.compile(r"сред", re.I), "wed"),
    (re.compile(r"четверг", re.I), "thu"),
    (re.compile(r"пятниц", re.I), "fri"),
    (re.compile(r"суббот", re.I), "sat"),
    (re.compile(r"воскрес", re.I), "sun"),
]
HUB_KEYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
DAY_NAMES = {"mon": "понедельник", "tue": "вторник", "wed": "среда",
             "thu": "четверг", "fri": "пятница", "sat": "суббота",
             "sun": "воскресенье"}
PY_KEYS = {"mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4,
           "sat": 5, "sun": 6}

CLASS_CELL = re.compile(r"^(\d{1,2})\s*[-\s]?\s*([а-яА-Я])$")
LESSON_NO = re.compile(r"^\d{1,2}(\.\d+)?$")
TIME_TXT = re.compile(r"^\d{1,2}[:.]\d{2}\s*[-–—]\s*\d{1,2}[:.]\d{2}")
DATE_IN_NAME = re.compile(
    r"(?:понед|вторн|сред|четверг|пятниц|суббот|воскрес)\w*\s*"
    r"(\d{1,2})\s*[.,]\s*(\d{1,2})\s*(?:[.,]\s*(\d{2,4}))?",
    re.I)

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")


def sheet_id_from_url(url):
    m = re.search(r"/d/([-\w]{20,})", url or "")
    return m.group(1) if m else None


def norm_key(s):
    return re.sub(r"\s+", "", str(s or "")).lower()


def clean_rows(rows):
    rows = [
        [None if c is None else str(c).replace("\xa0", " ").strip() for c in r]
        for r in rows
    ]
    maxcol = 0
    for r in rows:
        cols = [i for i, c in enumerate(r) if c]
        if cols:
            maxcol = max(maxcol, cols[-1] + 1)
    trimmed = [r[:maxcol] if maxcol else r for r in rows]
    return [r for r in trimmed if any(c for c in r)]


def day_key_from_name(name):
    for rx, key in DAY_MAP:
        if rx.search(name):
            return key
    return None


def parse_tab_date(name):
    """Разбирает «вторник 22.09.2026» / «пятница 24,09» и т.п.

    Возвращает (day_key, datetime.date) или None.
    День недели в названии должен совпадать с реальной датой:
    для не_явного года перебираем текущий ±2 года, иначе вкладку отбрасываем.
    """
    name = (name or "").strip()
    m = DATE_IN_NAME.search(name)
    if not m:
        return None
    d, mo = int(m.group(1)), int(m.group(2))
    if not (1 <= d <= 31 and 1 <= mo <= 12):
        return None
    key = day_key_from_name(name)
    if key is None:
        return None
    today = datetime.date.today()
    if m.group(3):
        yr = int(m.group(3))
        year = 2000 + yr if yr < 100 else yr
        cands = [year]
    else:
        cands = [today.year + dy for dy in (-2, -1, 0, 1, 2)]
    best = None
    for y in cands:
        try:
            dt = datetime.date(y, mo, d)
        except ValueError:
            continue
        if dt.weekday() == PY_KEYS[key]:
            # предпочитаем ближайший к текущему году
            if best is None or abs(y - today.year) < abs(best.year - today.year):
                best = dt
    return (key, best) if best else None


def is_window_cell(cell):
    """Урок-«окно» (свободное окошко без занятия) в расписание не попадает."""
    return cell is not None and norm_key(cell) == "окно"


_TIME_PART = re.compile(r"^(\d{1,2})[.,](\d{1,2})$")


def fmt_time(cell):
    """«8.15 - 08.55» / «09.05 - 09.45» -> «08:15-08:55».

    Минуты должны задаваться двумя цифрами (иначе ячейку временем
    не считаем и возвращаем "").
    """
    if cell is None:
        return ""
    t = str(cell).replace("\xa0", " ").strip()
    parts = [p.strip() for p in re.split(r"-|–|—", t) if p.strip()]
    out = []
    for p in parts:
        m = _TIME_PART.match(p)
        if not m or len(m.group(2)) < 2:
            return ""
        h, mi = int(m.group(1)), int(m.group(2))
        if not (0 <= h <= 23 and 0 <= mi <= 59):
            return ""
        out.append(f"{h:02d}:{mi:02d}")
    return "-".join(out)


def extract_class_day(rows, class_name):
    """Из матрицы ОДНОЙ датированной вкладки достаёт уроки класса.

    Расклад: ячейка даты, строка с названиями классов («5а … 7 а …»),
    далее строки уроков: <номер> | <время> | <клетки классов>.
    Возвращает (lessons, найдена_ли_колонка_класса).
    """
    target = norm_key(class_name)
    hcol = None
    for r in rows[:10]:
        for ci, c in enumerate(r):
            if c and norm_key(c) == target:
                hcol = ci
                break
        if hcol is not None:
            break
    if hcol is None:
        return [], False
    lessons = []
    for r in rows:
        if len(r) <= hcol:
            continue
        num = r[0] if r else None
        if num is None or not LESSON_NO.match(str(num).strip()):
            continue
        cell = r[hcol]
        if cell is None or not str(cell).strip():
            continue
        t = str(cell).replace("\xa0", " ").strip()
        if is_window_cell(t):
            continue
        if t and not LESSON_NO.match(t) and not TIME_TXT.match(t):
            t2 = fmt_time(r[1]) if len(r) > 1 else ""
            lessons.append((f"{t2} {t}" if t2 else t).strip())
    return lessons, True


def select_week_tabs(sheets, week_start, week_end, year):
    """Отбирает вкладки за неделю [week_start .. week_end].

    Возвращает список (day_key, datetime.date, название, strict: bool).

    Проход 1 (строгий): день недели в названии совпадает с фактической датой
    этой же недели (вкладки с явным годом вида «вторник 22.09.2026»).
    Если строгий проход что-то нашёл — legacy-вкладки не добавляем, чтобы
    не «перекрыть» корректные дни случайными листами.

    Проход 2 (запасной): включается ТОЛЬКО если строгий проход пуст.
    Берёт вкладки, чья дата попадает в неделю, слот дня — из названия
    (для legacy-серий вида «вторник 14.09», где дата не совпадает с днём).
    """
    good, loose = [], []
    for nm, _m in sheets:
        r = parse_tab_date(nm)
        if r and week_start <= r[1] <= week_end:
            good.append((r[0], r[1], nm))
            continue
        m = DATE_IN_NAME.search((nm or "").strip())
        if not m:
            continue
        d, mo = int(m.group(1)), int(m.group(2))
        if not (1 <= d <= 31 and 1 <= mo <= 12):
            continue
        key = day_key_from_name(nm)
        if key is None:
            continue
        if m.group(3):
            yr = int(m.group(3))
            parsed_year = 2000 + yr if yr < 100 else yr
        else:
            parsed_year = year
        try:
            dt = datetime.date(parsed_year, mo, d)
        except ValueError:
            continue
        if week_start <= dt <= week_end:
            loose.append((key, dt, nm))
    if not good:
        by_slot = {}
        for key, dt, nm in loose:
            if key not in by_slot:
                by_slot[key] = (dt, nm)
        return [(key, dt, nm, False)
                for key, (dt, nm) in sorted(by_slot.items(), key=lambda kv: kv[1][0])]
    by_date = {}
    for key, dt, nm in good:
        by_date.setdefault(dt, (key, nm))
    return [(key, dt, nm, True) for dt, (key, nm) in sorted(by_date.items())]


# ---------------- Режим всех классов (--all-classes / --grade / --classes) --

def normalize_class_display(cell):
    """'7 а' / '7А' / '11 Б' -> '7А' / '11Б' (нормализованное имя класса)."""
    m = CLASS_CELL.match(str(cell or "").strip())
    return (m.group(1) + m.group(2).upper()) if m else None


def grade_of(name):
    m = re.match(r"^(\d{1,2})", str(name or "").strip())
    return m.group(1) if m else None


def discover_classes(matrices):
    """Собирает имена классов из шапок (строки с 3+ ячейками вида «7 а»)."""
    found = {}
    for m in matrices:
        for r in m[:12]:
            hits = [d for c in r if c and (d := normalize_class_display(c))]
            if len(hits) >= 3:
                for d in hits:
                    found[d] = True
    def sort_key(n):
        return (int(grade_of(n) or 0), n[-1:])
    return sorted(found, key=sort_key)


def build_class_weeks(picked, by_name, class_list):
    """Собирает {класс: {mon:[...], ...}} для всех классов по вкладкам недели.

    Возвращает (results, missing), где missing — классы без колонки в таблице.
    """
    results, missing = {}, []
    for cl in class_list:
        days = {k: [] for k in HUB_KEYS}
        col_found = False
        for key, _dt, nm, _s in picked:
            lessons, has_col = extract_class_day(by_name.get(nm, []), cl)
            col_found = col_found or has_col
            days[key] = lessons
        if not col_found:
            missing.append(cl)
            continue
        results[cl] = days
    return results, missing


# ---------------- Попытка 0: XLSX-экспорт всего воркбука ----------------

def fetch_xlsx(sheet_id, out_path):
    import requests
    urls = [
        f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=xlsx",
        f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=xlsx&id={sheet_id}",
    ]
    for u in urls:
        for cookie in (False, True):
            try:
                s = requests.Session()
                s.headers.update({"User-Agent": UA, "Accept-Language": "ru,en;q=0.9"})
                if cookie:
                    s.cookies.set("CONSENT", "YES+cb", domain=".google.com")
                r = s.get(u, timeout=90, allow_redirects=True)
                if r.status_code == 200 and r.content[:2] == b"PK":
                    with open(out_path, "wb") as f:
                        f.write(r.content)
                    return out_path
            except Exception as e:
                print(f"  xlsx -> {type(e).__name__}: {e}")
    return None


def load_xlsx_sheets(path):
    import openpyxl
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    sheets = []
    for ws in wb.worksheets:
        rows = []
        for row in ws.iter_rows(values_only=True):
            rows.append([None if c is None else str(c).replace("\xa0", " ") for c in row])
        sheets.append((ws.title.strip(), clean_rows(rows)))
    wb.close()
    return sheets


def sheets_names_only(path):
    import openpyxl
    wb = openpyxl.load_workbook(path, read_only=True)
    names = [ws.title for ws in wb.worksheets]
    wb.close()
    return names


# ---------------- Старый режим: «недельная» вкладка ----------------

def extract_class_week(rows, class_name):
    """Недельная вкладка: блоки-дни, строка названий классов, строки уроков."""
    target = norm_key(class_name)
    days = {k: [] for k in HUB_KEYS}
    found_blocks = 0
    found_col = False
    n = len(rows)
    i = 0
    while i < n:
        r = rows[i]
        day_key = None
        if r:
            for cell in r[:4]:
                if cell:
                    for rx, k in DAY_MAP:
                        if rx.search(cell) and not CLASS_CELL.match(cell):
                            day_key = k
                            break
                    if day_key:
                        break
        if not day_key:
            i += 1
            continue
        j = i + 1
        hcol = None
        col_row = None
        while j < min(i + 5, n) and col_row is None:
            cand = rows[j]
            if cand and any(CLASS_CELL.match(str(c)) if c else False for c in cand):
                col_row = cand
                for ci, c in enumerate(cand):
                    if c and norm_key(c) == target:
                        hcol = ci
                        found_col = True
                        break
                if hcol is None:
                    for ci, c in enumerate(cand):
                        if c and CLASS_CELL.match(str(c)):
                            hcol = ci
                            break
            j += 1
        if col_row is None:
            i += 1
            continue
        found_blocks += 1
        k = i + 1
        while k < n:
            rr = rows[k]
            if rr:
                is_day = False
                for cell in rr[:4]:
                    if cell:
                        for rx, kk in DAY_MAP:
                            if rx.search(cell) and not CLASS_CELL.match(cell):
                                is_day = True
                                break
                        if is_day:
                            break
                if is_day:
                    break
                num = rr[1] if len(rr) > 1 else None
                if num and LESSON_NO.match(str(num).strip()) is not None:
                    if hcol is not None and len(rr) > hcol + 1:
                        cell = rr[hcol + 1]
                        if cell and not LESSON_NO.match(str(cell).strip()):
                            t = str(cell).replace("\xa0", " ").strip()
                            if not is_window_cell(t):
                                t2 = fmt_time(rr[0]) if rr else ""
                                days[day_key].append(
                                    (f"{t2} {t}" if t2 else t).strip())
            k += 1
        i = k
    return days, found_blocks, found_col


# ---------------- Попытки 1-3 (старая цепочка) ----------------

def fetch_html(url, use_consent=False):
    import requests
    s = requests.Session()
    s.headers.update({"User-Agent": UA, "Accept-Language": "ru,en;q=0.9"})
    if use_consent:
        s.cookies.set("CONSENT", "YES+cb", domain=".google.com")
    r = s.get(url, timeout=30, allow_redirects=True)
    return r.text if r.ok else None


def try_pandas(sheet_id):
    print("Пробую pandas.read_html…")
    urls = [
        f"https://docs.google.com/spreadsheets/d/{sheet_id}/edit?usp=drivesdk",
        f"https://docs.google.com/spreadsheets/d/{sheet_id}/htmlview",
        f"https://docs.google.com/spreadsheets/d/{sheet_id}/htmlview?sle=true",
    ]
    for use_consent in (False, True):
        for u in urls:
            try:
                html = fetch_html(u, use_consent)
                if not html:
                    print(f"  {u} -> пусто")
                    continue
                rows = html_to_rows(html)
                if rows:
                    return rows
            except Exception as e:
                print(f"  {u} -> {type(e).__name__}: {e}")
    return None


def html_to_rows(html):
    import pandas as pd
    tables = pd.read_html(io.StringIO(html))
    for tb in tables:
        rows = clean_rows(tb.values.tolist())
        if rows and any(any(c for c in r) for r in rows):
            return rows
    return None


def try_selenium(sheet_id):
    print("pandas не сработал, переключаюсь на Selenium…")
    try:
        from selenium import webdriver
        from selenium.webdriver.common.by import By
        from selenium.webdriver.common.keys import Keys
        from selenium.webdriver.chrome.options import Options as ChromeOpts
        from selenium.webdriver.edge.options import Options as EdgeOpts
        from selenium.webdriver.support.ui import WebDriverWait
    except ImportError as e:
        print(f"Selenium недоступен ({e}); пропускаю.")
        return None

    driver = None
    try:
        for engine, Opt in (("edge", EdgeOpts), ("chrome", ChromeOpts)):
            opts = Opt()
            opts.add_argument("--headless=new")
            opts.add_argument("--incognito")
            opts.add_argument("--no-sandbox")
            opts.add_argument("--disable-gpu")
            opts.add_argument("--disable-dev-shm-usage")
            opts.add_argument("--window-size=1440,1200")
            opts.add_argument("--user-agent=" + UA)
            prof = tempfile.mkdtemp(prefix="sch_incgn_")
            opts.add_argument("--user-data-dir=" + prof)
            try:
                if engine == "edge":
                    from webdriver_manager.microsoft import EdgeChromiumDriverManager
                    from selenium.webdriver.edge.service import Service
                    drv = EdgeChromiumDriverManager().install()
                    driver = webdriver.Edge(service=Service(drv), options=opts)
                else:
                    from webdriver_manager.chrome import ChromeDriverManager
                    from selenium.webdriver.chrome.service import Service
                    drv = ChromeDriverManager().install()
                    driver = webdriver.Chrome(service=Service(drv), options=opts)
                break
            except Exception as e:
                print(f"  Не удалось запустить {engine}: {type(e).__name__}: {e}")
        if driver is None:
            print("Нет доступного браузера для Selenium.")
            return None

        print("Selenium: загружаю страницу…")
        driver.get(f"https://docs.google.com/spreadsheets/d/{sheet_id}/edit")
        WebDriverWait(driver, 60).until(
            lambda d: d.execute_script(
                "return !!document.querySelector('[role=gridcell]') "
                "|| !!document.querySelector('.waffle')"
            ) is True
        )
        rows = None
        try:
            rows = html_to_rows(driver.page_source)
        except Exception:
            rows = None
        if not rows:
            try:
                grid = driver.find_element(
                    By.CSS_SELECTOR, "div.grid-container, .waffle, [role=grid]")
                driver.execute_script(
                    "arguments[0].setAttribute('tabindex','-1');", grid)
                grid.click()
            except Exception:
                pass
            body = driver.find_element(By.TAG_NAME, "body")
            for _ in range(2):
                body.send_keys(Keys.CONTROL, "a")
                time.sleep(0.4)
                txt = driver.execute_script("return window.getSelection().toString();")
                if txt and len(txt) > 5:
                    rows = clean_rows([[c for c in line.split("\t")]
                                       for line in txt.split("\n")])
                    if rows:
                        break
        if rows:
            return rows
        print("Selenium: таблица не найдена.")
        return None
    except Exception as e:
        print(f"Selenium: ошибка: {type(e).__name__}: {e}")
        return None
    finally:
        if driver is not None:
            try:
                driver.quit()
            except Exception:
                pass


def try_playwright(sheet_id):
    print("Selenium не сработал, переключаюсь на Playwright…")
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as e:
        print(f"Playwright недоступен ({e}); пропускаю.")
        return None
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
            ctx = browser.new_context(storage_state=None, user_agent=UA,
                                      viewport={"width": 1440, "height": 1200})
            page = ctx.new_page()
            page.goto(f"https://docs.google.com/spreadsheets/d/{sheet_id}/edit",
                      wait_until="domcontentloaded", timeout=60000)
            try:
                page.wait_for_selector('[role="gridcell"], .waffle', timeout=60000)
                page.locator("div.grid-container, .waffle, [role=grid]").first.click()
            except Exception:
                pass
            page.keyboard.press("Control+a")
            page.wait_for_timeout(500)
            txt = page.evaluate("() => window.getSelection().toString()")
            browser.close()
            if txt and len(txt) > 5:
                rows = clean_rows([[c for c in line.split("\t")]
                                   for line in txt.split("\n")])
                if rows:
                    return rows
            return None
    except Exception as e:
        print(f"Playwright: ошибка: {type(e).__name__}: {e}")
        return None


# ---------------- Общий случай (при --local / без xlsx) ----------------

def looks_like_lesson_number(cell):
    if cell is None:
        return True
    s = str(cell).strip()
    if not s or s in ("-", "—", "–"):
        return True
    if re.fullmatch(r"\d{1,2}\s*[.)]?\s*(урок)?", s, re.I):
        return True
    return bool(LESSON_NO.match(s))


def to_hub_schedule(rows):
    if not rows:
        return None
    header = rows[0]
    header_keys = {}
    for i, cell in enumerate(header):
        if cell is None:
            continue
        for rx, k in DAY_MAP:
            if rx.search(str(cell)):
                header_keys[k] = i
                break
    if len(header_keys) >= 2:
        days = {k: [] for k in HUB_KEYS}
        for r in rows[1:]:
            for k, idx in header_keys.items():
                if idx < len(r):
                    c = r[idx]
                    if not looks_like_lesson_number(c):
                        days[k].append(str(c))
        if any(days.values()):
            return days
    days = {k: [] for k in HUB_KEYS}
    found = False
    for r in rows:
        if not r or r[0] is None:
            continue
        key = None
        for rx, k in DAY_MAP:
            if rx.search(str(r[0])):
                key = k
                break
        if not key:
            continue
        found = True
        for c in r[1:]:
            if not looks_like_lesson_number(c):
                days[key].append(str(c))
    if found and any(days[k] for k in HUB_KEYS):
        return days
    return None


# ---------------- Firebase (--push) ----------------

def read_text_any_encoding(path):
    """Читает файл с авто-определением кодировки: UTF-8 (с BOM и без),
    затем CP1251 — на случай если файл сохранён в кодировке Windows
    (иначе чтение как UTF-8 падает с UnicodeDecodeError)."""
    with open(path, "rb") as f:
        raw = f.read()
    for enc in ("utf-8-sig", "cp1251"):
        try:
            return raw.decode(enc)
        except (LookupError, UnicodeDecodeError):
            continue
    return raw.decode("utf-8", errors="replace")


def load_api_key(arg):
    if arg:
        return arg
    try:
        print("Читаю API-ключ Firebase…")
        m = re.search(r'apiKey:\s*"([^"]+)"',
                      read_text_any_encoding("firebase-config.js"))
        if m:
            return m.group(1)
    except OSError:
        pass
    return "AIzaSyAWWpIGsIDNE1lR7OeW9Mx3e7Af7tMmcXo"


def firebase_base(db_url):
    return db_url.rstrip("/") + "/"


def firebase_token(api_key):
    import requests
    print("Подключаюсь к Firebase…")
    r = requests.post(
        "https://identitytoolkit.googleapis.com/v1/accounts:signUp",
        params={"key": api_key}, json={"returnSecureToken": True}, timeout=30)
    if r.status_code != 200:
        raise RuntimeError(f"Не удалось авторизоваться: {r.status_code} {r.text[:160]}")
    return r.json().get("idToken")


def firebase_class_nodes(db_url, token, school=None):
    """Возвращает (nodes, base, school_bases).

    nodes[NAME_норм] = [(node, school_name), ...] — расписания классов.
    Один и тот же класс может быть сразу в нескольких школах (это расписания
    разных школ!). Без --school загрузка не будет знать, куда писать.
    school — подстрока названия школы (например «Школа №25») или её sid:
    узлы других школ отбрасываются.
    school_bases — [(имя_школы, cities/{c}/schools/{s}/classes), ...] по тем же
    школам (нужно для авто-создания класса --create-classes)."""
    import requests
    base = firebase_base(db_url)
    cities = requests.get(base + "cities.json?shallow=true", timeout=30).json() or {}
    nodes = {}
    school_bases = []
    school_mask = (school or "").strip().lower()
    found_schools = set()
    for cid in cities:
        schools = requests.get(f"{base}cities/{cid}/schools.json?shallow=true",
                               timeout=30).json() or {}
        for sid in schools:
            sn = requests.get(f"{base}cities/{cid}/schools/{sid}/name.json",
                              timeout=30).json() or ""
            sname = (str(sn).strip() or sid)
            if school_mask and school_mask not in sname.lower() \
                    and school_mask not in sid.lower():
                continue
            if school_mask:
                found_schools.add(sname)
            school_bases.append((sname, f"cities/{cid}/schools/{sid}/classes"))
            classes = requests.get(f"{base}cities/{cid}/schools/{sid}/classes.json?shallow=true",
                                   timeout=30).json() or {}
            for clid in classes:
                nm = requests.get(f"{base}cities/{cid}/schools/{sid}/classes/{clid}/name.json",
                                  timeout=30).json()
                key = "".join((nm or "").split()).upper()
                if key:
                    nodes.setdefault(key, []).append(
                        (f"cities/{cid}/schools/{sid}/classes/{clid}/schedule", sname))
    if school_mask and not found_schools:
        raise RuntimeError(f"Школа «{school}» не найдена в Firebase.")
    return nodes, base, school_bases


def resolve_firebase_node(nodes, class_name):
    """Узел (path, school) для класса с учётом уже применённого --school.

    Без --school (nodes собран по всем школам) имя, совпадающее в нескольких
    школах, считается неоднозначным — возвращается None с предупреждением."""
    key = "".join((class_name or "").split()).upper()
    cands = nodes.get(key) or []
    if not cands:
        return None
    if len(cands) == 1:
        return cands[0]
    names = sorted({sn for _p, sn in cands})
    print(f"  «{class_name}» есть в нескольких школах ({', '.join(names)}) — "
          "пропускаю; укажите --school.")
    return None


def _push_schedule(base, node, schedule, token):
    """PUT-перезапись узла: старое содержимое /schedule удаляется целиком,
    в Firebase остаётся только свежая неделя (место не забивается хвостами)."""
    import requests
    resp = requests.put(base + node + ".json", params={"auth": token},
                        json=schedule, timeout=30)
    if resp.status_code != 200:
        raise RuntimeError(f"Firebase вернул {resp.status_code}: {resp.text[:160]}")


def create_firebase_class(base, school_base, class_name, days, token):
    """Авто-создание узла класса в школе и запись расписания (--create-classes).

    school_base — «cities/{c}/schools/{s}/classes». Пустой POST создаёт
    Firebase-ключ; дальше пишутся name и schedule. Возвращает clid."""
    import requests
    resp = requests.post(base + school_base + ".json", params={"auth": token},
                         json={}, timeout=30)
    if resp.status_code != 200:
        raise RuntimeError(f"Не удалось создать класс: {resp.status_code} "
                           f"{resp.text[:160]}")
    clid = resp.json().get("name")
    if not clid:
        raise RuntimeError("Firebase не вернул ключ нового класса.")
    resp = requests.put(base + school_base + "/" + clid + "/name.json",
                        params={"auth": token}, json=class_name, timeout=30)
    if resp.status_code != 200:
        raise RuntimeError(f"Не удалось записать имя класса: "
                           f"{resp.status_code} {resp.text[:160]}")
    _push_schedule(base, school_base + "/" + clid + "/schedule", days, token)
    return clid


def push_to_firebase(schedule, class_name, api_key, db_url, school=None):
    token = firebase_token(api_key)
    nodes, base, _bases = firebase_class_nodes(db_url, token, school=school)
    node = resolve_firebase_node(nodes, class_name)
    if not node:
        if school:
            raise RuntimeError(f"Класс «{class_name}» не найден в школе "
                               f"«{school}» в Firebase.")
        raise RuntimeError(f"Класс «{class_name}» не найден в Firebase "
                           f"(или имя неоднозначно).")
    print(f"Загружаю расписание для {class_name}…")
    _push_schedule(base, node[0], schedule, token)
    print(f"OK: {node[0]} ({node[1]}) обновлён.")


def push_all_schedules(schedules, api_key, db_url, school=None, create=False):
    """Загружает расписания всех классов: {имя: {mon..sun}} -> /schedule.
    school — подстрока названия школы (см. firebase_class_nodes).
    create — если класс не найден в нужной школе, создать его узел и записать
    расписание (нужно указание --school)."""
    print("Загружаю расписания в Firebase…")
    token = firebase_token(api_key)
    nodes, base, school_bases = firebase_class_nodes(db_url, token, school=school)
    ok, created, missing = [], [], []
    create_base = None
    if create and school and len(school_bases) == 1:
        create_base = school_bases[0][1]
    for cl, days in schedules.items():
        node = resolve_firebase_node(nodes, cl)
        if not node and create_base:
            try:
                clean = normalize_class_display(cl) or str(cl)
                create_firebase_class(base, create_base, clean, days, token)
                created.append(cl)
                print(f"  {cl}: создан узел класса в "
                      f"«{school_bases[0][0]}» и записано расписание.")
                continue
            except Exception as e:
                missing.append(cl)
                print(f"  {cl}: ошибка создания класса: {e}")
                continue
        if not node:
            missing.append(cl)
            continue
        print(f"  {cl}: загружаю расписание…")
        try:
            _push_schedule(base, node[0], days, token)
            ok.append(cl)
        except Exception as e:
            missing.append(cl)
            print(f"  {cl}: ошибка загрузки: {e}")
    total = len(schedules)
    print(f"Загружено расписание для {len(ok) + len(created)} из {total} классов "
          f"(создано новых: {len(created)}).")
    if created:
        print("Создано: " + ", ".join(created))
    if ok:
        print("OK: " + ", ".join(ok))
    for cl in missing:
        print(f"  {cl}: не найден в Firebase или ошибка — пропущен.")
    return not missing


def parse_local_csv(path):
    rows = []
    with open(path, encoding="utf-8-sig") as f:
        for line in f:
            rows.append([c.strip() for c in line.rstrip("\n").split(";")])
    return clean_rows(rows)


def instructions_manual():
    print()
    print("Не удалось получить данные автоматически. Как скачать вручную:")
    print("  1. Откройте ссылку таблицы в браузере, выберите нужную вкладку.")
    print("  2. Ctrl+A, Ctrl+C, вставьте в Excel/Google Sheets, сохраните как CSV.")
    print('  3. Запустите: python parse_schedule.py --local schedule.csv')


def fmt_date(dt):
    return f"{dt.day:02d}.{dt.month:02d}.{dt.year}"


def parse_week_from_date(dt):
    monday = dt - datetime.timedelta(days=dt.weekday())
    return monday, monday + datetime.timedelta(days=6)


# ---------------- Источник: raspisanie.nikasoft.ru ----------------

NIKA_DAY_SHORT = {"пн": "mon", "вт": "tue", "ср": "wed", "чт": "thu",
                  "пт": "fri", "сб": "sat", "вс": "sun"}
NIKA_DAY_LONG = [("mon", "понед"), ("tue", "вторн"), ("wed", "сред"),
                 ("thu", "четверг"), ("fri", "пятниц"), ("sat", "суббот"),
                 ("sun", "воскрес")]
NIKA_DEFAULT_URL = "https://raspisanie.nikasoft.ru/86111512.html"


def http_get(url):
    import requests
    r = requests.get(url, timeout=30,
                     headers={"User-Agent": UA, "Accept-Language": "ru,en;q=0.9"})
    if r.status_code != 200:
        raise RuntimeError(f"HTTP {r.status_code} при запросе {url}")
    return r.text


def nikasoft_schedule_id(page_url):
    html = http_get(page_url)
    m = re.search(r"initial_schedule_id\s*=\s*['\"]([^'\"]+)['\"]", html)
    if not m:
        raise RuntimeError("В HTML страницы нет переменной initial_schedule_id.")
    return m.group(1)


def load_nika_data(page_url, schedule_id):
    from urllib.parse import urlparse
    pr = urlparse(page_url)
    data_url = f"{pr.scheme}://{pr.netloc}/static/public/{schedule_id}"
    txt = http_get(data_url).lstrip("\ufeff")
    body = txt
    i = txt.find("var NIKA=")
    if i != -1:
        body = txt[i + len("var NIKA="):].lstrip()
    body = body.strip()
    if body.endswith(";"):
        body = body[:-1]
    try:
        data, _ = json.JSONDecoder().raw_decode(body)
        return data, data_url
    except ValueError:
        pass
    try:
        import js2py
        ctx = js2py.EvalJs()
        ctx.execute(txt)
        obj = ctx.NIKA
        data = obj.to_dict() if hasattr(obj, "to_dict") else None
        if data:
            print("Данные распознаны через js2py.")
            return data, data_url
    except Exception as e:
        print(f"js2py: {type(e).__name__}: {e}")
    print("JSON не распарсился, рендерю страницу в headless-браузере…")
    return nikasoft_render(page_url), data_url


def nikasoft_render(page_url):
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as e:
        raise RuntimeError(f"Данные NIKA не распарсились, а Playwright недоступен: {e}")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
        ctx = browser.new_context(user_agent=UA, viewport={"width": 1440, "height": 1200})
        page = ctx.new_page()
        page.goto(page_url, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(4000)
        data = page.evaluate(
            """() => (typeof window.NIKA === 'undefined')
                ? null
                : JSON.parse(JSON.stringify(window.NIKA))""")
        browser.close()
        if data:
            return data
        raise RuntimeError("После рендеринга window.NIKA не найден.")


def nika_day_col_map(data):
    col = {}
    names = data.get("DAY_NAMESH") or data.get("DAY_NAMES") or []
    for idx, name in enumerate(names):
        low = "".join(ch for ch in str(name).lower() if ch.isalpha())
        if low[:2] in NIKA_DAY_SHORT:
            col[NIKA_DAY_SHORT[low[:2]]] = idx
        else:
            for hk, root in NIKA_DAY_LONG:
                if low.startswith(root):
                    col[hk] = idx
                    break
    return col


def nika_class_id(data, class_name):
    target = norm_key(class_name)
    for cid, nm in (data.get("CLASSES") or {}).items():
        if norm_key(nm) == target:
            return cid
    return None


def nika_list_classes(data):
    cls = data.get("CLASSES") or {}
    try:
        vals = [cls[k] for k in sorted(cls, key=int)]
    except ValueError:
        vals = [cls[k] for k in sorted(cls)]
    return [str(v) for v in vals]


def nika_period_for(data, d):
    best = None
    for pid, p in (data.get("PERIODS") or {}).items():
        try:
            b = datetime.datetime.strptime(p["b"], "%d.%m.%Y").date()
            e = datetime.datetime.strptime(p["e"], "%d.%m.%Y").date()
        except Exception:
            continue
        if b <= d <= e:
            best = pid
            break
    return best


def nika_format_time(s):
    try:
        h, m = str(s).split(":")
        return f"{int(h):02d}:{int(m):02d}"
    except Exception:
        return ""


def nika_lesson_text(en, subjects, rooms):
    """Возвращает список строк урока: по одной на каждый предмет («Предмет кабинет»).

    Ячейка может объединять параллельные группы (несколько предметов) — каждый
    предмет выводится отдельной строкой, как в дневном виде на сайте. [] если урок отменён.
    """
    s = en.get("s") or []
    if isinstance(s, str):
        s = [s]
    if s and s[0] == "F":
        return []
    r = en.get("r") or []
    if isinstance(r, str):
        r = [r]
    out = []
    for i in range(len(s)):
        sv = str(s[i])
        if sv and sv[0] == "F":
            continue
        nm = (subjects.get(sv) or subjects.get(sv.zfill(3)))
        if not nm:
            nm = "(нет)"
        line = str(nm)
        if i < len(r):
            rv = r[i]
            rm = rooms.get(str(rv).zfill(3)) if str(rv).isdigit() else str(rv)
            if rm:
                line += " " + str(rm)
        out.append(line)
    return out


def nika_build_week(data, class_id, monday, sunday):
    """Расписание класса за неделю по периодам/заменам NIKA.

    Возвращает (days, used, active_periods, skipped) — used: [(hub, date, period)],
    skipped: [(hub, date, причина)] для дней, где уроков нет из-за каникул и т.п.
    """
    day_col = nika_day_col_map(data)
    sched = data.get("CLASS_SCHEDULE") or {}
    overr = (data.get("CLASS_EXCHANGE") or {}).get(class_id) or {}
    holidays = data.get("HOLIDAY_TRANSFER") or {}
    lesson_times = data.get("LESSON_TIMES") or {}
    first = int(data.get("FIRSTLESSONNUM") or 1)
    last = int(data.get("LESSONSINDAY") or 12)
    subjects = data.get("SUBJECTS") or {}
    rooms = data.get("ROOMS") or {}
    cancel_str = data.get("LESSON_CANCELED_STR") or "урок отменен"
    days = {k: [] for k in HUB_KEYS}
    used = []
    skipped = []
    active = []
    d = monday
    while d <= sunday:
        hub = None
        for hk, idx in day_col.items():
            if d.weekday() == idx:
                hub = hk
                break
        date_key = d.strftime("%d.%m.%Y")
        pid = nika_period_for(data, d)
        if pid and pid not in active:
            active.append(pid)
        holiday = holidays.get(date_key)
        if hub is not None:
            if holiday and holiday.get("type") == "vacation":
                skipped.append((hub, d, "каникулы"))
                d += datetime.timedelta(days=1)
                continue
            if pid is None:
                skipped.append((hub, d, "нет активного периода"))
                d += datetime.timedelta(days=1)
                continue
            pat = (sched.get(pid) or {}).get(class_id) or {}
            exc = overr.get(date_key) or {}
            col = day_col[hub] + 1
            used.append((hub, d, pid))
            for lsn in range(first, last + 1):
                en = pat.get(f"{col}{lsn:02d}")
                ex = exc.get(str(lsn))
                lines = None
                if ex is not None:
                    sxs = ex.get("s")
                    if isinstance(sxs, str):
                        sxs = [sxs]
                    if sxs and sxs[0] == "F":
                        en = None
                        lines = [cancel_str]
                    else:
                        en = ex
                        lines = nika_lesson_text(en, subjects, rooms)
                elif en is not None:
                    lines = nika_lesson_text(en, subjects, rooms)
                if not lines:
                    continue
                tt = lesson_times.get(str(lsn))
                head = ""
                if tt:
                    a = nika_format_time(tt[0])
                    b = nika_format_time(tt[1]) if len(tt) > 1 else ""
                    if a and b:
                        head = f"{a}-{b} "
                for line in lines:
                    days[hub].append(head + line)
        d += datetime.timedelta(days=1)
    return days, used, active, skipped


def nika_run(args, monday, sunday, allow_push=True):
    page_url = args.url.strip()
    try:
        schedule_id = nikasoft_schedule_id(page_url)
    except Exception as e:
        print(f"nikasoft: не удалось получить HTML: {e}")
        return 1
    print(f"Источник: raspisanie.nikasoft.ru  (schedule_id={schedule_id})")
    try:
        data, data_url = load_nika_data(page_url, schedule_id)
    except Exception as e:
        print(f"nikasoft: не удалось загрузить данные: {e}")
        return 1
    print(f"Школа: {data.get('SCHOOL_NAME')} ({data.get('CITY_NAME')})")
    print(f"Данные: {data_url}")
    if data.get("EXPORT_DATE"):
        print(f"Экспорт: {data.get('EXPORT_DATE')} {data.get('EXPORT_TIME')}")

    if args.list:
        classes = nika_list_classes(data)
        print(f"Доступные классы ({len(classes)}):")
        for nm in classes:
            print(f"  {nm}")
        return 0

    span_f = (f"{monday.day:02d}.{monday.month:02d}"
              f"–{sunday.day:02d}.{sunday.month:02d}")

    # ---- мульти-класс: --all-classes / --grade / --classes ----
    multi = bool(args.all_classes or args.grade or args.classes)
    if multi:
        if args.classes:
            names = [c.strip() for c in args.classes.split(",") if c.strip()]
        elif args.all_classes:
            names = nika_list_classes(data)
        else:
            g = str(args.grade).strip()
            names = [c for c in nika_list_classes(data) if grade_of(c) == g]
        if not names:
            print("Не найдено классов для обработки.")
            return 1
        print(f"Найдено классов: {', '.join(names)}")
        print(f"Неделя {span_f}; обрабатываю " + "… ".join(names) + "…")
        results, missing = {}, []
        for nm in names:
            cid = nika_class_id(data, nm)
            if cid is None:
                print(f"  {nm}: класс не найден в данных — пропускаю.")
                missing.append(nm)
                continue
            days, _used, _active, _skipped = nika_build_week(data, cid, monday, sunday)
            total = sum(len(days[k]) for k in HUB_KEYS)
            if total == 0:
                print(f"  {nm}: нет расписания на неделю {span_f} — пропускаю.")
                missing.append(nm)
                continue
            results[nm] = days
            print(f"  {nm}: {total} уроков за неделю")
            if days["sat"]:
                print(f"    {DAY_NAMES['sat']}: " + " | ".join(days["sat"]))
        if not results:
            print("Ни один класс не распознан в данных.")
            return 1
        with open("schedule_all.json", "w", encoding="utf-8") as f:
            json.dump({"week": span_f, "classes": results}, f,
                      ensure_ascii=False, indent=2)
        print("Записал: schedule_all.json")
        for nm, days in results.items():
            fname = "".join(ch for ch in str(nm) if ch.isalnum())
            with open(f"schedule_{fname}.json", "w", encoding="utf-8") as f:
                json.dump({"class": nm, "days": days}, f,
                          ensure_ascii=False, indent=2)
        print("Записал: schedule_<класс>.json для каждого класса.")
        if allow_push and not args.no_push:
            try:
                push_all_schedules(results, load_api_key(args.api_key),
                                   args.database_url, school=args.school,
                                   create=args.create_classes)
            except Exception as e:
                print(f"Firebase-загрузка не удалась: {e}")
        return 0

    # ---- один класс ----
    class_id = nika_class_id(data, args.class_name)
    if class_id is None:
        print(f"Класс «{args.class_name}» не найден. Доступные классы:")
        for nm in nika_list_classes(data):
            print(f"  {nm}")
        return 1

    print(f"Класс {args.class_name} -> id {class_id}, неделя {span_f}")
    days, used, active, skipped = nika_build_week(data, class_id, monday, sunday)
    total = sum(len(days[k]) for k in HUB_KEYS)
    if total == 0:
        print(f"Не найдено расписание на неделю {span_f}: "
              f"нет периодов на эти даты или у класса нет уроков.")
        return 1
    print(f"Активные периоды: {', '.join(active)}")
    for hk, d, pid in used:
        if days[hk]:
            print(f"  {DAY_NAMES[hk]} {fmt_date(d)} (период {pid}): "
                  + " | ".join(days[hk]))
        else:
            print(f"  {DAY_NAMES[hk]} {fmt_date(d)}: уроков нет")
    for hk, d, reason in skipped:
        print(f"  {DAY_NAMES[hk]} {fmt_date(d)}: {reason} — день пропущен")

    payload = {"class": args.class_name, "days": days}
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print(f"Записал: {args.out}")
    with open("schedule_raw.json", "w", encoding="utf-8") as f:
        json.dump({"source": "nikasoft",
                   "school": data.get("SCHOOL_NAME"),
                   "schedule_id": schedule_id,
                   "class": args.class_name, "class_id": class_id,
                   "week": span_f, "periods": active,
                   "days": [{ "day": hk, "date": d.isoformat(),
                              "period": pid, "lessons": days[hk] }
                            for hk, d, pid in used]},
                  f, ensure_ascii=False, indent=2)
    print("Записал: schedule_raw.json")

    if allow_push and not args.no_push:
        try:
            push_to_firebase(days, args.class_name,
                             load_api_key(args.api_key), args.database_url,
                             school=args.school)
        except Exception as e:
            print(f"Firebase-загрузка не удалась: {e}")
    return 0


# ---------------- main ----------------

def main(argv=None):
    ap = argparse.ArgumentParser(description="Парсер расписания (Google Таблицы / nikasoft)")
    ap.add_argument("url", nargs="?", help="Ссылка на Google-таблицу или raspisanie.nikasoft.ru")
    ap.add_argument("--class", dest="class_name", default="7А",
                    help="Класс (по умолчанию 7А)")
    ap.add_argument("--all-classes", action="store_true",
                    help="Обработать все классы, найденные во вкладках недели")
    ap.add_argument("--grade", default=None,
                    help="Только классы этой параллели (например 7)")
    ap.add_argument("--classes", default=None,
                    help="Конкретный список классов через запятую (7А,7Б,7В)")
    ap.add_argument("--week", action="store_true",
                    help="Принудительно взять текущую неделю (по умолчанию и так)")
    ap.add_argument("--date", default=None,
                    help="YYY-MM-DD — взять неделю, содержащую эту дату")
    ap.add_argument("--sheet", default=None,
                    help="Старый режим: подстрока названия «недельной» вкладки")
    ap.add_argument("--list", action="store_true", help="Показать список вкладок и выйти")
    ap.add_argument("--out", default="schedule.json",
                    help="Файл результата (по умолчанию schedule.json)")
    ap.add_argument("--local", help="Распарсить локальный CSV вместо сети")
    ap.add_argument("--nikasoft", action="store_true",
                    help="Принудительно использовать raspisanie.nikasoft.ru "
                         "(иначе источник определяется по домену)")
    ap.add_argument("--nikasoft-url", default=None,
                    help="URL страницы raspisanie.nikasoft.ru (по умолчанию "
                         f"{NIKA_DEFAULT_URL} — школа №25 «Гелиос», Находка)")
    ap.add_argument("--school", default=None,
                    help="Firebase-школа для загрузки (подстрока названия, "
                         "например «Школа №25»). Нужно, когда расписания двух "
                         "разных школ, а классы называются одинаково.")
    ap.add_argument("--create-classes", action="store_true",
                    help="Вместе с --school: класс, которого нет в Firebase, "
                         "создавать автоматически (узел + расписание) вместо "
                         "пропуска с предупреждением")
    ap.add_argument("--no-push", action="store_true",
                    help="НЕ загружать в Firebase (по умолчанию загружает)")
    ap.add_argument("--push", action="store_true",
                    help="Загрузить расписание в Firebase (включено по умолчанию)")
    ap.add_argument("--api-key", default=None, help="Web API key Firebase")
    ap.add_argument("--database-url",
                    default="https://school-hub-9d8aa-default-rtdb.firebaseio.com",
                    help="RTDB URL")
    ap.add_argument("--watch", nargs="?", const="900", default=None, metavar="СЕКУНД",
                    help="Перепроверять расписание каждые N секунд (по умолчанию "
                         "900 = 15 минут) и загружать в Firebase только при изменениях")
    args = ap.parse_args(argv)

    if not args.url:
        args.url = args.nikasoft_url or NIKA_DEFAULT_URL

    # ---- целевая дата и неделя ----
    if args.date:
        try:
            anchor = datetime.date.fromisoformat(args.date)
        except ValueError:
            print(f"Ошибка: --date должен быть формата YYYY-MM-DD (получено {args.date!r})")
            return 2
    else:
        anchor = datetime.date.today()
    monday, sunday = parse_week_from_date(anchor)
    print(f"Сегодня: {fmt_date(datetime.date.today())}")
    print(f"Целевая дата: {fmt_date(anchor)} (неделя {monday.day:02d}.{monday.month:02d}"
          f"–{sunday.day:02d}.{sunday.month:02d})")

    if args.watch is not None:
        return watch_loop(args, anchor, monday, sunday)
    return run_once(args, anchor, monday, sunday)


def watch_loop(args, anchor, monday, sunday):
    """--watch: цикл перепроверки. Каждые N секунд заново собирает расписание
    и загружает в Firebase ТОЛЬКО если данные изменились (по дайджесту файлов)."""
    try:
        interval = int(args.watch or 900)
    except ValueError:
        interval = 900
    if interval < 60:
        print("--watch: интервал минимум 60 секунд (ставлю 60).")
        interval = 60
    is_multi = bool(args.all_classes or args.grade or args.classes)
    print(f"Режим слежения: перепроверка каждые {interval} с, "
          f"в Firebase грузим только изменения (Ctrl+C — выход).")

    def digest_of_output():
        fname = "schedule_all.json" if is_multi else args.out
        try:
            with open(fname, encoding="utf-8") as f:
                return f.read()
        except OSError:
            return None

    def push_existing():
        api = load_api_key(args.api_key)
        if is_multi:
            with open("schedule_all.json", encoding="utf-8") as f:
                results = json.load(f)["classes"]
            push_all_schedules(results, api, args.database_url, school=args.school)
        else:
            with open(args.out, encoding="utf-8") as f:
                days = json.load(f)["days"]
            push_to_firebase(days, args.class_name, api, args.database_url,
                             school=args.school)

    last = None
    first = True
    try:
        while True:
            if first:
                first = False
            else:
                print("\n=== Перепроверка "
                      + datetime.datetime.now().strftime("%H:%M:%S") + " ===")
            rc = run_once(args, anchor, monday, sunday, allow_push=False)
            if rc != 0:
                print(f"[предупреждение] проход вернул код {rc}.")
            digest = digest_of_output()
            if digest is not None and digest != last:
                print("Расписание изменилось.")
                if not args.no_push:
                    try:
                        push_existing()
                    except Exception as e:
                        print(f"Firebase-загрузка не удалась: {e}")
            else:
                print("Без изменений — загрузка пропущена.")
            last = digest
            time.sleep(interval)
    except KeyboardInterrupt:
        print("\nСлежение остановлено.")
    return 0


def run_once(args, anchor, monday, sunday, allow_push=True):
    """Один полный проход: получить источник, распарсить, записать файлы,
    при необходимости (allow_push и не --no-push) загрузить в Firebase.
    Возвращает код возврата."""
    use_nikasoft = args.nikasoft or bool(
        args.url and "raspisanie.nikasoft.ru" in args.url.lower())
    if args.local:
        print(f"Читаю локальный файл: {args.local}")
        rows = parse_local_csv(args.local)
    elif use_nikasoft:
        return nika_run(args, monday, sunday, allow_push)
    else:
        sid = sheet_id_from_url(args.url)
        if not sid:
            print("Не распознал ID таблицы в ссылке.")
            instructions_manual()
            return 2

        xlsx = os.path.join(tempfile.gettempdir(), "sch_workbook.xlsx")
        if not fetch_xlsx(sid, xlsx):
            print("XLSX-экспорт недоступен, перехожу к цепочке pandas/Selenium/Playwright.")
            rows = try_pandas(sid)
            if rows is None:
                rows = try_selenium(sid)
            if rows is None:
                rows = try_playwright(sid)
            if rows is None:
                instructions_manual()
                return 1
            days = to_hub_schedule(rows)
            payload = {"class": args.class_name,
                       "days": days} if days else {"class": args.class_name, "rows": rows}
            with open(args.out, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
            with open("schedule_raw.json", "w", encoding="utf-8") as f:
                json.dump({"class": args.class_name, "rows": rows}, f,
                          ensure_ascii=False, indent=2)
            print(f"Записал: {args.out}")
            return 0

        print("XLSX-экспорт получен — читаю листы…")
        names = sheets_names_only(xlsx)
        if args.list:
            print(f"Всего вкладок: {len(names)}")
            for k, name in enumerate(names):
                print(f"{k:3d}  {name}")
            return 0
        sheets = load_xlsx_sheets(xlsx)

        # ---- режим всех классов: --all-classes / --grade / --classes ----
        multi = bool(args.all_classes or args.grade or args.classes)
        if multi and args.sheet:
            print("Флаги --all-classes/--grade/--classes не поддерживаются вместе с --sheet.")
            return 2
        if multi:
            picked = select_week_tabs(sheets, monday, sunday, anchor.year)
            if not picked:
                parsed_all = [r for r in (parse_tab_date(nm) for nm in names) if r]
                avail = sorted({(key, dt) for key, dt in parsed_all}, key=lambda x: x[1])
                avail_txt = ", ".join(
                    f"{DAY_NAMES[key]} {fmt_date(dt)}" for key, dt in avail[:30])
                print(f"\nНе найдено расписание на текущую неделю. "
                      f"Доступные даты: {avail_txt}.")
                return 1

            span_f = f"{picked[0][1].day:02d}.{picked[0][1].month:02d}" \
                     f"–{picked[-1][1].day:02d}.{picked[-1][1].month:02d}"
            print(f"Ищу вкладки за неделю {span_f}")
            print("Найдено: " + ", ".join(nm for _k, _d, nm, _s in picked))
            loose_names = [nm for _k, _d, nm, s in picked if not s]
            if loose_names:
                print("Внимание: у вкладок " + ", ".join(loose_names)
                      + " дата не совпадает с днём недели в названии (беру их как есть).")

            by_name = {nm: m for nm, m in sheets}
            tab_names = [nm for _k, _d, nm, _s in picked]

            # список классов
            if args.classes:
                clist = [c for c in
                         (normalize_class_display(c) or c.strip()
                          for c in args.classes.split(",")) if c]
            else:
                clist = discover_classes([by_name[nm] for nm in tab_names])
                if args.grade:
                    g = str(args.grade).strip()
                    clist = [c for c in clist if grade_of(c) == g]
            if not clist:
                print("Не найдено классов для обработки.")
                return 1

            print("Обрабатываю " + "… ".join(clist) + "…")
            results, missing = build_class_weeks(picked, by_name, clist)
            for cl in missing:
                print(f"  {cl}: класс не найден в вкладках недели — пропускаю.")
            if not results:
                print("\nНи один класс не распознан в таблице.")
                return 1
            for cl, days in results.items():
                total = sum(len(days[k]) for k in HUB_KEYS)
                print(f"  {cl}: {total} уроков за неделю")
                if days["sat"]:
                    print(f"    {DAY_NAMES['sat']}: " + " | ".join(days["sat"]))

            with open("schedule_all.json", "w", encoding="utf-8") as f:
                json.dump({"week": span_f, "classes": results}, f,
                          ensure_ascii=False, indent=2)
            print("Записал: schedule_all.json")
            for cl, days in results.items():
                name = "".join(ch for ch in cl if ch.isalnum())
                with open(f"schedule_{name}.json", "w", encoding="utf-8") as f:
                    json.dump({"class": cl, "days": days}, f,
                              ensure_ascii=False, indent=2)
            print("Записал: schedule_<класс>.json для каждого класса.")

            if allow_push and not args.no_push:
                try:
                    push_all_schedules(results, load_api_key(args.api_key),
                                       args.database_url, school=args.school,
                                       create=args.create_classes)
                except Exception as e:
                    print(f"Firebase-загрузка не удалась: {e}")
            return 0

        # ---- старый режим: конкретная «недельная» вкладка ----
        if args.sheet:
            wanted = args.sheet.strip().lower()
            cand = [(nm, m) for nm, m in sheets if wanted in nm.strip().lower()]
            if not cand:
                print(f"Вкладка с подстрокой {args.sheet!r} не найдена.")
                return 1
            best, best_score = None, -1
            for nm, m in cand:
                days, blocks, has_col = extract_class_week(m, args.class_name)
                total = sum(len(days[k]) for k in HUB_KEYS)
                score = blocks * 100 + (10 if has_col else 0) + total
                if score > best_score:
                    best_score, best = score, (nm, m, days, blocks, has_col)
            nm, m, days, blocks, has_col = best
            print(f"Вкладка: {nm!r} ({blocks} дней, колонка класса: "
                  f"{'есть' if has_col else 'не найдена'}).")
            payload = {"class": args.class_name, "days": days}
            with open(args.out, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
            with open("schedule_raw.json", "w", encoding="utf-8") as f:
                json.dump({"class": args.class_name, "sheet": nm, "rows": m}, f,
                          ensure_ascii=False, indent=2)
            print(f"Записал: {args.out}")
            if allow_push and not args.no_push:
                try:
                    push_to_firebase(days, args.class_name,
                                     load_api_key(args.api_key), args.database_url,
                                     school=args.school)
                except Exception as e:
                    print(f"Firebase-загрузка не удалась: {e}")
            return 0

        # ---- НОВЫЙ режим: вкладки с датами за текущую неделю ----
        picked = select_week_tabs(sheets, monday, sunday, anchor.year)
        if not picked:
            parsed_all = [r for r in (parse_tab_date(nm) for nm in names) if r]
            avail = sorted({(key, dt) for key, dt in parsed_all}, key=lambda x: x[1])
            avail_txt = ", ".join(
                f"{DAY_NAMES[key]} {fmt_date(dt)}" for key, dt in avail[:30])
            print(f"\nНе найдено расписание на текущую неделю. "
                  f"Доступные даты: {avail_txt}.")
            return 1

        span_f = f"{picked[0][1].day:02d}.{picked[0][1].month:02d}" \
                 f"–{picked[-1][1].day:02d}.{picked[-1][1].month:02d}"
        print(f"Ищу вкладки за неделю {span_f}")
        print("Найдено: " + ", ".join(nm for _k, _d, nm, _s in picked))
        loose_names = [nm for _k, _d, nm, s in picked if not s]
        if loose_names:
            print("Внимание: у вкладок " + ", ".join(loose_names)
                  + " дата не совпадает с днём недели в названии (беру их как есть).")

        days = {k: [] for k in HUB_KEYS}
        any_col = False
        by_name = {nm: m for nm, m in sheets}
        for key, dt, nm, _strict in picked:
            lessons, has_col = extract_class_day(by_name.get(nm, []), args.class_name)
            any_col = any_col or has_col
            days[key] = lessons
            if has_col:
                print(f"  {DAY_NAMES[key]} {fmt_date(dt)} ({nm.strip()}): "
                      + (" | ".join(lessons) if lessons else "—"))
            else:
                print(f"  {DAY_NAMES[key]} {fmt_date(dt)}: "
                      f"колонка класса {args.class_name} не найдена; день пуст")

        if not any_col:
            print(f"\nКласс {args.class_name} не найден ни в одной вкладке за неделю.")
            return 1
        have_keys = {x[0] for x in picked}
        for k in HUB_KEYS:
            if not days[k] and k not in have_keys:
                dt = monday + datetime.timedelta(days=PY_KEYS[k])
                print(f"  Нет вкладки на {DAY_NAMES[k]} {fmt_date(dt)} — день пропущен.")

        payload = {"class": args.class_name, "days": days}
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        print(f"Записал: {args.out}")
        raw_tabs = {nm: by_name.get(nm, []) for _k, _d, nm, _s in picked}
        with open("schedule_raw.json", "w", encoding="utf-8") as f:
            json.dump({"class": args.class_name, "week": span_f, "tabs": raw_tabs}, f,
                      ensure_ascii=False, indent=2)
        print("Записал: schedule_raw.json")

        if allow_push and not args.no_push:
            try:
                push_to_firebase(days, args.class_name,
                                 load_api_key(args.api_key), args.database_url,
                                 school=args.school)
            except Exception as e:
                print(f"Firebase-загрузка не удалась: {e}")
        return 0


if __name__ == "__main__":
    sys.exit(main())