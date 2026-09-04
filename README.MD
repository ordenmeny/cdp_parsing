# Инструкция по установке


### 1. Установить необходимые программы

Откройте PowerShell и выполните:
```powershell
winget install --id Git.Git -e --source winget
winget install --id GNU.Nano -e --source winget
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

`nano` — простой текстовый редактор, им создаётся файл настроек на шаге 3.

Установите Google Chrome, если он ещё не установлен. После установки закройте
PowerShell и откройте его снова.

### 2. Скачать репозиторий

```powershell
cd "$env:USERPROFILE\Documents"
git clone https://github.com/ordenmeny/cdp_parsing.git MegamarketControl
cd MegamarketControl
```

### 3. Создать файл настроек

Получите у администратора токен доступа. Затем из папки `MegamarketControl`
откройте новый файл:

```powershell
nano .env
```

Впишите пять строк, подставив полученный токен вместо `<токен>`:

```dotenv
PARSER_REMOTE_API_URL=http://10.0.4.69:8001
PARSER_REMOTE_API_TOKEN=<токен>
PARSER_REMOTE_API_TIMEOUT=600
PARSER_BROWSER_HOST=127.0.0.1
PARSER_BROWSER_PORT=51112
```

Токен длинный, набирать его руками не нужно — скопируйте и вставьте правой
кнопкой мыши. Угловые скобки не оставляйте.

Сохраните и закройте файл: нажмите `Ctrl+O`, затем `Enter`, затем `Ctrl+X`.

Проверьте, что получилось:

```powershell
Get-Content .env
```

Должны появиться те же пять строк, а в строке с токеном — сам токен.

Проверьте доступность сервера:

```powershell
Invoke-WebRequest http://10.0.4.69:8001/docs -UseBasicParsing
```

В результате должен появиться статус `200`.

### 4. Подготовить программу

Выполните из папки `MegamarketControl`:

```powershell
uv sync --locked
```

Команда обязательна при первой установке и может занять несколько минут.

Интерфейс собирать не нужно: при каждом запуске программа сама скачивает его
с сервера и запоминает в
`%LOCALAPPDATA%\MegamarketControl\frontend`. Заново он скачивается только
после того, как интерфейс обновят на сервере.

## Каждый запуск программы

### 1. Запустить специальное окно Chrome

Откройте PowerShell и выполните:

```powershell
$chrome = @("$env:ProgramFiles\Google\Chrome\Application\chrome.exe", "${env:ProgramFiles(x86)}\Google\Chrome\Application\chrome.exe", "$env:LOCALAPPDATA\Google\Chrome\Application\chrome.exe") | Where-Object { Test-Path $_ } | Select-Object -First 1
& $chrome --remote-debugging-port=51112 --user-data-dir="$env:LOCALAPPDATA\chrome-profiles\megamarket-12" --disable-blink-features=AutomationControlled --no-first-run --no-default-browser-check
```

Не закрывайте открывшееся окно Chrome во время работы.

Проверить Chrome можно командой:

```powershell
Invoke-RestMethod http://127.0.0.1:51112/json/version
```

Если появилась информация о версии Chrome, браузер готов.

### 2. Запустить приложение

Откройте ещё одно окно PowerShell. Перейдите в ту же директорию и запустите веб-сервер:

```powershell
cd "$env:USERPROFILE\Documents\MegamarketControl"
uv run uvicorn megamarket.api.app:app --host 127.0.0.1 --port 8000
```

Не закрывайте это окно PowerShell во время работы.

### 3. Открыть интерфейс

Откройте в браузере:

```text
http://127.0.0.1:8000
```

## Как пользоваться

### Собрать товары

1. Откройте вкладку **Обработка**.
2. Введите обычный поисковый запрос, например `makita`.
3. Нажмите **Запустить и скачать Excel**.
4. Не закрывайте специальное окно Chrome.
5. После завершения Excel-файл скачается автоматически.

### Проверить продавцов

1. На вкладке **Обработка** выберите Excel-файл.
2. Укажите количество продавцов.
3. Нажмите **Проверить и скачать файл**.

Обработанный файл скачается с тем же именем. Ссылка останется только у продавца
со статусом **Корректный**. Если не выбирать файл, программа проверит продавцов
в базе без скачивания Excel.

На вкладке **Продавцы** доступны просмотр, поиск, фильтрация и редактирование.

## Завершение работы

1. Дождитесь окончания текущей операции.
2. Нажмите `Ctrl+C` в окне PowerShell с запущенным приложением.
3. Закройте специальное окно Chrome.

## Обновление кода программы

Откройте PowerShell и выполните:

```powershell
cd "$env:USERPROFILE\Documents\MegamarketControl"
git pull
uv sync --locked
```

После обновления запускайте программу обычным способом. Интерфейс обновится
сам при первом запуске.

## Если программа не запускается

Проверьте сервер:

```powershell
Invoke-WebRequest http://10.0.4.69:8001/docs -UseBasicParsing
```

Проверьте Chrome:

```powershell
Invoke-RestMethod http://127.0.0.1:51112/json/version
```

Если обе проверки работают, закройте ранее запущенную копию программы через
`Ctrl+C` и снова выполните команду запуска приложения.

### Страница не открывается

При запуске программа скачивает интерфейс с сервера. Посмотрите на окно
PowerShell с запущенным приложением:

- `Не удалось обновить интерфейс с сервера` вместе с `Открыт интерфейс,
  скачанный ранее` — сервер недоступен, но программа работает на прошлой
  версии интерфейса. Проверьте сервер по инструкции выше.
- `Интерфейс недоступен` — сервер недоступен, и скачанной копии ещё нет. Так
  бывает при первом запуске без связи с сервером. Дождитесь доступности
  сервера и запустите программу снова.
