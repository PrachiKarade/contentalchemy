
from src.repositories.profile_repository import (
    ensure_indexes,
    upsert_profile,
    get_profile,
    delete_profile,
)

USER_ID = "usr_local_001"
CONVERSATION_ID = "conv_profile_test_001"


def main():
    # 1. Ensure database indexes exist.
    ensure_indexes()
    print("Profile indexes ready.")

    # 2. Create or update the profile.
    profile_markdown = """
# User Content Profile

## Writing Style
Practical, clear, and educational.

## Target Audience
Software developers learning AI.

## Brand Voice
Professional and approachable.

## Preferred Platforms
- LinkedIn
- Blog

## Content Goals
- Educate developers
- Share practical examples
- Increase engagement

## Additional Preferences
- Language: English
- Include code examples: Yes
"""

    profile = upsert_profile(
        user_id=USER_ID,
        conversation_id=CONVERSATION_ID,
        profile_markdown=profile_markdown,
    )

    print("\nSaved profile:")
    print(profile)

    # 3. Retrieve the profile.
    saved_profile = get_profile(
        USER_ID,
        CONVERSATION_ID,
    )

    assert saved_profile is not None
    assert saved_profile["user_id"] == USER_ID
    assert saved_profile["conversation_id"] == CONVERSATION_ID
    assert "Software developers learning AI" in saved_profile["profile_markdown"]

    print("\nProfile retrieved successfully.")
    print(saved_profile["profile_markdown"])

    # 4. Update the profile.
    updated_markdown = """
# User Content Profile

## Writing Style
Concise, practical, and educational.

## Target Audience
AI engineers and software developers.

## Additional Preferences
- Language: English
- Include code examples: No
"""

    updated_profile = upsert_profile(
        user_id=USER_ID,
        conversation_id=CONVERSATION_ID,
        profile_markdown=updated_markdown,
    )

    assert updated_profile["profile_markdown"] == updated_markdown

    print("\nProfile updated successfully.")

    # 5. Verify the updated profile.
    final_profile = get_profile(
        USER_ID,
        CONVERSATION_ID,
    )

    assert final_profile is not None
    assert "Include code examples: No" in final_profile["profile_markdown"]

    print("\nAll profile repository checks passed.")

    # 6. Optional cleanup.
    # Uncomment to delete the test profile.
    # delete_profile(USER_ID, CONVERSATION_ID)


if __name__ == "__main__":
    main()
