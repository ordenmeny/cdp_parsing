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