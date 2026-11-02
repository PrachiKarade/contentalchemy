
import os
from functools import lru_cache

from dotenv import load_dotenv
from pymongo import MongoClient
from pymongo.database import Database

load_dotenv()


@lru_cache(maxsize=1)
def get_mongo_client() -> MongoClient:
    uri = os.getenv("MONGODB_URI")

    if not uri:
        raise ValueError("MONGODB_URI is missing from .env")

    return MongoClient(
        uri,
        serverSelectionTimeoutMS = 5000,
    )


def get_database() -> Database:
    database_name = os.getenv("MONGODB_DATABASE", "contentalchemy_db", )

    return get_mongo_client()[database_name]


def check_mongodb_connection() -> bool:
    get_mongo_client().admin.command("ping")
    return True
