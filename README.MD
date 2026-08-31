## Запуск браузера

```bash
  killall chrome 2>/dev/null
```

```bash
  rm -rf "$HOME/.cache/chrome-profiles/megamarket-12"
```

```bash
  cp -r "$HOME/.config/google-chrome" "$HOME/.cache/chrome-profiles/megamarket-12"
```

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


## Запуск скрипта
```bash
python main.py
```


