
from src.repositories.user_repository import (
    create_user,
    authenticate_user,
    get_user_by_email,
)

# Test registration
email = "testuser@example.com"

existing_user = get_user_by_email(email)

if existing_user:
    print("Test user already exists. Skipping registration.")
else:
    user = create_user(
        username="Test User",
        email=email,
        password="TestPassword123!",
    )
    print("Registration successful:", user)

# Test login
authenticated_user = authenticate_user(
    email=email,
    password="TestPassword123!",
)

if authenticated_user:
    print("Login successful:", authenticated_user["username"])
else:
    print("Login failed")

# Test incorrect password
invalid_user = authenticate_user(
    email=email,
    password="WrongPassword123!",
)

print("Invalid password rejected:", invalid_user is None)
