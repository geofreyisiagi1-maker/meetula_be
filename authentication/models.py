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
    display_name = models.CharField(max_length=80, blank=True, default="")
    avatar_url = models.URLField(max_length=2048, blank=True, default="")
    bio = models.TextField(blank=True, default="")
    location = models.CharField(max_length=100, blank=True, default="")
    website = models.URLField(max_length=2048, blank=True, default="")
    ACTIVITY_VISIBILITY_CHOICES = [
        ("public", "Public"),
        ("hidden", "Hidden"),
    ]
    activity_visibility = models.CharField(
        max_length=10,
        choices=ACTIVITY_VISIBILITY_CHOICES,
        default="public",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                Lower("username"),
                name="authentication_profile_username_ci_unique",
            ),
        ]


class Follow(models.Model):
    follower = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="following_relationships",
    )
    following = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="follower_relationships",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["follower", "following"],
                name="authentication_unique_follow",
            ),
            models.CheckConstraint(
                condition=~models.Q(follower=models.F("following")),
                name="authentication_follow_not_self",
            ),
        ]
        indexes = [
            models.Index(
                fields=["following", "created_at"],
                name="auth_following_created_idx",
            ),
        ]
