
from src.repositories.profile_repository import (
    ensure_indexes,
    upsert_profile,
    get_profile,
    update_profile_preferences,
)

USER_ID = "usr_local_001"


def main():
    ensure_indexes()
    print("Profile indexes ready.")

    # Create or update the user's content preferences.
    profile = upsert_profile(
        user_id=USER_ID,
        writing_style="Practical, clear, and educational",
        target_audience="Software developers learning AI",
        brand_voice="Professional and approachable",
        preferred_platforms=["LinkedIn", "Blog"],
        content_goals=[
            "Educate developers",
            "Share practical examples",
            "Increase engagement",
        ],
        additional_preferences={
            "preferred_language": "English",
            "include_code_examples": True,
        },
    )

    print("\nSaved profile:")
    print(profile)

    # Retrieve the saved profile.
    saved_profile = get_profile(USER_ID)

    if saved_profile:
        print("Writing style:", saved_profile["writing_style"])
        print("Target audience:", saved_profile["target_audience"])

    # Update only additional preferences.
    updated = update_profile_preferences(
        USER_ID,
        {
            "include_code_examples": False,
            "preferred_language": "English",
        },
    )

    print("\nPreferences updated:", updated)

    final_profile = get_profile(USER_ID)
    print(
        "Include code examples:",
        final_profile["additional_preferences"]["include_code_examples"],
    )


if __name__ == "__main__":
    main()
