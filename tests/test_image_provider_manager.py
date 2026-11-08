from src.integrations.image_provider_manager import ( ImageProviderManager,)

manager = ImageProviderManager()

result = manager.generate_image(
    prompt="A professional illustration of a RAG architecture",
    size="1024x1024",
)

print("Provider:", result["provider"])
print("Image bytes:", len(result["image_bytes"]))