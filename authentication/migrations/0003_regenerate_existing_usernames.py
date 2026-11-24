import secrets

from django.conf import settings
from django.db import migrations


AFRICAN_NAMES = (
    "adaeze", "amara", "ayo", "imani", "kato", "kofi",
    "lerato", "mosi", "nia", "sade", "thabo", "zuri",
)
AFRICAN_WORDS = (
    "acacia", "baobab", "kijiji", "mango", "nile", "savannah", "ubuntu",
)


def regenerate_usernames(apps, schema_editor):
    User = apps.get_model(*settings.AUTH_USER_MODEL.split("."))
    UserProfile = apps.get_model("authentication", "UserProfile")
    database = schema_editor.connection.alias

    for user in User.objects.using(database).all().iterator():
        profile = UserProfile.objects.using(database).get(user_id=user.pk)
        for _ in range(100):
            username = (
                f"{secrets.choice(AFRICAN_NAMES)}_"
                f"{secrets.choice(AFRICAN_WORDS)}_"
                f"{secrets.randbelow(9000) + 1000}"
            )
            if (
                not UserProfile.objects.using(database)
                .filter(username__iexact=username)
                .exclude(user_id=user.pk)
                .exists()
                and not User.objects.using(database)
                .filter(username__iexact=username)
                .exclude(pk=user.pk)
                .exists()
            ):
                break
        else:
            raise RuntimeError("Could not generate an available username.")

        User.objects.using(database).filter(pk=user.pk).update(username=username)
        UserProfile.objects.using(database).filter(pk=profile.pk).update(
            username=username
        )


class Migration(migrations.Migration):
    dependencies = [
        ("authentication", "0002_userprofile"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.RunPython(regenerate_usernames, migrations.RunPython.noop),
    ]
