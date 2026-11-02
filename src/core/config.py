
import os
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI

load_dotenv()

OPENAI_MODEL       = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
OPENAI_IMAGE_MODEL = os.getenv("OPENAI_IMAGE_MODEL", "")
SERPAPI_KEY        = os.getenv("SERPAPI_KEY")
OPENAI_API_KEY     = os.getenv("OPENAI_API_KEY")


def validate_openai_config() -> None:
    if not os.getenv("OPENAI_API_KEY"):
        raise ValueError( "OPENAI_API_KEY is missing from your .env file." )


def validate_research_config() -> None:
    if not SERPAPI_KEY:
        raise ValueError( "SERPAPI_KEY is missing from your .env file." )

