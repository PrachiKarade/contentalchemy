import os

from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv()

uri = os.getenv("MONGODB_URI")
database_name = os.getenv("MONGODB_DATABASE", "contentalchemy_db")

if not uri:
    raise ValueError("MONGODB_URI is missing from .env")

client = MongoClient(uri, serverSelectionTimeoutMS=5000)

try:
    client.admin.command("ping")
    print("MongoDB connection successful!")

    db = client[database_name]
    print(f"Database configured: {db.name}")
    print("Collections:", db.list_collection_names())
except Exception as exc:
    print(f"MongoDB connection failed: {exc}")
finally:
    client.close()