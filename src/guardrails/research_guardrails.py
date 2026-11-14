
from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator


class ResearchFinding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    claim: str = Field(min_length=3, max_length=1000)
    explanation: str = Field(max_length=3000)
    source_urls: list[HttpUrl] = Field(min_length=1, max_length=10)

    @field_validator("claim", "explanation")
    @classmethod
    def strip_text(cls, value: str) -> str:
        return value.strip()


class ResearchSource(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=500)
    url: HttpUrl
    snippet: str = Field(max_length=3000)

    @field_validator("title", "snippet")
    @classmethod
    def strip_text(cls, value: str) -> str:
        return value.strip()


class ResearchOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    topic: str = Field(min_length=2, max_length=300)
    findings: list[ResearchFinding] = Field(min_length=1, max_length=30)
    research_summary: str = Field(min_length=10, max_length=5000)
    sources: list[ResearchSource] = Field(min_length=1, max_length=20)

    @field_validator("topic", "research_summary")
    @classmethod
    def strip_and_validate_text(cls, value: str) -> str:
        value = value.strip()

        if not value:
            raise ValueError("This field cannot be empty or whitespace.")
        return value


def validate_research_output(data: dict) -> dict:
    """Validate and normalize structured research output."""
    validated = ResearchOutput.model_validate(data)
    return validated.model_dump(mode="json")
