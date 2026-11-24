import secrets

from django.contrib.auth import get_user_model

from .models import UserProfile


AFRICAN_NAMES = (
    "adaeze",
    "amara",
    "ayo",
    "imani",
    "kato",
    "kofi",
    "lerato",
    "mosi",
    "nia",
    "sade",
    "thabo",
    "zuri",
)

AFRICAN_WORDS = (
    "acacia",
    "baobab",
    "kijiji",
    "mango",
    "nile",
    "savannah",
    "ubuntu",
)


def is_generated_username(username):
    parts = username.lower().split("_")
    if len(parts) not in {2, 3}:
        return False
    if parts[0] not in AFRICAN_NAMES or parts[1] not in AFRICAN_WORDS:
        return False
    return len(parts) == 2 or (parts[2].isdigit() and len(parts[2]) <= 13)


def generate_unique_username():
    User = get_user_model()

    def is_taken(username):
        return (
            UserProfile.objects.filter(username__iexact=username).exists()
            or User.objects.filter(username__iexact=username).exists()
        )

    for _ in range(20):
        base = f"{secrets.choice(AFRICAN_NAMES)}_{secrets.choice(AFRICAN_WORDS)}"
        if not is_taken(base):
            return base

        for suffix in range(2, 102):
            username = f"{base}_{suffix}"
            if not is_taken(username):
                return username

    raise RuntimeError("Could not generate an available username.")
