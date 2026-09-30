from enum import StrEnum

from pydantic import BaseModel, Field, model_validator

ID_PATTERN = r"^[\w-]{1,64}$"


class EventType(StrEnum):
    VIEW = "view"
    CLICK = "click"
    RATE = "rate"


class EventIn(BaseModel):
    user_id: str = Field(pattern=ID_PATTERN)
    item_id: str = Field(pattern=ID_PATTERN)
    type: EventType
    rating: int | None = Field(default=None, ge=1, le=5)

    @model_validator(mode="after")
    def check_rating(self) -> "EventIn":
        if (self.type is EventType.RATE) != (self.rating is not None):
            raise ValueError("rating is required for 'rate' events and only for them")
        return self
