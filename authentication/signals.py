from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import UserProfile
from .usernames import generate_unique_username, is_generated_username


@receiver(post_save, sender=get_user_model())
def create_user_profile(sender, instance, created, **kwargs):
    if not created:
        return

    username = instance.username.lower()
    if (
        not is_generated_username(username)
        or UserProfile.objects.filter(username__iexact=username).exists()
        or sender.objects.filter(username__iexact=username)
        .exclude(pk=instance.pk)
        .exists()
    ):
        username = generate_unique_username()

    for _ in range(20):
        try:
            with transaction.atomic():
                if instance.username != username:
                    instance.username = username
                    instance.save(update_fields=["username"])
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
