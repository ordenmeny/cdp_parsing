Два типа поиска:
# https://megamarket.ru/catalog/?q=айфон17
# https://megamarket.ru/catalog/page-2/?q=айфон17

Здесь произошел редирект с https://megamarket.ru/catalog/?q=айфон16 на:
# https://megamarket.ru/catalog/iphone-16/#?related_search=айфон16
# https://megamarket.ru/catalog/iphone-16/page-2/#?related_search=айфон16


## Запуск браузера

```bash
TZ="Europe/Moscow" google-chrome-stable
    --disable-blink-features=AutomationControlled
    --no-first-run --no-default-browser-check
    --lang=ru-RU --window-size=1366,768
    --force-webrtc-ip-handling-policy=disable_non_proxied_udp
    --user-data-dir="$HOME/.cache/chrome-profiles/megamarket-12"
    --remote-debugging-port=51111
```


## Запуск скрипта
```bash
python main.py
```


