Откройте PowerShell и перейдите в распакованный каталог, содержащий файл
`pyproject.toml`. Например:

```powershell
cd "C:\Users\user\Downloads\PythonProject"
```

В следующих шагах команды нужно выполнять из этого каталога.

## 3. Установить uv

`uv` — программа для установки Python, зависимостей и запуска проекта.
Выполните:

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

После установки закройте PowerShell, откройте его снова, вернитесь в каталог
проекта и проверьте установку:

```powershell
uv --version
```

Другие способы установки приведены в
[официальной документации uv](https://docs.astral.sh/uv/getting-started/installation/).

## 4. Установить Python и зависимости проекта

В каталоге проекта выполните:

```powershell
uv sync --locked
```

Команда создаст виртуальное окружение `.venv` и установит в него зависимости
из файла `uv.lock`.

## 5. Подготовить отдельный профиль Chrome

Полностью закройте все окна Google Chrome. Затем выполните в PowerShell:

```powershell
$sourceProfile = "$env:LOCALAPPDATA\Google\Chrome\User Data"
$parserProfile = "$env:LOCALAPPDATA\chrome-profiles\megamarket-12"

if (-not (Test-Path $sourceProfile)) {
    throw "Профиль Google Chrome не найден: $sourceProfile"
}

New-Item -ItemType Directory -Force -Path (Split-Path $parserProfile) | Out-Null

if (-not (Test-Path $parserProfile)) {
    Copy-Item -Path $sourceProfile -Destination $parserProfile -Recurse
}
```

Копирование выполняется только при первом запуске. В дальнейшем программа
использует уже созданный профиль `megamarket-12`.

## 6. Запустить Chrome с поддержкой CDP

Выполните в PowerShell:

```powershell
$chrome = "$env:ProgramFiles\Google\Chrome\Application\chrome.exe"
$parserProfile = "$env:LOCALAPPDATA\chrome-profiles\megamarket-12"

if (-not (Test-Path $chrome)) {
    $chrome = "$env:LOCALAPPDATA\Google\Chrome\Application\chrome.exe"
}

if (-not (Test-Path $chrome)) {
    throw "Google Chrome не найден"
}

& $chrome `
  --disable-blink-features=AutomationControlled `
  --no-first-run `
  --no-default-browser-check `
  --lang=ru-RU `
  --window-size=1366,768 `
  --force-webrtc-ip-handling-policy=disable_non_proxied_udp `
  --user-data-dir="$parserProfile" `
  --remote-debugging-port=51111
```

Оставьте открывшийся Chrome запущенным до окончания работы программы.
Если что-то из вышеперечисленного пошло не так, то просто выполнить программу:
```bash
google-chrome-stable \
  --no-sandbox \
  --disable-blink-features=AutomationControlled \
  --no-first-run \
  --no-default-browser-check \
  --user-data-dir="/tmp/uc_$(openssl rand -hex 8)" \
  --remote-debugging-port=51111
```

## 7. Запустить парсер

> Выдача собирается без фильтра «В наличии». Капчу нужно решить в окне Chrome.

Откройте ещё одно окно PowerShell, перейдите в каталог проекта и выполните:

```powershell
uv run python main.py
```

Введите поисковый запрос, например:

```text
Поисковый запрос: айфон 17
```

Готовый файл сохраняется в каталоге `output` с именем вида:

```text
megamarket_айфон_17_2026-08-31_09-45.xlsx
```

## Настройка

Параметры можно переопределить в файле `.env` в корне проекта. Например:

```dotenv
PARSER_NUMBER_PAGES=5
PARSER_NUMBER_ITEMS=20
PARSER_PAGE_DELAY=3
PARSER_CARD_DELAY=7
PARSER_CARD_CLOSE_DELAY=3
PARSER_CAPTCHA_TIMEOUT=300
PARSER_FILTER_TIMEOUT=15
```

Основные параметры:

| Переменная | Значение по умолчанию | Назначение |
| --- | ---: | --- |
| `PARSER_BROWSER_HOST` | `127.0.0.1` | Адрес Chrome с включённым CDP |
| `PARSER_BROWSER_PORT` | `51111` | Порт CDP; должен совпадать с `--remote-debugging-port` |
| `PARSER_NUMBER_PAGES` | `3` | Максимальное количество страниц выдачи |
| `PARSER_NUMBER_ITEMS` | `4` | Максимальное количество товаров с одной страницы |
| `PARSER_NUMBER_VISITS` | без ограничения | Максимальное количество открываемых карточек при сборе ссылок продавцов |
| `PARSER_PAGE_DELAY` | `2` | Пауза между страницами, секунды |
| `PARSER_CARD_DELAY` | `7` | Пауза перед каждым переходом в карточку, секунды |
| `PARSER_CARD_CLOSE_DELAY` | `3` | Пауза после обработки карточки перед закрытием вкладки, секунды |
| `PARSER_CAPTCHA_TIMEOUT` | `300` | Тайм-аут загрузки страницы, секунды |
| `PARSER_FILTER_TIMEOUT` | `15` | Тайм-аут поиска и включения фильтра «В наличии», секунды |
| `PARSER_POPOVER_TIMEOUT` | `10` | Тайм-аут окна продавца, секунды |

Если переменная не добавлена в `.env`, используется значение по умолчанию из
`config.py`.

## Добавить ссылки продавцов в уже готовый отчёт

> При сборе ссылок на продавцов IP-адрес с высокой вероятностью будет
> заблокирован. Запускайте этот этап только после завершения сбора страниц
> поисковой выдачи.

Каждая карточка нового продавца открывается в отдельной вкладке, которая
закрывается после настроенной паузы. Это освобождает ресурсы браузера, но само
по себе не защищает от блокировки; парсер также пропускает уже просмотренных
продавцов и выдерживает настроенную паузу между переходами.

Если вручную закрыть текущую вкладку карточки, сбор ссылок остановится, а уже
собранные ссылки будут сохранены в отчёт.

При запущенном Chrome выполните:

```powershell
uv run python set_seller_links.py "output\megamarket_айфон_17_2026-08-31_09-45.xlsx"
```

Укажите имя своего отчёта вместо имени из примера. Исходный файл не изменяется:
рядом с ним будет создана копия с суффиксом `_with_seller_links.xlsx`.
