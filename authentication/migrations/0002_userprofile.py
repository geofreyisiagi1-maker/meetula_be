from django.conf import settings
from django.db import migrations, models
from django.db.models.functions.text import Lower
import django.db.models.deletion


def create_existing_profiles(apps, schema_editor):
    User = apps.get_model(*settings.AUTH_USER_MODEL.split("."))
    UserProfile = apps.get_model("authentication", "UserProfile")
    UserProfile.objects.bulk_create(
        [
            UserProfile(user_id=user.pk, username=f"member_{user.pk}")
            for user in User.objects.only("pk").iterator()
        ]
    )


class Migration(migrations.Migration):
    dependencies = [
        ("authentication", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="UserProfile",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("username", models.CharField(max_length=30)),
                (
                    "user",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="profile",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "constraints": [
                    models.UniqueConstraint(
                        Lower("username"),
                        name="authentication_profile_username_ci_unique",
                    ),
                ],
            },
        ),
        migrations.RunPython(create_existing_profiles, migrations.RunPython.noop),
    ]
