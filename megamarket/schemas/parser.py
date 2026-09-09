from pydantic import (
    AliasChoices,
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
)


# Каждый запрос — это отдельный проход по выдаче, и идут они последовательно.
# Предел нужен, чтобы одним нажатием нельзя было занять браузер на сутки.
MAX_COMMANDS = 20


class ParseRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    commands: list[str] = Field(
        # Прежний контракт с единственной командой остаётся рабочим: у
        # пользователя интерфейс приходит с сервера, а код — из git, и одно
        # обновление может опередить другое.
        validation_alias=AliasChoices("commands", "command"),
        min_length=1,
        max_length=MAX_COMMANDS,
        examples=[["scrolling||makita", "scrolling||iphone 17"]],
        description=(
            "Команды формата scrolling||<поисковый запрос>. Результат всех "
            "запросов попадает в один файл. Одна строка вместо списка тоже "
            "принимается."
        ),
    )

    @field_validator("commands", mode="before")
    @classmethod
    def _as_list(cls, value: object) -> object:
        return [value] if isinstance(value, str) else value
