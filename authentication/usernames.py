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


def generate_unique_username():
    User = get_user_model()
    for _ in range(20):
        username = (
            f"{secrets.choice(AFRICAN_NAMES)}_"
            f"{secrets.choice(AFRICAN_WORDS)}_"
            f"{secrets.randbelow(9000) + 1000}"
        )
        if (
            not UserProfile.objects.filter(username__iexact=username).exists()
            and not User.objects.filter(username__iexact=username).exists()
        ):
            return username
    raise RuntimeError("Could not generate an available username.")
