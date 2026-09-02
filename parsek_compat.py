"""Compatibility fixes for races in the installed ``parsek-cdp`` release."""

from __future__ import annotations

from parsek_cdp.cdp import Target as TargetDomain
from parsek_cdp.core.target import Target
from websockets.exceptions import InvalidStatus


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


def install_parsek_target_race_fix() -> None:
    """Install the target-created race fix once for this Python process."""
    current = Target._on_target_created
    if getattr(current, "__parsek_missing_target_fix__", False):
        return

    _safe_on_target_created.__parsek_missing_target_fix__ = True
    Target._on_target_created = _safe_on_target_created
