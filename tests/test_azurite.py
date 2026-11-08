from src.integrations.image_storage import AzuriteImageStorage

storage = AzuriteImageStorage()

if not storage.container.exists():
    storage.container.create_container()
    print("Container created.")
else:
    print("Container already exists.")

print("Azurite connection successful!")

print("Azurite connection successful!")
print("Container:", storage.container_name)

blob = storage.container.get_blob_client("test/hello.txt")

blob.upload_blob(
    b"Hello from ContentAlchemy!",
    overwrite=True
)

print("Upload successful!")