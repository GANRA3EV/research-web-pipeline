# Research Web Pipeline

Сбор текстов с веб-страниц и классификация через
[fintech-triage](https://github.com/GANRA3EV/fintech-triage). На выходе — XLSX
с текстами, прогнозами и исходными URL. Классификатор и локальные резюме
подключаются отдельно; парсинг работает и без них.

## Быстрый старт

Для полного цикла нужен Python 3.11–3.14. Команды ниже рассчитаны на PowerShell
и запускаются из папки репозитория. В Linux и macOS путь к Python окружения —
`.venv/bin/python`.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe run_all.py --config config/example.json
```

Пример загружает `https://example.com`. Результаты появляются в новой папке
`runs/` с датой и временем запуска.

## Выбор загрузчика

| Загрузчик | JavaScript | Для каких страниц |
|---|---|---|
| [curl_cffi](https://github.com/lexiforest/curl_cffi) | Нет | Данные доступны в исходном HTML |
| [Patchright](https://github.com/Kaliiiiiiiiii-Vinyzu/patchright-python) | Да | Нужен Chromium и выполнение JavaScript |
| [Camoufox](https://github.com/daijro/camoufox) | Да | Нужен браузер на базе Firefox |
| [Clearcote](https://github.com/clearcotelabs/clearcote-browser) | Да | Нужен модифицированный Chromium |

Для браузерных загрузчиков:

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[browsers]"
.\.venv\Scripts\python.exe -m patchright install chromium
.\.venv\Scripts\python.exe -m camoufox fetch
.\.venv\Scripts\python.exe run_all.py --config config/all-engines.json
```

Clearcote скачивает свой браузер при первом запуске. На Linux могут понадобиться
системные библиотеки: `python -m patchright install --with-deps chromium` и
`python -m playwright install-deps firefox`.

Если в `engines` перечислены несколько загрузчиков, каждый получает страницу
отдельно. Перехода на другой браузер после блокировки нет. Временные сетевые
сбои и ответы HTTP 500, 502, 503, 504 допускают повторную попытку. Ответы 403
и 429 записываются в журнал без повторов.

## Свои источники

Конфигурация задаётся в JSON. Пример для страницы с динамическим содержимым:

```json
{
  "engines": ["patchright"],
  "headless": true,
  "timeout_seconds": 30,
  "delay_seconds": 1,
  "retries": 1,
  "sources": [{
    "id": "example",
    "url": "https://example.com",
    "title_selector": "h1",
    "text_selector": "body",
    "wait_for_selector": "h1"
  }]
}
```

`title_selector` выбирает первый заголовок, `text_selector` — элементы с
нужным текстом. Вложенные совпадения могут дублировать содержимое, поэтому
лучше выбирать непересекающиеся элементы. Браузерный загрузчик ожидает
появления `wait_for_selector` перед сохранением страницы. Скрипты и стили
в извлечённый текст не попадают.

Адреса сохраняются в результатах, поэтому URL не должен содержать ключи
и пароли. Интерактивный вход и обработка CAPTCHA не поддерживаются.

## Классификация и локальное резюме

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[analysis,local-hf]"
.\.venv\Scripts\python.exe tools/demo_semantic.py --backend rubert --with-summary --output runs/rubert-demo
```

Демонстрация обучает классификаторы на синтетических строках, запускает
локальный сайт и проводит его страницы через весь цикл обработки.
`rubert-tiny2` работает на CPU. При первом запуске скачиваются веса с
Hugging Face. Резюме состоит из предложений исходного текста.

Для своих страниц нужна обученная модель и её SHA-256 в разделе `analysis`
конфигурации. Шаблон — [config/semantic.template.json](config/semantic.template.json),
описание параметров и обучения — в [руководстве по анализу](docs/SEMANTIC_INTEGRATION.md).
Модель из `fintech-triage` классифицирует обращения по теме и срочности.
Для другого корпуса понадобятся собственная разметка и обучение.

Совпадающие тексты анализируются один раз. Ссылки на все страницы сохраняются,
даже если после очистки их тексты совпали. Прогноз относится к отдельному
фрагменту; общей метки документа программа не назначает.

## Выходные файлы

```text
runs/<время_UTC>/
  data/
    raw.xlsx
    processed.xlsx
    analysis.xlsx
  logs/
    manifest.json
    attempts.json
    diagnostics.json
    analysis_report.json
    word_count_report.json
    word_frequency_report.json
```

`raw.xlsx` хранит полученный HTML или DOM, адреса, HTTP-статусы и контрольные
суммы. `processed.xlsx` содержит заголовки, извлечённые тексты и отметки
дубликатов. При подключённом анализе добавляются `analysis.xlsx` и
`analysis_report.json`. Прогнозы связаны с фрагментами и URL через
`chunk_id`, `analysis_id` и `record_id`.

Длинные значения XLSX разбиваются на части на листе `long_values`.
Внешний текст сохраняется как текст, включая строки со знаком `=`.
Журнал запуска содержит конфигурацию, версии пакетов и хэши файлов.

Папка запуска не перезаписывается. Свой путь задаётся через `--output runs/my-run`.
Код завершения 0 означает успешный сбор и подключённый анализ, 1 — ошибку
обработки, 2 — ошибку параметров или файлов. При сбое классификатора уже
собранные страницы остаются на диске.

## Camoufox в Windows

Чтение файлов по пути с кириллицей поддержано адаптером для `indexed_zstd`.
У некоторых сборок встречается отдельная ошибка запуска, связанная с
`mozglue` в манифесте. Она описана в
[обсуждении разработчиков](https://github.com/daijro/camoufox/issues/650).

В проекте есть команда просмотра и применения исправления:

```powershell
.\.venv\Scripts\python.exe tools/repair_camoufox_windows.py
.\.venv\Scripts\python.exe tools/repair_camoufox_windows.py --apply
```

При применении рядом с `camoufox.exe` сохраняются исходная копия
`camoufox.exe.original` и отчёт с контрольными суммами. Для отката при закрытом
браузере исходная копия заменяет изменённый файл. Обычный запуск пайплайна
исполняемый файл не меняет.

## Тесты

```powershell
.\.venv\Scripts\python.exe -m pytest -q -m "not browser"
```

Для проверки браузеров после их установки:

```powershell
$env:TEST_BROWSERS = "1"
.\.venv\Scripts\python.exe -m pytest -q -m browser
```

GitHub Actions проверяет базовый сбор и связку с `fintech-triage`.
Браузерные тесты доступны через ручной запуск с параметром `browsers`.
Результаты выполненных проверок находятся в [VALIDATION.md](VALIDATION.md).

## Ограничения

curl_cffi получает исходный HTML; браузерные загрузчики сохраняют DOM после
выполнения JavaScript и ожидания селектора. Содержимое может различаться
между загрузчиками и запусками. Для каждого адреса создаётся отдельная
браузерная сессия; cookies между страницами не переносятся.

Подсчёт слов использует пробельные разделители. Частотный отчёт считает
словоформы без лемматизации и удаления стоп-слов. Качество классификации
на своих данных нужно оценивать отдельно. Программа не проверяет
достоверность утверждений, собранных со страниц.
