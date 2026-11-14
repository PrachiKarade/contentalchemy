
from pydantic import BaseModel, ConfigDict, Field, field_validator
from typing import Literal


ContentIntent = Literal[
    "research",
    "blog",
    "linkedin",
    "image",
    "strategy",
    "multi",
]

ContentDeliverable = Literal[
    "research",
    "blog",
    "linkedin",
    "image",
    "strategy",
]


class UserRequestInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_request: str = Field(min_length=3, max_length=5000)

    @field_validator("user_request")
    @classmethod
    def validate_request(cls, value: str) -> str:
        value = value.strip()

        if not value:
            raise ValueError("User request cannot be empty.")

        return value


class QueryAnalysisOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    intent: ContentIntent
    topic: str = Field(min_length=2, max_length=300)
    target_audience: str = Field(max_length=300)
    tone: str = Field(max_length=100)
    keywords: list[str] = Field(max_length=20)
    objective: str = Field(max_length=500)

    requested_agents: list[ContentDeliverable] = Field(
        min_length=1,
        max_length=5,
    )

    @field_validator("topic", "target_audience", "tone", "objective")
    @classmethod
    def strip_text(cls, value: str) -> str:
        return value.strip()

    @field_validator("keywords")
    @classmethod
    def validate_keywords(cls, values: list[str]) -> list[str]:
        cleaned = [item.strip() for item in values]

        if any(not item or len(item) > 100 for item in cleaned):
            raise ValueError("Each keyword must contain 1–100 characters.")

        return list(dict.fromkeys(cleaned))

    @field_validator("requested_agents")
    @classmethod
    def validate_requested_agents(
        cls,
        values: list[ContentDeliverable],
    ) -> list[ContentDeliverable]:
        if len(values) != len(set(values)):
            raise ValueError("Requested deliverables must be unique.")

        return values
