from pathlib import Path
from typing import Literal, TypedDict, cast


DB_Settings = {
    "file": "db_sellers.txt",
}

type SellerStatus = Literal["correct", "incorrect", "unconfirmed"]


class SellerData(TypedDict):
    link: str
    status: SellerStatus


class SellersManager:
    """Управление локальной базой ссылок продавцов.

    Каждая непустая строка файла имеет формат
    ``название||предположительная ссылка||статус``.
    """

    STATUSES = frozenset({"correct", "incorrect", "unconfirmed"})
    FINAL_STATUSES = frozenset({"correct", "incorrect"})

    def __init__(self, file: str | Path | None = None) -> None:
        configured = Path(file or DB_Settings["file"]).expanduser()
        if not configured.is_absolute():
            configured = Path(__file__).resolve().parent / configured
        self.file = configured.resolve()

    @staticmethod
    def _clean_field(value: str, field_name: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError(f"Поле «{field_name}» не должно быть пустым.")
        if "||" in value or "\n" in value or "\r" in value:
            raise ValueError(
                f"Поле «{field_name}» содержит недопустимый разделитель."
            )
        return value

    @classmethod
    def _validate_status(
            cls,
            status: str,
            *,
            allow_unconfirmed: bool,
    ) -> SellerStatus:
        status = status.strip().casefold()
        allowed = cls.STATUSES if allow_unconfirmed else cls.FINAL_STATUSES
        if status not in allowed:
            expected = ", ".join(sorted(allowed))
            raise ValueError(f"Недопустимый статус. Ожидается: {expected}.")
        return cast(SellerStatus, status)

    def serialize(self) -> dict[str, SellerData]:
        """Прочитать файл базы и вернуть словарь продавцов."""
        if not self.file.exists():
            return {}
        if not self.file.is_file():
            raise ValueError(f"Путь базы не является файлом: {self.file}")

        sellers: dict[str, SellerData] = {}
        for line_number, raw_line in enumerate(
                self.file.read_text(encoding="utf-8-sig").splitlines(),
                start=1,
        ):
            if not raw_line.strip():
                continue

            parts = [part.strip() for part in raw_line.split("||")]
            if len(parts) != 3:
                raise ValueError(
                    f"Некорректная строка {line_number} в {self.file.name}: "
                    "ожидается три поля, разделённые ||."
                )

            name = self._clean_field(parts[0], "Название продавца")
            link = self._clean_field(parts[1], "Ссылка")
            status = self._validate_status(parts[2], allow_unconfirmed=True)
            if name in sellers:
                raise ValueError(
                    f"Продавец «{name}» повторяется в строке {line_number}."
                )
            sellers[name] = {"link": link, "status": status}
        return sellers

    def _save(self, sellers: dict[str, SellerData]) -> None:
        self.file.parent.mkdir(parents=True, exist_ok=True)
        content = "".join(
            f"{name}||{data['link']}||{data['status']}\n"
            for name, data in sellers.items()
        )
        self.file.write_text(content, encoding="utf-8")

    def add(
            self,
            name: str,
            link: str,
            status: str = "unconfirmed",
    ) -> None:
        """Добавить нового продавца отдельной строкой в базу."""
        name = self._clean_field(name, "Название продавца")
        link = self._clean_field(link, "Ссылка")
        validated_status = self._validate_status(
            status,
            allow_unconfirmed=True,
        )
        sellers = self.serialize()
        if name in sellers:
            raise ValueError(f"Продавец «{name}» уже есть в базе.")
        sellers[name] = {"link": link, "status": validated_status}
        self._save(sellers)

    def change_status(self, name: str, status: str) -> None:
        """Установить продавцу подтверждённый статус ссылки."""
        name = self._clean_field(name, "Название продавца")
        validated_status = self._validate_status(
            status,
            allow_unconfirmed=False,
        )
        sellers = self.serialize()
        if name not in sellers:
            raise KeyError(f"Продавец «{name}» не найден в базе.")
        sellers[name]["status"] = validated_status
        self._save(sellers)

    def change_link(self, name: str, link: str) -> None:
        """Заменить ссылку указанного продавца, сохранив текущий статус."""
        name = self._clean_field(name, "Название продавца")
        link = self._clean_field(link, "Ссылка")
        sellers = self.serialize()
        if name not in sellers:
            raise KeyError(f"Продавец «{name}» не найден в базе.")
        sellers[name]["link"] = link
        self._save(sellers)

    async def determine_status(self, name: str) -> int:
        """Определить HTTP-статус страницы продавца"""
        raise NotImplementedError("Определение статуса страницы ещё не реализовано.")