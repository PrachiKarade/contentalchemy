from src.integrations.text_provider_manager import TextProviderManager

text_provider_manager = TextProviderManager()
result = text_provider_manager.generate_text(
    query="Explain what an AI agent is in three sentences."
)

print(result)