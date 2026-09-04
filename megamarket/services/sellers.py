from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

from sqlalchemy.exc import IntegrityError

from megamarket.config import settings
from megamarket.db.models import SellerJob, Sellers
from megamarket.domain import SellerObservationState, SellerStatus
from megamarket.repositories.sellers import SellerRepository
from megamarket.schemas.seller_jobs import (
    SellerCandidate,
    SellerJobFinishResponse,
    SellerJobStartResponse,
    SellerObservation,
    SellerObservationResponse,
)
from megamarket.schemas.sellers import SellerUpdate
from megamarket.slug import SlugifyCard
from megamarket.storage.report import ExcelCardsReport
from megamarket.utils import normalize_link, normalize_text


class SellerNotFoundError(LookupError):
    pass


class SellerConflictError(RuntimeError):
    pass


class SellerJobStateError(RuntimeError):
    pass


class SellerService:
    """Серверная бизнес-логика списка продавцов."""

    def __init__(self, repository: SellerRepository) -> None:
        self.repository = repository

    async def get_sellers(
            self,
            status: SellerStatus | None = None,
    ) -> list[Sellers]:
        return await self.repository.get_all(status)

    async def set_sellers(
            self,
            updates: list[SellerUpdate],
    ) -> list[Sellers]:
        sellers: list[Sellers] = []
        try:
            for update in updates:
                seller = await self.repository.get_by_identity(
                    seller_id=update.seller_id,
                    name=update.name,
                )
                if seller is None:
                    identity = update.seller_id or update.name
                    raise SellerNotFoundError(f"Продавец {identity!r} не найден")

                for field, value in update.changes().items():
                    setattr(seller, field, value)
                sellers.append(seller)

            await self.repository.flush()
            await self.repository.commit()
            return sellers
        except IntegrityError as error:
            await self.repository.rollback()
            raise SellerConflictError(
                "Изменения нарушают уникальность имени или ссылки продавца"
            ) from error
        except Exception:
            await self.repository.rollback()
            raise


