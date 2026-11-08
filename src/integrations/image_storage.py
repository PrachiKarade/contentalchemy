
import os
import base64

from azure.storage.blob import BlobServiceClient
from azure.core.credentials import AzureNamedKeyCredential
from dotenv import load_dotenv
from pathlib import Path
from uuid import uuid4

from src.core.logger import setup_logger
load_dotenv()
key = os.getenv("AZURITE_ACCOUNT_KEY", "")

print("Key loaded:", bool(key))
print("Key length:", len(key))
print("Base64 valid:", end=" ")

try:
    base64.b64decode(key, validate=True)
    print(True)
except Exception as exc:
    print(False, "-", exc)


class AzuriteImageStorage:

    def __init__(self): # this is constructor method that initializes the AzuriteImageStorage class. It sets up the connection to the Azurite blob storage service using the provided account name, account key, and endpoint. It also retrieves the container name from environment variables and creates a BlobServiceClient instance to interact with the blob storage service. Finally, it gets a reference to the specified container for further operations.
         
        account_name = os.getenv( "AZURITE_ACCOUNT_NAME", "devstoreaccount1" )
        account_key = os.getenv("AZURITE_ACCOUNT_KEY")
        endpoint = os.getenv(
            "AZURITE_BLOB_ENDPOINT",
            "http://127.0.0.1:10000/devstoreaccount1"
        )

        self.container_name = os.getenv( "AZURITE_CONTAINER_NAME", "contentalchemy-images")

        if not account_key:
            raise ValueError("AZURITE_ACCOUNT_KEY is missing.")

        credential = AzureNamedKeyCredential( account_name, account_key  )

        self.blob_service = BlobServiceClient(
            account_url=endpoint,
            credential=credential,
            api_version="2026-06-06"
        )

        self.container = self.blob_service.get_container_client( self.container_name)

    # ---------------------------------------------------------
    # Upload Image Method
    # ---------------------------------------------------------
    def upload_image(
        self,
        image_bytes: bytes,
        blob_name: str
    ) -> str:

        blob = self.container.get_blob_client(blob_name)

        blob.upload_blob(
            image_bytes,
            overwrite=True,
            content_type="image/png"
        )
        return blob.url





#---------------------------------------------------------
# Local Image Storage Class
#---------------------------------------------------------
class LocalImageStorage:

    def __init__(self):
        self.image_directory = (
            Path(__file__).resolve().parents[2]
            / "generated"
            / "images"
        )

    def upload_image(
        self,
        image_bytes: bytes,
        blob_name: str
    ) -> str:

        image_path = self.image_directory / blob_name
        image_path.parent.mkdir(
            parents=True,
            exist_ok=True
        )

        image_path.write_bytes(image_bytes)

        logger.info(
            "Image saved locally: %s",
            image_path
        )

        return str(image_path)


class ImageStorageManager:

    def __init__(self):
        self.azurite = AzuriteImageStorage()
        self.local = LocalImageStorage()

    def upload_image(
        self,
        image_bytes: bytes,
        blob_name: str
    ) -> dict:

        try:
            image_url = self.azurite.upload_image(
                image_bytes,
                blob_name
            )

            return {
                "storage_provider": "azurite",
                "image_path": blob_name,
                "image_url": image_url,
            }

        except Exception as error:
            logger.exception(
                "Azurite upload failed. Using local storage."
            )

            local_path = self.local.upload_image(
                image_bytes,
                blob_name
            )

            return {
                "storage_provider": "local",
                "image_path": local_path,
                "image_url": "",
            }
