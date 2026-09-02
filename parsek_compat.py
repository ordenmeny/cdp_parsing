"""Compatibility fixes for races in the installed ``parsek-cdp`` release."""

from __future__ import annotations

from parsek_cdp.cdp import Target as TargetDomain
from parsek_cdp.core.browser import Browser
from parsek_cdp.core.target import Target
from websockets.exceptions import InvalidStatus


_original_browser_discover = Browser._discover


def _is_missing_target(error: InvalidStatus) -> bool:
    """Whether Chrome rejected a websocket for an already destroyed target."""
    response = error.response
    body = bytes(response.body).decode("utf-8", errors="replace").casefold()
    return response.status_code in {404, 500} and "no such target id" in body


async def _safe_on_target_created(
        self: Target,
        event: TargetDomain.TargetCreated,
) -> None:
    """Track a target without leaking an exception when it disappears early.

    Chrome may emit ``Target.targetCreated`` for a short-lived iframe or worker
    and destroy it before parsek-cdp opens that target's websocket.  Version
    0.1.8 leaves the resulting ``InvalidStatus`` in an unobserved asyncio task.
    Treat Chrome's explicit ``No such target id`` as the normal destroy race,
    but keep propagating every other websocket failure.
    """
    info = event.target_info
    parent_id = info.opener_id or info.parent_frame_id

    # Browser.watch() отдельно создаёт Page для верхнеуровневых вкладок.
    # Если общий обработчик тоже подключится к тому же target, Яндекс Браузер
    # может перестать отвечать на Page.getFrameTree во втором соединении.
    if (
        self.type_ == "browser"
        and info.type_ in {"page", "tab"}
    ):
        return

    if parent_id is not None and parent_id != self.id:
        for child in list(self.targets):
            await child._on_target_created(event)
        return

    # Duplicate discovery events must not create a second websocket connection.
    if info.target_id in self._targets:
        self._targets[info.target_id]._target = info
        return

    target = Target(info, self)
    self._targets[info.target_id] = target
    try:
        await target.connect()
    except InvalidStatus as error:
        if self._targets.get(info.target_id) is target:
            self._targets.pop(info.target_id, None)
        if _is_missing_target(error):
            return
        raise
    except BaseException:
        if self._targets.get(info.target_id) is target:
            self._targets.pop(info.target_id, None)
        raise


async def _discover_without_empty_pages(self: Browser) -> None:
    """Не подключаться к пустым служебным page-targets Яндекс Браузера.

    Яндекс Браузер публикует target с ``type=page`` и пустым URL, однако не
    отвечает на ``Page.getFrameTree`` для него. Стандартный ``_discover`` ждёт
    этот ответ бесконечно и не завершает ``Browser.connect_http``.
    """
    empty_page_ids = [
        target.id
        for target in self.targets
        if target.type_ in {"page", "tab"} and not target.url.strip()
    ]
    for target_id in empty_page_ids:
        self._targets.pop(target_id, None)
    await _original_browser_discover(self)


def install_parsek_target_race_fix() -> None:
    """Install compatibility fixes once for this Python process."""
    current = Target._on_target_created
    if not getattr(current, "__parsek_missing_target_fix__", False):
        _safe_on_target_created.__parsek_missing_target_fix__ = True
        Target._on_target_created = _safe_on_target_created

    current_discover = Browser._discover
    if not getattr(current_discover, "__parsek_empty_page_fix__", False):
        _discover_without_empty_pages.__parsek_empty_page_fix__ = True
        Browser._discover = _discover_without_empty_pages
