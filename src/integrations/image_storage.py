
import os
from pathlib import Path

from azure.storage.blob import BlobServiceClient
from azure.core.credentials import AzureNamedKeyCredential
from dotenv import load_dotenv

from src.core.logger import setup_logger

load_dotenv()

logger = setup_logger("ImageStorage")


# ---------------------------------------------------------
# Azurite Image Storage
# ---------------------------------------------------------

class AzuriteImageStorage:

    def __init__(self):
        account_name = os.getenv(
            "AZURITE_ACCOUNT_NAME",
            "devstoreaccount1"
        )

        account_key = os.getenv("AZURITE_ACCOUNT_KEY")

        endpoint = os.getenv(
            "AZURITE_BLOB_ENDPOINT",
            "http://127.0.0.1:10000/devstoreaccount1"
        )

        self.container_name = os.getenv(
            "AZURITE_CONTAINER_NAME",
            "contentalchemy-images"
        )

        if not account_key:
            raise ValueError("AZURITE_ACCOUNT_KEY is missing.")

        credential = AzureNamedKeyCredential(
            account_name,
            account_key
        )

        self.blob_service = BlobServiceClient(
            account_url=endpoint,
            credential=credential
        )

        self.container = self.blob_service.get_container_client(
            self.container_name
        )

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


# ---------------------------------------------------------
# Local Image Storage
# ---------------------------------------------------------

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


# ---------------------------------------------------------
# Image Storage Manager
# ---------------------------------------------------------
class ImageStorageManager:

    def __init__(self):
        self._azurite = None
        self.local = LocalImageStorage()

    def upload_image(
        self,
        image_bytes: bytes,
        blob_name: str
    ) -> dict:

        # Always save a local copy for Streamlit UI.
        local_path = self.local.upload_image(
            image_bytes,
            blob_name
        )

        try:
            if self._azurite is None:
                self._azurite = AzuriteImageStorage()

            image_url = self._azurite.upload_image(
                image_bytes,
                blob_name
            )

            logger.info("Image uploaded to Azurite successfully.")

            return {
                "storage_provider": "azurite",
                "image_path": local_path,
                "image_url": image_url,
            }

        except Exception:
            logger.exception(
                "Azurite upload failed. Using local storage."
            )

            return {
                "storage_provider": "local",
                "image_path": local_path,
                "image_url": "",
            }
