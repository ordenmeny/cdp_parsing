"""Опциональные метрики исходящих команд Chrome DevTools Protocol."""

from __future__ import annotations

import json
import time
from collections import Counter
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field

from parsek_cdp.core.target import CDPConnection


@dataclass(frozen=True, slots=True)
class CDPMetricsSnapshot:
    calls: Counter[str]
    response_bytes: int
    failures: int
    timestamp: float


@dataclass(slots=True)
class CDPMetrics:
    """Накопленные вызовы CDP и приблизительный объём их ответов."""

    calls: Counter[str] = field(default_factory=Counter)
    response_bytes: int = 0
    failures: int = 0
    started_at: float = field(default_factory=time.perf_counter)

    def snapshot(self) -> CDPMetricsSnapshot:
        return CDPMetricsSnapshot(
            calls=self.calls.copy(),
            response_bytes=self.response_bytes,
            failures=self.failures,
            timestamp=time.perf_counter(),
        )

    def print_summary(
            self,
            label: str,
            *,
            since: CDPMetricsSnapshot | None = None,
    ) -> None:
        """Вывести сводку целиком или разницу относительно снимка."""
        if since is None:
            calls = self.calls
            response_bytes = self.response_bytes
            failures = self.failures
            started_at = self.started_at
        else:
            calls = self.calls - since.calls
            response_bytes = self.response_bytes - since.response_bytes
            failures = self.failures - since.failures
            started_at = since.timestamp

        total_calls = sum(calls.values())
        megabytes = response_bytes / (1024 * 1024)
        elapsed = time.perf_counter() - started_at
        print(
            f"CDP [{label}]: вызовов — {total_calls}, "
            f"ответов — {megabytes:.2f} МБ, ошибок — {failures}, "
            f"время — {elapsed:.2f} сек."
        )
        for method, count in sorted(
                calls.items(),
                key=lambda item: (-item[1], item[0]),
        ):
            print(f"  {method}: {count}")


_active_metrics: ContextVar[tuple[CDPMetrics, ...]] = ContextVar(
    "active_cdp_metrics",
    default=(),
)
_original_send = CDPConnection.send
_metrics_installed = False


def _response_size(value: object) -> int:
    """Оценить размер JSON-ответа тем же UTF-8 представлением."""
    try:
        serialized = json.dumps(
            value,
            ensure_ascii=False,
            separators=(",", ":"),
            default=str,
        )
    except (TypeError, ValueError):
        serialized = repr(value)
    return len(serialized.encode("utf-8"))


async def _measured_send(
        self: CDPConnection,
        method: str,
        params: dict,
) -> object:
    metrics_group = _active_metrics.get()
    for metrics in metrics_group:
        metrics.calls[method] += 1

    try:
        result = await _original_send(self, method, params)
    except BaseException:
        for metrics in metrics_group:
            metrics.failures += 1
        raise

    size = _response_size(result)
    for metrics in metrics_group:
        metrics.response_bytes += size
    return result


def _install_metrics_wrapper() -> None:
    global _metrics_installed
    if _metrics_installed:
        return
    CDPConnection.send = _measured_send
    _metrics_installed = True


@contextmanager
def collect_cdp_metrics(
        enabled: bool,
        *,
        total_label: str = "Итого за прогон",
) -> Iterator[CDPMetrics | None]:
    """Считать CDP-вызовы внутри блока и напечатать итог при выходе."""
    if not enabled:
        yield None
        return

    _install_metrics_wrapper()
    metrics = CDPMetrics()
    token = _active_metrics.set((*_active_metrics.get(), metrics))
    try:
        yield metrics
    finally:
        _active_metrics.reset(token)
        metrics.print_summary(total_label)
