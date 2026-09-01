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

**5. Запустить парсер**

```powershell
pip install uv
```

```powershell
uv run python main.py
```

## Пометки

- Первая команда закроет все окна Chrome без сохранения вкладок.
- `robocopy` считает успехом коды возврата 0–7, проверить: `$LASTEXITCODE`.
- Окно Chrome из шага 2 держать открытым: парсер работает в нём, капча решается там же.
- Обычный Chrome можно запускать параллельно, он не мешает.
- Ошибка подключения на шаге 3 — Chrome уже был запущен с этим профилем и открыл окно в старом процессе без порта. Закрыть, повторить шаг 2.
- В скопированном профиле сайт может не помнить вход — залогиниться один раз в этом окне.
- Без копирования профиля: тот же запуск с `--user-data-dir="$env:LOCALAPPDATA\chrome-profiles\megamarket-clean"`, Chrome создаст чистый профиль сам.
