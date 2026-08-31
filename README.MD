# Парсер товаров Megamarket

## 1. Получение проекта

```bash
git clone git@gitlab.bpg.team:developer/parsers/unusualparsers/megamarketru_parsek_cdp.git
cd megamarketru_parsek_cdp
```

## 2. Установка uv и зависимостей
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

После установки перезапустите терминал. Другие способы установки описаны в
[официальной документации uv](https://docs.astral.sh/uv/getting-started/installation/).

Находясь в каталоге проекта, установите нужную версию Python и зависимости:

```bash
uv sync --locked
```

## 3. Подготовка профиля Chrome

Парсер использует отдельную копию профиля Chrome. Перед первым запуском
полностью закройте Chrome, затем выполните:

```bash
killall chrome 2>/dev/null
```

```bash
rm -rf "$HOME/.cache/chrome-profiles/megamarket-12"
```

```bash
cp -r "$HOME/.config/google-chrome" "$HOME/.cache/chrome-profiles/megamarket-12"
```

## 4. Запуск Chrome с CDP

Запустите браузер в отдельном терминале:

```bash
TZ="Europe/Moscow" google-chrome-stable \
  --disable-blink-features=AutomationControlled \
  --no-first-run \
  --no-default-browser-check \
  --lang=ru-RU \
  --window-size=1366,768 \
  --force-webrtc-ip-handling-policy=disable_non_proxied_udp \
  --user-data-dir="$HOME/.cache/chrome-profiles/megamarket-12" \
  --remote-debugging-port=51111
```

Не закрывайте это окно Chrome во время работы программы.

## 5. Запуск парсера

Откройте второй терминал, перейдите в каталог проекта и выполните:

```bash
uv run python main.py
```

После этого введите поисковый запрос, например:

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
PARSER_CARD_DELAY=3
PARSER_CAPTCHA_TIMEOUT=300
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
| `PARSER_CARD_DELAY` | `2` | Пауза между карточками, секунды |
| `PARSER_CAPTCHA_TIMEOUT` | `300` | Тайм-аут загрузки страницы, секунды |
| `PARSER_POPOVER_TIMEOUT` | `10` | Тайм-аут окна продавца, секунды |

Если переменная не нужна, не добавляйте её в `.env`: будет использовано
значение по умолчанию из `config.py`.

## Добавление ссылок продавцов в готовый отчёт. 
### !!! При сборе ссылок на продавцов IP-адрес скорее всего будет заблокирован, поэтому запускайте этот этап только после завершения сбора страниц поисковой выдачи

При запущенном Chrome выполните:

```bash
uv run python set_seller_links.py "output/megamarket_айфон_17_2026-08-31_09-45.xlsx"
```

Исходный отчёт не изменяется: рядом будет создана копия с суффиксом `_with_seller_links.xlsx`.