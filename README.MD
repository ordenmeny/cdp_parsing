# Megamarket Control

## Установка на Windows

### 1. Установить программы

Откройте PowerShell и выполните:

```powershell
winget install --id Git.Git -e --source winget
winget install --id OpenJS.NodeJS.LTS -e --source winget
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

Google Chrome должен быть установлен обычным способом. После установки
закройте PowerShell и откройте его снова.

Проверьте команды:

```powershell
git --version
uv --version
npm --version
```

### 2. Получить проект

```powershell
cd "$env:USERPROFILE\Documents"
git clone https://github.com/ordenmeny/cdp_parsing.git MegamarketControl
cd MegamarketControl
```

Все дальнейшие команды выполняются из папки `MegamarketControl`.

### 3. Получить настройки

Администратор должен выдать файл `.env`. Положите его рядом с `README.MD`.

В пользовательском `.env` находятся только внутренний адрес удалённого API,
токен и настройки Chrome. Например, адрес может выглядеть как
`http://10.0.0.25:8001`. Реквизитов PostgreSQL в файле быть не должно. Пример
состава находится в `.env.example`.

Не публикуйте `.env` и не передавайте токен посторонним.

### 4. Подготовить приложение

Эти команды нужны при первой установке:

```powershell
uv sync --locked
npm --prefix frontend ci
npm --prefix frontend run build
```

`uv` установит Python 3.13, API и парсер, а npm соберёт пользовательский
интерфейс.

## Подготовка Chrome

Парсер работает через отдельное окно Chrome. При первой настройке закройте все
окна Chrome и выполните:

```powershell
Get-Process chrome -ErrorAction SilentlyContinue | Stop-Process -Force
robocopy "$env:LOCALAPPDATA\Google\Chrome\User Data" "$env:LOCALAPPDATA\chrome-profiles\megamarket-12" /E /R:0 /W:0 /NFL /NDL /NJH /NJS /XD Cache "Code Cache" GPUCache ShaderCache GrShaderCache "Service Worker" Crashpad
```

Профиль копируется только один раз. Перед каждым запуском парсера откройте
специальное окно Chrome двумя командами:

```powershell
$chrome = @("$env:ProgramFiles\Google\Chrome\Application\chrome.exe", "${env:ProgramFiles(x86)}\Google\Chrome\Application\chrome.exe", "$env:LOCALAPPDATA\Google\Chrome\Application\chrome.exe") | Where-Object { Test-Path $_ } | Select-Object -First 1
& $chrome --remote-debugging-port=51112 --user-data-dir="$env:LOCALAPPDATA\chrome-profiles\megamarket-12" --disable-blink-features=AutomationControlled --no-first-run --no-default-browser-check --lang=ru-RU --window-size=1366,768
```

Не закрывайте открывшееся окно. Проверка подключения:

```powershell
Invoke-RestMethod http://127.0.0.1:51112/json/version
```

## Запуск локального приложения

Оставьте специальное окно Chrome открытым. В новом PowerShell из папки проекта
выполните:

```powershell
uv run uvicorn megamarket.api.app:app --host 127.0.0.1 --port 8000
```

Затем откройте:

```text
http://127.0.0.1:8000
```

Окно PowerShell с API нельзя закрывать до окончания работы. Для остановки
нажмите `Ctrl+C`.

Frontend запускает сбор через локальную ручку `POST /parse`. Он сам добавляет
к запросу служебный префикс `scrolling||`; пользователю вводить его не нужно.
Страницами Megamarket управляет Chrome пользователя, а данные продавцов
локальное приложение получает через удалённый API.

## Как пользоваться

### Собрать товары

На вкладке **Обработка**:

1. Введите обычный запрос, например `makita`.
2. Нажмите **Запустить и скачать Excel**.
3. Не закрывайте специальное окно Chrome.
4. После завершения браузер скачает Excel-файл.

Если Megamarket показывает капчу, пройдите её вручную в специальном окне.

### Проверить продавцов

На вкладке **Обработка** можно прикрепить `.xlsx`, указать количество продавцов
и нажать **Проверить и скачать файл**. Новые продавцы будут добавлены в базу,
после чего указанное количество продавцов пройдёт проверку.

Обработанный файл скачивается с тем же именем. Ссылка остаётся только у продавца
со статусом **Корректный**. Исходный файл программа не изменяет.

Без файла приложение проверит продавцов со статусом **На проверке** и обновит
только базу. На вкладке **Продавцы** доступны поиск, фильтрация, редактирование
и пагинация по 10 записей.

## Повторный запуск

После первоначальной установки достаточно:

1. открыть специальное окно Chrome;
2. запустить локальное приложение командой с `uvicorn`;
3. открыть `http://127.0.0.1:8000`.

Повторно выполнять `uv sync` и сборку frontend не нужно.

## Обновление

После получения новой версии выполните:

```powershell
git pull
uv sync --locked
npm --prefix frontend ci
npm --prefix frontend run build
```

После этого запускайте приложение обычной командой с `uvicorn`.

## Если что-то не работает

### Не открывается интерфейс

Проверьте, что окно с Uvicorn открыто и содержит строку:

```text
Uvicorn running on http://127.0.0.1:8000
```

Если порт занят, остановите ранее запущенную копию программы через `Ctrl+C`.

### Приложение не подключается к Chrome

```powershell
Invoke-RestMethod http://127.0.0.1:51112/json/version
```

Если команда завершается ошибкой, закройте все окна Chrome и заново запустите
специальное окно.

### Не загружаются продавцы

Проверьте интернет, VPN и выданный администратором `.env`. Локальное приложение
не подключается к PostgreSQL напрямую.

## Необязательный запуск пользователя через Docker

Если Docker всё же установлен, локальную часть можно запустить отдельно:

```powershell
docker compose -f docker-compose.local.yml up -d --build
```

Основной `docker-compose.yml` предназначен только для удалённого сервера.

## Проверка схемы «сервер + пользователь» на одном компьютере

Это рекомендуемый режим для разработчика: удалённый API запускается точно так
же, как на сервере, а локальное приложение — точно так же, как у пользователя.
Контейнер использует сеть Linux-хоста, поэтому видит те же LAN- и VPN-маршруты
до PostgreSQL, что и сам компьютер.

Сначала освободите порт `8001`, если на нём остался ранее запущенный Uvicorn.
Затем поднимите серверную часть через Docker:

```bash
docker compose up -d --build
docker compose logs --tail=100 remote-api
```

В локальном `.env` укажите LAN-адрес этого компьютера. Для текущей сети пример
выглядит так:

```dotenv
PARSER_REMOTE_API_URL=http://10.17.4.17:8001
```

После этого запустите специальное окно Chrome и локальное приложение без
Docker:

```bash
uv run uvicorn megamarket.api.app:app --host 127.0.0.1 --port 8000
```

Откройте `http://127.0.0.1:8000`. В этой схеме локальный процесс не получает
реквизиты PostgreSQL: они находятся только в `.env.remote` серверного
контейнера.

Остановить серверную часть:

```bash
docker compose down
```

Инструкция администратору находится в
[`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md).
