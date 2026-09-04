from pydantic import BaseModel, ConfigDict, Field


class ParseRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    command: str = Field(
        min_length=1,
        examples=["scrolling||makita"],
        description="Команда формата scrolling||<поисковый запрос>",
    )
