import re

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import UserProfile
from .usernames import generate_unique_username


@receiver(post_save, sender=get_user_model())
def create_user_profile(sender, instance, created, **kwargs):
    if not created:
        return

    username = instance.username.lower()
    if (
        re.fullmatch(r"[a-z0-9_]{3,30}", username) is None
        or UserProfile.objects.filter(username__iexact=username).exists()
    ):
        username = generate_unique_username()

    for _ in range(20):
        try:
            with transaction.atomic():
                UserProfile.objects.create(
                    user=instance,
                    username=username,
                )
            return
        except IntegrityError:
            if UserProfile.objects.filter(user=instance).exists():
                return
            username = generate_unique_username()
    raise RuntimeError("Could not create a unique profile username.")
