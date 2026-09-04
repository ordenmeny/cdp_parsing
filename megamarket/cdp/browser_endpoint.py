import ipaddress
import json
import socket
import urllib.request
from urllib.parse import urlsplit, urlunsplit

from parsek_cdp.cdp import CDP
from parsek_cdp.core.browser import Browser
from parsek_cdp.core.page import Page
from parsek_cdp.core.target import (
    CDPConnection,
    cdp_host,
    cdp_target_path,
    ws_origin,
)


def resolve_browser_endpoint(endpoint: str) -> str:
    """Заменить DNS-имя хоста на IP, который принимает Chrome DevTools.

    Chrome отклоняет `/json/version`, если HTTP Host содержит произвольное
    имя вроде `host.docker.internal`. Для localhost и готовых IP ничего не
    меняем; Docker-имя разрешаем в адрес шлюза хоста.
    """
    parsed = urlsplit(endpoint)
    hostname = parsed.hostname
    if not hostname or hostname.casefold() == "localhost":
        return endpoint
    try:
        ipaddress.ip_address(hostname)
        return endpoint
    except ValueError:
        pass

    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    addresses = socket.getaddrinfo(
        hostname,
        port,
        family=socket.AF_INET,
        type=socket.SOCK_STREAM,
    )
    if not addresses:
        return endpoint
    address = addresses[0][4][0]
    netloc = f"{address}:{parsed.port}" if parsed.port else address
    return urlunsplit(parsed._replace(netloc=netloc))


def rewrite_websocket_host(websocket_url: str, endpoint: str) -> str:
    """Направить websocket по тому же адресу, что и HTTP endpoint.

    Chrome обычно сообщает ``127.0.0.1`` в ``webSocketDebuggerUrl``. Внутри
    Docker это адрес контейнера, поэтому его нужно заменить адресом хоста.
    """
    websocket = urlsplit(websocket_url)
    browser_endpoint = urlsplit(endpoint)
    return urlunsplit(websocket._replace(netloc=browser_endpoint.netloc))


async def connect_browser(
    endpoint: str,
    *,
    page_class: type[Page] = Page,
) -> Browser:
    """Подключиться к Chrome напрямую или из Docker-контейнера."""
    resolved_endpoint = resolve_browser_endpoint(endpoint)
    with urllib.request.urlopen(
        f"{resolved_endpoint.rstrip('/')}/json/version"
    ) as response:
        info = json.loads(response.read())

    websocket_url = rewrite_websocket_host(
        info["webSocketDebuggerUrl"],
        resolved_endpoint,
    )
    cdp_host.set(ws_origin(websocket_url))
    cdp_target_path.set("/devtools/page/")

    bootstrap = CDPConnection()
    await bootstrap._open(websocket_url)
    try:
        browser_info = (await CDP(bootstrap).Target.get_target_info()).target_info
    finally:
        await bootstrap.close()

    browser = Browser(browser_info, page_class=page_class)
    await browser.connect(websocket_url)
    await browser._discover()
    return browser
