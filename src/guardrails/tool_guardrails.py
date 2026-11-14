
from pydantic import BaseModel, ConfigDict, Field, field_validator


class ResearchToolInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    topic: str = Field(min_length=2, max_length=300)
    target_audience: str = Field(default="", max_length=300)

    @field_validator("topic", "target_audience")
    @classmethod
    def strip_text(cls, value: str) -> str:
        return value.strip()

    @field_validator("topic")
    @classmethod
    def validate_topic(cls, value: str) -> str:
        if not value:
            raise ValueError("Topic cannot be empty.")
        return value


class InternetSearchToolInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    topic: str = Field(min_length=2, max_length=300)
    primary_keyword: str = Field(default="", max_length=100)

    @field_validator("topic", "primary_keyword")
    @classmethod
    def strip_text(cls, value: str) -> str:
        return value.strip()

    @field_validator("topic")
    @classmethod
    def validate_topic(cls, value: str) -> str:
        if not value:
            raise ValueError("Topic cannot be empty.")
        return value
