from unittest.mock import Mock, patch

from django.contrib.auth.models import User
from django.test import RequestFactory, SimpleTestCase, TestCase, override_settings
from django.urls import reverse
from rest_framework import status
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.test import APIClient

from .auth import DevelopmentUserAuthentication


class VerifyTokenTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.url = reverse("verify-token")

    def test_valid_authenticated_user_returns_clerk_id_from_username(self):
        user = User.objects.create_user(username="user_clerk_123")
        self.client.force_authenticate(user=user)

        response = self.client.post(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            response.data,
            {"valid": True, "clerk_id": "user_clerk_123"},
        )

    def test_missing_token_returns_invalid(self):
        response = self.client.post(self.url)

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(response.data, {"valid": False})

    @patch(
        "authentication.auth.ClerkAuthentication.authenticate",
        side_effect=AuthenticationFailed("Invalid token"),
    )
    def test_invalid_token_returns_invalid(self, _authenticate):
        response = self.client.post(
            self.url,
            HTTP_AUTHORIZATION="******",
        )

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(response.data, {"valid": False})


class DevelopmentUserAuthenticationTests(SimpleTestCase):
    @override_settings(DEBUG=True, ENABLE_DEV_ANONYMOUS_USER=True)
    @patch("authentication.auth.User.objects.get_or_create")
    def test_opted_in_loopback_request_uses_development_user(self, get_or_create):
        user = Mock(spec=User, username="frontend-dev")
        get_or_create.return_value = (user, True)
        request = RequestFactory().get(
            "/api/communities/",
            HTTP_X_DEVELOPMENT_USER="enabled",
        )
        request.META["REMOTE_ADDR"] = "127.0.0.1"

        result = DevelopmentUserAuthentication().authenticate(request)

        self.assertEqual(result, (user, None))
        get_or_create.assert_called_once_with(
            username="frontend-dev",
            defaults={"first_name": "Frontend", "last_name": "Developer"},
        )

    @override_settings(DEBUG=False, ENABLE_DEV_ANONYMOUS_USER=True)
    @patch("authentication.auth.User.objects.get_or_create")
    def test_disabled_outside_debug_mode(self, get_or_create):
        request = RequestFactory().get(
            "/api/communities/",
            HTTP_X_DEVELOPMENT_USER="enabled",
        )
        request.META["REMOTE_ADDR"] = "127.0.0.1"

        self.assertIsNone(DevelopmentUserAuthentication().authenticate(request))
        get_or_create.assert_not_called()

    @override_settings(DEBUG=True, ENABLE_DEV_ANONYMOUS_USER=True)
    @patch("authentication.auth.User.objects.get_or_create")
    def test_refuses_non_loopback_request(self, get_or_create):
        request = RequestFactory().get(
            "/api/communities/",
            HTTP_X_DEVELOPMENT_USER="enabled",
        )
        request.META["REMOTE_ADDR"] = "192.0.2.10"

        self.assertIsNone(DevelopmentUserAuthentication().authenticate(request))
        get_or_create.assert_not_called()
