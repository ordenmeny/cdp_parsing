from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from megamarket.db.models import SellerJob, SellerJobItem, Sellers
from megamarket.domain import SellerInfo, SellerStatus


class SellerRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add_new(self, candidates: Sequence[Sellers]) -> int:
        """Добавить записи, не конфликтующие с существующими уникальными полями."""
        unique: list[Sellers] = []
        seller_ids: set[str] = set()
        names: set[str] = set()
        links: set[str] = set()

        for seller in candidates:
            if (
                    seller.seller_id in seller_ids
                    or seller.name in names
                    or seller.link_to_seller in links
            ):
                continue
            unique.append(seller)
            seller_ids.add(seller.seller_id)
            names.add(seller.name)
            links.add(seller.link_to_seller)

        if not unique:
            return 0

        statement = select(Sellers).where(
            or_(
                Sellers.seller_id.in_(seller_ids),
                Sellers.name.in_(names),
                Sellers.link_to_seller.in_(links),
            )
        )
        existing = list((await self.session.scalars(statement)).all())
        existing_ids = {seller.seller_id for seller in existing}
        existing_names = {seller.name for seller in existing}
        existing_links = {seller.link_to_seller for seller in existing}

        new_sellers = [
            seller
            for seller in unique
            if seller.seller_id not in existing_ids
               and seller.name not in existing_names
               and seller.link_to_seller not in existing_links
        ]
        self.session.add_all(new_sellers)
        await self.session.flush()
        return len(new_sellers)

    async def get_unconfirmed(self, limit: int) -> list[Sellers]:
        statement = (
            select(Sellers)
            .where(Sellers.status == SellerStatus.UNCONFIRMED)
            .order_by(Sellers.seller_id)
            .limit(limit)
        )
        return list((await self.session.scalars(statement)).all())

    async def create_job(
            self,
            job: SellerJob,
            limit: int,
    ) -> list[Sellers]:
        """Создать задание и зарезервировать ещё не занятых продавцов."""
        active_reservation = exists(
            select(SellerJobItem.job_id)
            .join(SellerJob, SellerJob.job_id == SellerJobItem.job_id)
            .where(
                SellerJobItem.seller_id == Sellers.seller_id,
                SellerJob.status == "active",
                SellerJob.expires_at > func.now(),
            )
        )
        statement = (
            select(Sellers)
            .where(
                Sellers.status == SellerStatus.UNCONFIRMED,
                ~active_reservation,
            )
            .order_by(Sellers.seller_id)
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        sellers = list((await self.session.scalars(statement)).all())
        self.session.add(job)
        await self.session.flush()
        self.session.add_all([
            SellerJobItem(
                job_id=job.job_id,
                seller_id=seller.seller_id,
                position=position,
            )
            for position, seller in enumerate(sellers)
        ])
        await self.session.flush()
        return sellers

    async def get_all(
            self,
            status: SellerStatus | None = None,
    ) -> list[Sellers]:
        statement = select(Sellers).order_by(Sellers.seller_id)
        if status is not None:
            statement = statement.where(Sellers.status == status)
        return list((await self.session.scalars(statement)).all())

    async def get_by_identity(
            self,
            *,
            seller_id: str | None = None,
            name: str | None = None,
    ) -> Sellers | None:
        if seller_id is not None:
            return await self.session.get(Sellers, seller_id)
        if name is not None:
            statement = select(Sellers).where(Sellers.name == name)
            return await self.session.scalar(statement)
        raise ValueError("Не указан идентификатор продавца")

    async def get_by_ids(self, seller_ids: set[str]) -> dict[str, Sellers]:
        if not seller_ids:
            return {}
        statement = select(Sellers).where(Sellers.seller_id.in_(seller_ids))
        sellers = (await self.session.scalars(statement)).all()
        return {seller.seller_id: seller for seller in sellers}

    async def get_job(self, job_id: str) -> SellerJob | None:
        return await self.session.get(SellerJob, job_id)

    async def get_job_item(
            self,
            job_id: str,
            seller_id: str,
    ) -> SellerJobItem | None:
        return await self.session.get(SellerJobItem, (job_id, seller_id))

    async def mark_job_item(
            self,
            job_id: str,
            seller_id: str,
            outcome: str,
    ) -> None:
        item = await self.get_job_item(job_id, seller_id)
        if item is None:
            raise LookupError(
                f"Продавец {seller_id} не входит в задание {job_id}"
            )
        item.processed = True
        item.outcome = outcome
        await self.session.flush()

    async def get_job_outcomes(self, job_id: str) -> list[str | None]:
        statement = (
            select(SellerJobItem.outcome)
            .where(SellerJobItem.job_id == job_id)
            .order_by(SellerJobItem.position)
        )
        return list((await self.session.scalars(statement)).all())

    async def finish_job(
            self,
            job: SellerJob,
            *,
            stopped_reason: str,
            finished_at: datetime,
    ) -> None:
        job.status = "finished"
        job.stopped_reason = stopped_reason
        job.finished_at = finished_at
        await self.session.flush()

    async def mark_incorrect(self, seller_id: str) -> None:
        seller = await self._get_required(seller_id)
        seller.status = SellerStatus.INCORRECT
        await self.session.flush()

    async def confirm(
            self,
            seller_id: str,
            info: SellerInfo,
            link_to_seller: str,
    ) -> None:
        seller = await self._get_required(seller_id)
        seller.name = info.name or seller.name
        seller.link_to_seller = link_to_seller
        seller.email = info.email
        seller.ogrn = info.ogrn
        seller.official_name = info.official_name
        seller.inn = info.inn
        seller.phone = info.phone
        seller.rating = info.rating
        seller.status = SellerStatus.CORRECT
        await self.session.flush()

    async def commit(self) -> None:
        await self.session.commit()

    async def flush(self) -> None:
        await self.session.flush()

    async def rollback(self) -> None:
        await self.session.rollback()

    async def _get_required(self, seller_id: str) -> Sellers:
        seller = await self.session.get(Sellers, seller_id)
        if seller is None:
            raise LookupError(f"Продавец {seller_id} не найден")
        return seller
