import io
import json
import tarfile
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient

from megamarket.schemas.frontend import FrontendBundleInfo
from megamarket.services.frontend_bundle import (
    FrontendBundleMissing,
    build_archive,
    bundle_files,
    bundle_version,
    get_frontend_bundle,
)
from megamarket.services.frontend_sync import (
    BUNDLES_DIR,
    POINTER_NAME,
    cached_bundle,
    sync_frontend,
)


def make_dist(root: Path, script: str = "console.log(1)") -> Path:
    """Каталог, похожий на результат vite build."""
    dist = root / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text(
        '<!doctype html><script src="/assets/index.js"></script>',
        encoding="utf-8",
    )
    (dist / "assets" / "index.js").write_text(script, encoding="utf-8")
    (dist / "assets" / "index.css").write_text("body{}", encoding="utf-8")
    return dist


def archive_of(dist: Path) -> bytes:
    return build_archive(dist, bundle_files(dist))


def version_of(dist: Path) -> str:
    return bundle_version(dist, bundle_files(dist))


class FakeRemote:
    """Удалённое API в объёме, который нужен синхронизации интерфейса."""

    def __init__(self, dist: Path) -> None:
        self.dist = dist
        self.info_calls = 0
        self.download_calls = 0
        self.archive_override: bytes | None = None

    async def get_frontend_info(self, *, timeout: float) -> FrontendBundleInfo:
        self.info_calls += 1
        archive = self.archive_override
        if archive is None:
            archive = archive_of(self.dist)
        return FrontendBundleInfo(
            version=version_of(self.dist),
            size=len(archive),
        )

    async def download_frontend_bundle(
            self,
            *,
            timeout: float,
            max_size: int,
    ) -> bytes:
        self.download_calls += 1
        if self.archive_override is not None:
            return self.archive_override
        return archive_of(self.dist)


class BundleVersionTests(unittest.TestCase):
    def test_version_survives_rebuild_of_identical_files(self):
        with tempfile.TemporaryDirectory() as first, \
                tempfile.TemporaryDirectory() as second:
            one = make_dist(Path(first))
            two = make_dist(Path(second))
            self.assertEqual(version_of(one), version_of(two))

    def test_version_changes_when_bundle_changes(self):
        with tempfile.TemporaryDirectory() as first, \
                tempfile.TemporaryDirectory() as second:
            one = make_dist(Path(first))
            two = make_dist(Path(second), script="console.log(2)")
            self.assertNotEqual(version_of(one), version_of(two))

    def test_missing_build_is_reported(self):
        with tempfile.TemporaryDirectory() as root:
            get_frontend_bundle.cache_clear()
            with self.assertRaises(FrontendBundleMissing):
                get_frontend_bundle(Path(root))


class FrontendSyncTests(unittest.IsolatedAsyncioTestCase):
    async def test_first_run_downloads_and_unpacks_bundle(self):
        with tempfile.TemporaryDirectory() as root:
            base = Path(root)
            remote = FakeRemote(make_dist(base / "server"))
            cache_dir = base / "cache"

            directory = await sync_frontend(
                remote,
                cache_dir=cache_dir,
                timeout=5,
            )

            self.assertEqual(
                (directory / "index.html").read_text(encoding="utf-8"),
                '<!doctype html><script src="/assets/index.js"></script>',
            )
            self.assertEqual(
                (directory / "assets" / "index.js").read_text(encoding="utf-8"),
                "console.log(1)",
            )
            pointer = json.loads(
                (cache_dir / POINTER_NAME).read_text(encoding="utf-8")
            )
            self.assertEqual(pointer["version"], version_of(remote.dist))
            self.assertEqual(remote.download_calls, 1)

    async def test_unchanged_version_is_not_downloaded_again(self):
        with tempfile.TemporaryDirectory() as root:
            base = Path(root)
            remote = FakeRemote(make_dist(base / "server"))
            cache_dir = base / "cache"

            first = await sync_frontend(remote, cache_dir=cache_dir, timeout=5)
            second = await sync_frontend(remote, cache_dir=cache_dir, timeout=5)

            self.assertEqual(first, second)
            self.assertEqual(remote.info_calls, 2)
            self.assertEqual(remote.download_calls, 1)

    async def test_new_version_replaces_and_prunes_the_old_one(self):
        with tempfile.TemporaryDirectory() as root:
            base = Path(root)
            remote = FakeRemote(make_dist(base / "server"))
            cache_dir = base / "cache"
            old = await sync_frontend(remote, cache_dir=cache_dir, timeout=5)

            (remote.dist / "assets" / "index.js").write_text(
                "console.log(2)",
                encoding="utf-8",
            )
            new = await sync_frontend(remote, cache_dir=cache_dir, timeout=5)

            self.assertNotEqual(old, new)
            self.assertFalse(old.exists())
            self.assertEqual(
                (new / "assets" / "index.js").read_text(encoding="utf-8"),
                "console.log(2)",
            )
            self.assertEqual(
                [entry.name for entry in (cache_dir / BUNDLES_DIR).iterdir()],
                [new.name],
            )

    async def test_archive_escaping_the_cache_is_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            base = Path(root)
            remote = FakeRemote(make_dist(base / "server"))
            cache_dir = base / "cache"
            good = await sync_frontend(remote, cache_dir=cache_dir, timeout=5)

            buffer = io.BytesIO()
            with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
                payload = b"pwned"
                info = tarfile.TarInfo("../../evil.txt")
                info.size = len(payload)
                archive.addfile(info, io.BytesIO(payload))
            remote.archive_override = buffer.getvalue()
            (remote.dist / "assets" / "index.js").write_text(
                "console.log(3)",
                encoding="utf-8",
            )

            with self.assertRaises(tarfile.TarError):
                await sync_frontend(remote, cache_dir=cache_dir, timeout=5)

            self.assertFalse((base / "evil.txt").exists())
            self.assertFalse((cache_dir / "evil.txt").exists())
            # Прошлая версия осталась рабочей.
            self.assertEqual(cached_bundle(cache_dir).directory, good)

    async def test_archive_without_index_is_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            base = Path(root)
            remote = FakeRemote(make_dist(base / "server"))
            cache_dir = base / "cache"

            buffer = io.BytesIO()
            with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
                payload = b"body{}"
                info = tarfile.TarInfo("assets/index.css")
                info.size = len(payload)
                archive.addfile(info, io.BytesIO(payload))
            remote.archive_override = buffer.getvalue()

            with self.assertRaises(ValueError):
                await sync_frontend(remote, cache_dir=cache_dir, timeout=5)
            self.assertIsNone(cached_bundle(cache_dir))


