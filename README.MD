# Chrome с портом 51111 (Windows, PowerShell)

Chrome с 136-й версии включает порт отладки только с отдельным каталогом
профиля, поэтому «текущий» профиль сначала копируется в свою папку.

**1. Скопировать профиль (один раз, Chrome должен быть закрыт полностью)**

```powershell
Get-Process chrome -ErrorAction SilentlyContinue | Stop-Process -Force
```

```powershell
robocopy "$env:LOCALAPPDATA\Google\Chrome\User Data" "$env:LOCALAPPDATA\chrome-profiles\megamarket-12" /E /R:0 /W:0 /NFL /NDL /NJH /NJS /XD Cache "Code Cache" GPUCache ShaderCache GrShaderCache "Service Worker" Crashpad
```

**2. Запустить Chrome**

```powershell
$chrome = @("$env:ProgramFiles\Google\Chrome\Application\chrome.exe", "${env:ProgramFiles(x86)}\Google\Chrome\Application\chrome.exe", "$env:LOCALAPPDATA\Google\Chrome\Application\chrome.exe") | Where-Object { Test-Path $_ } | Select-Object -First 1
```

```powershell
& $chrome --remote-debugging-port=51111 --user-data-dir="$env:LOCALAPPDATA\chrome-profiles\megamarket-12" --disable-blink-features=AutomationControlled --no-first-run --no-default-browser-check --lang=ru-RU --window-size=1366,768
```

**3. Проверить порт** — должна вывестись версия Chrome

```powershell
Invoke-RestMethod http://127.0.0.1:51111/json/version
```

**4. Указать порт парсеру** — в коде по умолчанию 51112

