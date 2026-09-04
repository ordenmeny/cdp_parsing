import ast
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from megamarket.db.models import SellerJob, SellerJobItem, Sellers
from megamarket.cdp.browser_endpoint import (
    resolve_browser_endpoint,
    rewrite_websocket_host,
)
from megamarket.domain import SellerObservationState, SellerStatus
from megamarket.parsers.seller_page import SellerPageResult, SellerPageState
from megamarket.schemas.seller_jobs import (
    SellerCandidate,
    SellerJobFinishResponse,
    SellerJobStartResponse,
    SellerObservation,
)
from megamarket.services.local_sellers import LocalSellerService
from megamarket.services.sellers import SellerJobService


class ApiBoundaryTests(unittest.TestCase):
    @patch(
        "megamarket.cdp.browser_endpoint.socket.getaddrinfo",
        return_value=[
            (2, 1, 6, "", ("172.17.0.1", 51112)),
        ],
    )
    def test_docker_browser_hostname_is_replaced_with_ip(self, _):
        self.assertEqual(
            resolve_browser_endpoint("http://host.docker.internal:51112"),
            "http://172.17.0.1:51112",
        )

    def test_browser_websocket_uses_reachable_endpoint(self):
        self.assertEqual(
            rewrite_websocket_host(
                "ws://127.0.0.1:51112/devtools/browser/browser-id",
                "http://192.168.65.254:51112",
            ),
            "ws://192.168.65.254:51112/devtools/browser/browser-id",
        )

    def test_local_api_has_no_database_imports(self):
        project = Path(__file__).resolve().parents[1]
        local_files = [
            project / "megamarket/api/app.py",
            project / "megamarket/api/deps.py",
            project / "megamarket/api/sellers.py",
            project / "megamarket/clients/remote_api.py",
            project / "megamarket/services/local_sellers.py",
        ]
        forbidden = ("sqlalchemy", "megamarket.db", "megamarket.repositories")
        for path in local_files:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            imports = [
                node.module or ""
                for node in ast.walk(tree)
                if isinstance(node, ast.ImportFrom)
            ] + [
                alias.name
                for node in ast.walk(tree)
                if isinstance(node, ast.Import)
                for alias in node.names
            ]
            self.assertFalse(
                any(name.startswith(forbidden) for name in imports),
                f"Локальный модуль {path.name} импортирует слой БД",
            )


class LocalSellerServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_parses_locally_and_submits_observation_to_remote(self):
        remote = MagicMock()
        remote.start_job = AsyncMock(return_value=SellerJobStartResponse(
            job_id="job-1",
            added=1,
            filename=None,
            sellers=[SellerCandidate(
                seller_id="13635",
                name="Магазин",
                link_to_seller="https://megamarket.ru/shop/magazin/",
            )],
        ))
        remote.observe = AsyncMock()
        remote.finish_job = AsyncMock(return_value=SellerJobFinishResponse(
            job_id="job-1",
            added=1,
            selected=1,
            processed=1,
            confirmed=0,
            incorrect=1,
            unknown=0,
            stopped_reason="",
            filename=None,
            has_file=False,
        ))
        browser = MagicMock()
        parser = MagicMock()
        parser.parse = AsyncMock(return_value=SellerPageResult(
            SellerPageState.NOT_FOUND
        ))

        with (
            patch.object(
                LocalSellerService,
                "_connect_browser",
                new=AsyncMock(return_value=browser),
            ),
            patch(
                "megamarket.services.local_sellers.MegamarketSellerPage",
                return_value=parser,
            ),
            patch(
                "megamarket.services.local_sellers.Target.close",
                new=AsyncMock(),
            ),
        ):
            result = await LocalSellerService(remote).define_sellers(
                limit=4,
                file=None,
            )

        submitted = remote.observe.await_args.args[1]
        self.assertEqual(submitted.seller_id, "13635")
        self.assertIs(submitted.state, SellerObservationState.NOT_FOUND)
        remote.finish_job.assert_awaited_once_with("job-1", "")
        self.assertEqual(result.summary.incorrect, 1)


class SellerJobServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_different_page_seller_id_is_marked_incorrect(self):
        job = SellerJob(
            job_id="job-1",
            status="active",
            added=0,
            expires_at=datetime.now(UTC) + timedelta(minutes=10),
        )
        seller = Sellers(
            seller_id="13635",
            name="Магазин",
            link_to_seller="https://megamarket.ru/shop/magazin/",
            link_to_card="https://megamarket.ru/card_13635/",
            status=SellerStatus.UNCONFIRMED,
        )
        item = SellerJobItem(
            job_id="job-1",
            seller_id="13635",
            position=0,
            processed=False,
        )
        repository = MagicMock()
        repository.get_job = AsyncMock(return_value=job)
        repository.get_job_item = AsyncMock(return_value=item)
        repository.get_by_identity = AsyncMock(return_value=seller)
        repository.mark_incorrect = AsyncMock()
        repository.mark_job_item = AsyncMock()
        repository.commit = AsyncMock()
        repository.rollback = AsyncMock()

        observation = SellerObservation.model_validate({
            "seller_id": "13635",
            "state": "found",
            "info": {
                "seller_id": "99999",
                "name": "Другой магазин",
            },
        })
        result = await SellerJobService(repository).observe("job-1", observation)

        repository.mark_incorrect.assert_awaited_once_with("13635")
        repository.mark_job_item.assert_awaited_once_with(
            "job-1",
            "13635",
            "incorrect",
        )
        self.assertEqual(result.outcome, "incorrect")


if __name__ == "__main__":
    unittest.main()
