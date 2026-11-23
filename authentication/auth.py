from django.conf import settings
from django.contrib.auth.models import User
from rest_framework import authentication


class DevelopmentUserAuthentication(authentication.BaseAuthentication):
    """Opt-in identity for requests coming from a local development frontend."""

    def authenticate(self, request):
        if (
            not settings.DEBUG
            or not getattr(settings, "ENABLE_DEV_ANONYMOUS_USER", False)
            or request.headers.get("X-Development-User") != "enabled"
            or request.META.get("REMOTE_ADDR") not in {"127.0.0.1", "::1"}
        ):
            return None

        user, _ = User.objects.get_or_create(
            username="frontend-dev",
            defaults={
                "first_name": "Frontend",
                "last_name": "Developer",
            },
        )
        return (user, None)