class SellerJobService:
    """Серверная часть распределённой проверки продавцов."""

    JOB_TTL = timedelta(minutes=30)

    def __init__(self, repository: SellerRepository) -> None:
        self.repository = repository

    async def start(
            self,
            *,
            limit: int,
            input_path: Path | None = None,
            output_path: Path | None = None,
            filename: str | None = None,
    ) -> SellerJobStartResponse:
        report: ExcelCardsReport | None = None
        try:
            added = 0
            if input_path is not None:
                if output_path is None or filename is None:
                    raise ValueError("Не указаны параметры выходного Excel-файла")
                report = ExcelCardsReport(input_path)
                added = await self.repository.add_new(
                    self._sellers_from_report(report)
                )

            now = datetime.now(UTC)
            job = SellerJob(
                job_id=str(uuid4()),
                filename=filename,
                input_path=str(input_path) if input_path is not None else None,
                output_path=str(output_path) if output_path is not None else None,
                added=added,
                expires_at=now + self.JOB_TTL,
            )
            sellers = await self.repository.create_job(job, limit)
            await self.repository.commit()
            return SellerJobStartResponse(
                job_id=job.job_id,
                added=added,
                filename=filename,
                sellers=[
                    SellerCandidate.model_validate(seller, from_attributes=True)
                    for seller in sellers
                ],
            )
        except Exception:
            await self.repository.rollback()
            raise
        finally:
            if report is not None:
                report.close()

    async def observe(
            self,
            job_id: str,
            observation: SellerObservation,
    ) -> SellerObservationResponse:
        job = await self._active_job(job_id)
        item = await self.repository.get_job_item(job.job_id, observation.seller_id)
        if item is None:
            raise SellerNotFoundError(
                f"Продавец {observation.seller_id} не входит в задание"
            )
        seller = await self.repository.get_by_identity(
            seller_id=observation.seller_id
        )
        if seller is None:
            raise SellerNotFoundError(
                f"Продавец {observation.seller_id} не найден"
            )
        if item.processed:
            return SellerObservationResponse(
                seller_id=seller.seller_id,
                status=seller.status.value,
                outcome=item.outcome or "unknown",
            )

        try:
            outcome = "unknown"
            if observation.state is SellerObservationState.NOT_FOUND:
                await self.repository.mark_incorrect(seller.seller_id)
                outcome = "incorrect"
            elif observation.state is SellerObservationState.FOUND:
                info = observation.info
                if info is None:
                    raise ValueError("Нет данных найденного продавца")
                if info.seller_id != seller.seller_id:
                    await self.repository.mark_incorrect(seller.seller_id)
                    outcome = "incorrect"
                else:
                    canonical_link = (
                        f"{settings.base_url}/shop/{info.slug}/"
                        if info.slug
                        else seller.link_to_seller
                    )
                    await self.repository.confirm(
                        seller.seller_id,
                        info,
                        canonical_link,
                    )
                    outcome = "correct"

            await self.repository.mark_job_item(
                job.job_id,
                seller.seller_id,
                outcome,
            )
            await self.repository.commit()
            return SellerObservationResponse(
                seller_id=seller.seller_id,
                status=seller.status.value,
                outcome=outcome,
            )
        except IntegrityError as error:
            await self.repository.rollback()
            raise SellerConflictError(
                "Полученные данные конфликтуют с другим продавцом"
            ) from error
        except Exception:
            await self.repository.rollback()
            raise

    async def finish(
            self,
            job_id: str,
            *,
            stopped_reason: str = "",
    ) -> SellerJobFinishResponse:
        job = await self.repository.get_job(job_id)
        if job is None:
            raise SellerNotFoundError(f"Задание {job_id} не найдено")

        if job.status == "active":
            if job.input_path and job.output_path:
                report = ExcelCardsReport(Path(job.input_path))
                try:
                    await self._set_report_links(report)
                    report.save(
                        Path(job.output_path),
                        replace_seller_links=True,
                    )
                finally:
                    report.close()
            await self.repository.finish_job(
                job,
                stopped_reason=stopped_reason,
                finished_at=datetime.now(UTC),
            )
            await self.repository.commit()

        outcomes = await self.repository.get_job_outcomes(job.job_id)
        return SellerJobFinishResponse(
            job_id=job.job_id,
            added=job.added,
            selected=len(outcomes),
            processed=sum(outcome is not None for outcome in outcomes),
            confirmed=outcomes.count("correct"),
            incorrect=outcomes.count("incorrect"),
            unknown=outcomes.count("unknown"),
            stopped_reason=job.stopped_reason,
            filename=job.filename,
            has_file=bool(job.output_path and Path(job.output_path).is_file()),
        )

    async def get_file(self, job_id: str) -> tuple[Path, str]:
        job = await self.repository.get_job(job_id)
        if job is None:
            raise SellerNotFoundError(f"Задание {job_id} не найдено")
        if job.status != "finished":
            raise SellerJobStateError("Задание ещё не завершено")
        if not job.output_path or not job.filename:
            raise SellerNotFoundError("У задания нет Excel-файла")
        path = Path(job.output_path)
        if not path.is_file():
            raise SellerNotFoundError("Excel-файл задания не найден")
        return path, job.filename

    async def _active_job(self, job_id: str) -> SellerJob:
        job = await self.repository.get_job(job_id)
        if job is None:
            raise SellerNotFoundError(f"Задание {job_id} не найдено")
        if job.status != "active":
            raise SellerJobStateError("Задание уже завершено")
        if job.expires_at <= datetime.now(UTC):
            raise SellerJobStateError("Время выполнения задания истекло")
        return job

    @staticmethod
    def _sellers_from_report(report: ExcelCardsReport) -> list[Sellers]:
        return [
            Sellers(
                seller_id=normalize_link(card.card_link),
                name=normalize_text(card.seller),
                link_to_seller=SlugifyCard.link_for_seller(
                    normalize_text(card.seller)
                ),
                link_to_card=card.card_link,
                status=SellerStatus.UNCONFIRMED,
            )
            for card in report.cards
        ]

    async def _set_report_links(self, report: ExcelCardsReport) -> None:
        seller_ids = {normalize_link(card.card_link) for card in report.cards}
        sellers = await self.repository.get_by_ids(seller_ids)
        for card in report.cards:
            seller = sellers.get(normalize_link(card.card_link))
            card.seller_link = (
                seller.link_to_seller
                if seller is not None and seller.status is SellerStatus.CORRECT
                else ""
            )
