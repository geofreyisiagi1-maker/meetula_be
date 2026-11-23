from django.conf import settings
from django.db import models
from django.db.models.functions import Lower


class OAuthLoginCode(models.Model):
    code_hash = models.CharField(max_length=64, unique=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="oauth_login_codes",
    )
    expires_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)
    used_at = models.DateTimeField(blank=True, null=True)


class UserProfile(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="profile",
    )
    username = models.CharField(max_length=30)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                Lower("username"),
                name="authentication_profile_username_ci_unique",
            ),
        ]