```powershell
Add-Content -Path .env -Value "`nPARSER_BROWSER_PORT=51111" -Encoding ascii
```

**5. Установить uv**
## `uv` — программа для установки Python, зависимостей и запуска проекта.
[официальной документации uv](https://docs.astral.sh/uv/getting-started/installation/).

```powershell
$env:NO_PROXY="127.0.0.1,localhost" 
$env:no_proxy="127.0.0.1,localhost"
```

```powershell 
uv run python main.py
```


**6. Использование**

Если доступ к сайту временно заблокирован, после снятия блокировки сбор можно продолжить с нужной страницы, указав её номер после поискового запроса. Результат каждого запуска сохраняется в отдельный файл. После завершения всех итераций полученные файлы можно объединить в один отчёт, указав путь к каталогу с результатами.

Дойдя до конца, сайт может начать выдачу заново — после 64-й страницы отдать вторую. Такое кольцо распознаётся по резко упавшему приросту новых карточек; сбор останавливается после двух подозрительных страниц подряд (`PARSER_REPEAT_PAGES_LIMIT`, `PARSER_REPEAT_NEW_SHARE`).

Отдельный режим `scrolling||<запрос>` собирает выдачу иначе: страница открывается один раз, а новые карточки добираются нажатием «Показать ещё» — без перезагрузки документа и без адресов вида `page-N`. Номер страницы этому режиму не передаётся; ограничить число догрузок можно переменной `PARSER_NUMBER_CLICKS`.


##### На выбор четыре варианта:
```powershell
Запрос[||страница], scrolling||<запрос> или join||<папка>: айфон 17 - начать парсинг по поиску.
```
```powershell
Запрос[||страница], scrolling||<запрос> или join||<папка>: айфон 17||15 - начать парсинг с 15-й страницы.
```

```powershell
Запрос[||страница], scrolling||<запрос> или join||<папка>: join||<Путь до папки> - объединить все файлы с результатами в один.
```

```powershell
Запрос[||страница], scrolling||<запрос> или join||<папка>: scrolling||makita - собрать выдачу без перехода по страницам.
```

**7. Экстренная остановка сбора**
Если нужно сохранить уже собранные данные, необходимо закрыть вкладку браузера.
Терминал не трогать до тех пор, пока процесс не остановится штатно.



Поля Sellers:
seller_id - id продавца 
name: str (unique)
link_to_seller: str (unique)
link_to_card: str (любая ссылка на товар)
status: "confirmed", "unconfirmed", "incorrect"
email: str
orgn: str
official_name: str


id продавца получаем из нормализованной ссылки normalize_link (megamarket/utils.py),
например, https://megamarket.ru/catalog/details/zu-greenworks-2945107-100031211934_13635
Здесь id продавца 13635.


Во время первоначального сбора получаем список из объектов селлеров (sellers).
Парсер проверяет, есть ли селлер в sellers.
Если ДА:
    Если статус confirmed: парсер устанавливает в CardToPars seller_link.
    Если статус другой: парсер не устанавливает в CardToPars seller_link, поле в excel пустое.

Если НЕТ:
    ----------------------------
    Заносится в БД новый объект Sellers.
    link_to_seller - через класс SlugifyCard создается слаг
    name, link_to_card
    status - unconfirmed
    inn
    mobile
    rating
    --------------------------


! В excel файл помечает только ссылки селлеров, которые confirmed. Если ссылка не confirmed, то в файле пусто.


API (define_sellers, на вход может поступить excel):
Сначала добавляем в БД всех новых селлеров из excel файла, если он пришел на вход.
После этого начинается процесс определения статусов:
Выбираем из БД всех селлеров, у которых статус unconfirmed.
Делаем парсинг страниц этих селлеров:
    Если страница 404 по этой ссылке - в БД помечаем поле селлера как incorrect.
    Если ссылка ведет не на 404, а на страницу продавца - парсим данные о продавце.
        Заносим данные об этом продавце в БД. Помечаем статус как confirmed.
        Если есть excel-файл, то устанавливаем для этого продавца ссылку, если она confirmed.


API (get_sellers)
Через query-параметр можно передать "confirmed", "unconfirmed", "incorrect" 
и сделать фильтр по этому параметру. Если query-параметра нет, получаем всех продавцов.

API PATCH (set_sellers)
Можно передать один или несколько селлеров с определенными параметрами.
Можно передать, например, правильную ссылку или статус.
Идентифицировать селлера можно либо по id, либо по name.


**7. Структура проекта**

```
main.py                     точка входа: поиск, scrolling, join
set_seller_links.py         точка входа: дополнить готовый отчёт ссылками продавцов
megamarket/
├── config.py               Settings (окружение) и ParserSettings (как собирать)
├── domain.py               модели данных: CardToPars, Stock
├── exceptions.py
├── utils.py                разбор введённой команды и текстовые помощники
├── slug.py                 ссылка продавца из названия
├── cdp/                    слой браузера
│   ├── cdp_metrics.py      подсчёт CDP-вызовов
│   ├── extractors.py       JS-экстракторы карточек и состояния страницы
│   └── parsek_compat.py    заплатки к parsek-cdp
├── parsers/                сбор выдачи
│   ├── base_parser.py      общий поток постраничного обхода
│   ├── parsing.py          MegamarketParsePage, MegamarketParseCard
│   └── scrolling.py        MegamarketScrollPage — догрузка «Показать ещё»
└── storage/                результат
    └── report.py           ExcelReport, join_excel_reports, ExcelCardsReport
scripts/measure_cdp.py      замер CDP-нагрузки на локальной странице
output/                     отчёты
```

Импорты внутри пакета абсолютные: `from megamarket.domain import CardToPars`.
Пакет можно импортировать, не запуская парсер, — модели, настройки и база
продавцов не тянут за собой браузер.


Пример использования:
```python
import asyncio

from main import connect_browser
from megamarket.config import settings
from megamarket.exceptions import SiteBlocked
from megamarket.parsers.seller_page import MegamarketSellerPage, SellerPageState


async def main():
    browser = await connect_browser(settings.browser_endpoint)
    pages = MegamarketSellerPage(browser)

    result = await pages.parse("https://megamarket.ru/shop/a-pole/")

    match result.state:
        case SellerPageState.FOUND:
            print(result.info.official_name, result.info.ogrn, result.info.email)
        case SellerPageState.NOT_FOUND:
            print("такого магазина нет")
        case SellerPageState.UNKNOWN:
            print("страница не ответила — ссылку не судим")


asyncio.run(main())
```