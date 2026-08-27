```bash
TZ="Europe/Moscow" google-chrome-stable \
  --disable-blink-features=AutomationControlled \
  --no-first-run --no-default-browser-check \
  --lang=ru-RU \
  --user-data-dir="$HOME/.cache/chrome-profiles/megamarket" \
  --remote-debugging-port=51111 \
  --proxy-server=http://46.161.46.26:9479
```





