# Краткая инструкция по развёртыванию

## 1. Что нужно сделать владельцу проекта

1. Передать администратору сервера:
   - адрес репозитория;
   - готовый файл `.env.remote`.
2. После запуска сервера проверить, что открывается:

   ```text
   http://10.0.0.198:8001/docs
   ```

3. Передать каждому пользователю готовый файл `.env`.

`.env.remote` предназначен только для сервера. Пользователям его передавать
нельзя. Файлы `.env` и `.env.remote` нельзя добавлять в Git.

## 2. Что нужно сделать администратору сервера

На Linux-сервере должны быть установлены Git, Docker Engine и Docker Compose.

### Первый запуск

Выполнить:

```bash
git clone https://github.com/ordenmeny/cdp_parsing.git
cd cdp_parsing
```

Положить полученный `.env.remote` в папку `cdp_parsing`, затем выполнить:

```bash
chmod 600 .env.remote
docker compose up -d --build
docker compose ps
docker compose logs --tail=100 remote-api
curl http://127.0.0.1:8001/openapi.json
```

Если последняя команда вернула JSON, серверная часть работает.

Порт `8001` должен быть доступен пользовательским компьютерам внутри локальной
сети. Если используется UFW:

```bash
sudo ufw allow from <локальная-подсеть> to any port 8001 proto tcp
```

### Обновление сервера

```bash
cd cdp_parsing
git pull
docker compose up -d --build
```

### Остановка сервера

```bash
cd cdp_parsing
docker compose down
```

## 3. Что нужно сделать пользователю

Пользователь работает на Windows. Docker устанавливать не нужно.

### Установка

Открыть PowerShell и выполнить:

```powershell
winget install --id Git.Git -e --source winget
winget install --id OpenJS.NodeJS.LTS -e --source winget
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

Закрыть PowerShell, открыть его снова и выполнить:

```powershell
cd "$env:USERPROFILE\Documents"
git clone https://github.com/ordenmeny/cdp_parsing.git MegamarketControl
cd MegamarketControl
uv sync --locked
npm --prefix frontend ci
npm --prefix frontend run build
```

Положить полученный от владельца файл `.env` в папку:

```text
Документы\MegamarketControl
```

Проверить сервер:

```powershell
Invoke-WebRequest http://10.0.0.198:8001/docs -UseBasicParsing
```

Должен появиться статус `200`.

### Каждый запуск программы

Открыть PowerShell и выполнить команды запуска специального Chrome:

```powershell
$chrome = @("$env:ProgramFiles\Google\Chrome\Application\chrome.exe", "${env:ProgramFiles(x86)}\Google\Chrome\Application\chrome.exe", "$env:LOCALAPPDATA\Google\Chrome\Application\chrome.exe") | Where-Object { Test-Path $_ } | Select-Object -First 1
& $chrome --remote-debugging-port=51112 --user-data-dir="$env:LOCALAPPDATA\chrome-profiles\megamarket-12" --disable-blink-features=AutomationControlled --no-first-run --no-default-browser-check
```

Chrome закрывать нельзя. Проверить его можно командой:

```powershell
Invoke-RestMethod http://127.0.0.1:51112/json/version
```

Открыть ещё одно окно PowerShell и выполнить:

```powershell
cd "$env:USERPROFILE\Documents\MegamarketControl"
uv run uvicorn megamarket.api.app:app --host 127.0.0.1 --port 8000
```

Не закрывая это окно, открыть в браузере:

```text
http://127.0.0.1:8000
```

Для завершения работы нажать `Ctrl+C` в окне с запущенной программой, затем
закрыть специальное окно Chrome.

### Обновление программы

```powershell
cd "$env:USERPROFILE\Documents\MegamarketControl"
git pull
uv sync --locked
npm --prefix frontend ci
npm --prefix frontend run build
```