class CachedBundleTests(unittest.TestCase):
    def test_empty_cache_has_nothing_to_offer(self):
        with tempfile.TemporaryDirectory() as root:
            self.assertIsNone(cached_bundle(Path(root)))

    def test_pointer_without_files_is_ignored(self):
        with tempfile.TemporaryDirectory() as root:
            cache_dir = Path(root)
            (cache_dir / POINTER_NAME).write_text(
                json.dumps({"version": "a" * 64}),
                encoding="utf-8",
            )
            self.assertIsNone(cached_bundle(cache_dir))

    def test_version_that_is_not_a_digest_is_ignored(self):
        with tempfile.TemporaryDirectory() as root:
            cache_dir = Path(root)
            escaped = cache_dir / BUNDLES_DIR / ".." / ".."
            escaped.mkdir(parents=True, exist_ok=True)
            (cache_dir / POINTER_NAME).write_text(
                json.dumps({"version": "../.."}),
                encoding="utf-8",
            )
            self.assertIsNone(cached_bundle(cache_dir))


class LocalAppFrontendTests(unittest.TestCase):
    """Статика на «/» и маршруты API живут в одном приложении."""

    def setUp(self):
        from megamarket.api import app as app_module
        from megamarket.api.deps import get_local_seller_service

        self.app_module = app_module
        # Своя заглушка вместо шлюза: тест проверяет маршрутизацию, а не
        # доступность сервера, и в сеть ходить не должен.
        service = SimpleNamespace(get_sellers=_returning([]))
        app_module.app.dependency_overrides[get_local_seller_service] = (
            lambda: service
        )
        self.addCleanup(app_module.app.dependency_overrides.clear)

    def test_frontend_is_served_and_api_routes_still_match(self):
        with tempfile.TemporaryDirectory() as root:
            dist = make_dist(Path(root))
            with patch.object(
                self.app_module,
                "prepare_frontend",
                new=_returning(dist),
            ):
                with TestClient(self.app_module.app) as client:
                    index = client.get("/")
                    self.assertEqual(index.status_code, 200)
                    self.assertIn("<!doctype html>", index.text)

                    asset = client.get("/assets/index.js")
                    self.assertEqual(asset.status_code, 200)
                    self.assertEqual(asset.text, "console.log(1)")

                    # Смонтированная в «/» статика не должна перехватывать
                    # маршруты API, объявленные раньше неё.
                    sellers = client.get("/get_sellers")
                    self.assertEqual(sellers.status_code, 200)
                    self.assertEqual(sellers.json(), [])

    def test_app_starts_without_any_frontend(self):
        with patch.object(
            self.app_module,
            "prepare_frontend",
            new=_returning(None),
        ):
            with TestClient(self.app_module.app) as client:
                self.assertEqual(client.get("/").status_code, 404)
                self.assertEqual(client.get("/get_sellers").status_code, 200)


def _returning(value):
    async def _call(*args, **kwargs):
        return value

    return _call


if __name__ == "__main__":
    unittest.main()
