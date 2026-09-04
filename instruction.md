# Развёртывание Megamarket Control

## 1) В пользовательском `.env` указать этот адрес:

```dotenv
PARSER_REMOTE_API_URL=http://<внутренний-IP-сервера>:8001
```

## 2) На сервере
1. Положить `.env.remote` в корень проекта

2. Собрать и запустить серверную часть:
```bash
docker compose up -d --build
```

## 3. Что требуется от конечного пользователя

Пользователю нужны Windows, Google Chrome, Git, `uv` и Node.js.

### Установка

1. Установить инструменты в PowerShell:
```powershell
winget install --id Git.Git -e --source winget
winget install --id OpenJS.NodeJS.LTS -e --source winget
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

2. Перезапустить PowerShell и скачать проект:
```powershell
cd "$env:USERPROFILE\Documents"
git clone https://github.com/ordenmeny/cdp_parsing.git MegamarketControl
cd MegamarketControl
```

3. Положить полученный от владельца `.env` рядом с `README.MD`.

4. Подготовить приложение:

```powershell
uv sync --locked
npm --prefix frontend ci
npm --prefix frontend run build
```

### Запуск

1. Запустить специальное окно Chrome:

```powershell
$chrome = @("$env:ProgramFiles\Google\Chrome\Application\chrome.exe", "${env:ProgramFiles(x86)}\Google\Chrome\Application\chrome.exe", "$env:LOCALAPPDATA\Google\Chrome\Application\chrome.exe") | Where-Object { Test-Path $_ } | Select-Object -First 1
& $chrome --remote-debugging-port=51112 --user-data-dir="$env:LOCALAPPDATA\chrome-profiles\megamarket-12" --disable-blink-features=AutomationControlled
```

2. В другом PowerShell из папки проекта запустить локальное приложение:
```powershell
uv run uvicorn megamarket.api.app:app --host 127.0.0.1 --port 8000
```

3. Открыть интерфейс:
```text
http://127.0.0.1:8000
```