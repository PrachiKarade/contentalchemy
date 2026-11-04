import time

from src.integrations.image_clients import generate_image


print("Starting Stability AI image test...")

start = time.perf_counter()

try:
    result = generate_image(
        prompt=(
            "A professional 3D illustration of an "
            "AI healthcare assistant working with a doctor, "
            "modern medical office, clean composition, "
            "soft lighting, high-quality digital artwork."
        ),
        conversation_id="stability_test",
        quality="standard",
        size="1024x1024",
    )

    print("\nImage generated successfully!")
    print("Image path:", result["image_path"])

except Exception as error:
    print("\nImage generation failed:")
    print(error)

finally:
    elapsed = time.perf_counter() - start
    print(f"\nTotal elapsed time: {elapsed:.2f} seconds")