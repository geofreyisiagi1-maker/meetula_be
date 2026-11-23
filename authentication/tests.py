import hashlib
from datetime import timedelta
from unittest.mock import Mock, patch

from allauth.account.models import EmailAddress
from django.contrib.auth.models import User
from django.test import RequestFactory, SimpleTestCase, TestCase, override_settings
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from communities.models import Community
from posts.models import Comment, Post
from communities.serializers import UserSerializer
from .auth import DevelopmentUserAuthentication
from .models import OAuthLoginCode


class EmailAuthenticationTests(TestCase):
    @patch("authentication.views.EmailAddress.send_confirmation")
    def test_signup_creates_unverified_user_and_sends_confirmation(
        self,
        send_confirmation,
    ):
        response = self.client.post(
            "/api/auth/signup/",
            {"email": "Person@Example.com", "password": "Uganda-Community-2026!"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        user = User.objects.get(email="person@example.com")
        self.assertTrue(user.check_password("Uganda-Community-2026!"))
        self.assertRegex(user.profile.username, r"^[a-z]+_[a-z]+_\d{4}$")
        self.assertEqual(response.data["username"], user.profile.username)
        self.assertFalse(EmailAddress.objects.get(user=user).verified)
        self.assertIn("verify your account", response.data["detail"])
        send_confirmation.assert_called_once()

    def test_signup_username_does_not_depend_on_email_and_is_unique(self):
        with patch("authentication.usernames.secrets.randbelow", side_effect=[0, 1]):
            first = self.client.post(
                "/api/auth/signup/",
                {"email": "same@example.com", "password": "Uganda-Community-2026!"},
                format="json",
            )
            second = self.client.post(
                "/api/auth/signup/",
                {"email": "different@example.com", "password": "Uganda-Community-2026!"},
                format="json",
            )

        self.assertEqual(first.status_code, status.HTTP_201_CREATED)
        self.assertEqual(second.status_code, status.HTTP_201_CREATED)
        self.assertNotEqual(first.data["username"], second.data["username"])

    def test_current_user_can_update_public_username_case_insensitively(self):
        user = User.objects.create_user(username="original-username")
        client = APIClient()
        client.force_authenticate(user=user)

        response = client.patch(
            "/api/auth/me/",
            {"username": "New_Handle"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["username"], "new_handle")
        user.refresh_from_db()
        self.assertEqual(user.username, "new_handle")
        serialized_user = UserSerializer(user).data
        self.assertEqual(serialized_user["username"], "new_handle")
        self.assertEqual(
            set(serialized_user),
            {"id", "username", "email", "first_name", "last_name"},
        )

    def test_current_user_rejects_an_existing_username_case_insensitively(self):
        User.objects.create_user(username="first-internal")
        other = User.objects.create_user(username="second-internal")
        other.profile.username = "taken_handle"
        other.profile.save(update_fields=["username"])
        client = APIClient()
        client.force_authenticate(user=User.objects.get(username="first-internal"))

        response = client.patch(
            "/api/auth/me/",
            {"username": "TAKEN_HANDLE"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("username", response.data)

    def test_login_requires_verified_email(self):
        user = User.objects.create_user(
            username="person",
            email="person@example.com",
            password="Uganda-Community-2026!",
        )
        EmailAddress.objects.create(
            user=user,
            email=user.email,
            primary=True,
            verified=False,
        )

        response = self.client.post(
            "/api/auth/login/",
            {"email": user.email, "password": "Uganda-Community-2026!"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("Verify your email", response.data["detail"])

    def test_signup_rejects_duplicate_email_case_insensitively(self):
        User.objects.create_user(
            username="existing",
            email="person@example.com",
            password="Uganda-Community-2026!",
        )

        response = self.client.post(
            "/api/auth/signup/",
            {"email": "PERSON@example.com", "password": "Uganda-Community-2026!"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("email", response.data)

    def test_login_returns_token_for_valid_email_credentials(self):
        user = User.objects.create_user(
            username="person",
            email="person@example.com",
            password="Uganda-Community-2026!",
        )
        EmailAddress.objects.create(
            user=user,
            email=user.email,
            primary=True,
            verified=True,
        )

        response = self.client.post(
            "/api/auth/login/",
            {"email": "PERSON@example.com", "password": "Uganda-Community-2026!"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["token"])

    def test_login_rejects_invalid_credentials(self):
        response = self.client.post(
            "/api/auth/login/",
            {"email": "person@example.com", "password": "wrong-password"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data, {"detail": "Email or password is incorrect."})

    def test_current_user_and_logout_use_revocable_token(self):
        user = User.objects.create_user(
            username="person",
            email="person@example.com",
            password="Uganda-Community-2026!",
        )
        EmailAddress.objects.create(
            user=user,
            email=user.email,
            primary=True,
            verified=True,
        )
        response = self.client.post(
            "/api/auth/login/",
            {"email": user.email, "password": "Uganda-Community-2026!"},
            format="json",
        )
        token = response.data["token"]

        me_response = self.client.get(
            "/api/auth/me/",
            HTTP_AUTHORIZATION=f"Token {token}",
        )
        logout_response = self.client.post(
            "/api/auth/logout/",
            HTTP_AUTHORIZATION=f"Token {token}",
        )
        after_logout = self.client.get(
            "/api/auth/me/",
            HTTP_AUTHORIZATION=f"Token {token}",
        )

        self.assertEqual(me_response.status_code, status.HTTP_200_OK)
        self.assertEqual(me_response.data["email"], user.email)
        self.assertEqual(logout_response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertEqual(after_logout.status_code, status.HTTP_401_UNAUTHORIZED)


    def test_google_code_exchange_is_single_use_and_expires(self):
        user = User.objects.create_user(username="google-user", email="google@example.com")
        login_code = "one-time-code"
        OAuthLoginCode.objects.create(
            code_hash=hashlib.sha256(login_code.encode()).hexdigest(),
            user=user,
            expires_at=timezone.now() + timedelta(minutes=2),
        )

        response = self.client.post(
            "/api/auth/google/exchange/",
            {"code": login_code},
            format="json",
        )
        replay = self.client.post(
            "/api/auth/google/exchange/",
            {"code": login_code},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(replay.status_code, status.HTTP_400_BAD_REQUEST)

    def test_google_code_exchange_rejects_expired_code(self):
        user = User.objects.create_user(username="google-user", email="google@example.com")
        login_code = "expired-code"
        OAuthLoginCode.objects.create(
            code_hash=hashlib.sha256(login_code.encode()).hexdigest(),
            user=user,
            expires_at=timezone.now() - timedelta(seconds=1),
        )

        response = self.client.post(
            "/api/auth/google/exchange/",
            {"code": login_code},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_google_login_completion_uses_allauth_session_and_redirects_with_code(self):
        user = User.objects.create_user(username="google-user", email="google@example.com")
        self.client.force_login(user)

        response = self.client.get("/api/auth/google/complete/")

        self.assertEqual(response.status_code, status.HTTP_302_FOUND)
        self.assertIn("http://localhost:3000/auth/callback?code=", response["Location"])
        self.assertEqual(OAuthLoginCode.objects.filter(user=user).count(), 1)


class PublicProfileApiTests(TestCase):
    def setUp(self):
        self.profile_user = User.objects.create_user(
            username="profile_owner",
            first_name="Profile",
            last_name="Owner",
        )
        self.public_community = Community.objects.create(
            name="Public profile community",
            community_url="c/public-profile",
            description="Public profile activity.",
            owner=self.profile_user,
        )
        self.public_community.members.add(self.profile_user)
        self.post = Post.objects.create(
            community=self.public_community,
            author=self.profile_user,
            post_type="discussion",
            title="A public profile post",
            content="Public content.",
        )
        self.comment = Comment.objects.create(
            post=self.post,
            author=self.profile_user,
            content="A public profile comment.",
        )
        self.private_community = Community.objects.create(
            name="Private profile community",
            community_url="c/private-profile",
            description="Private profile activity.",
            owner=self.profile_user,
            visibility="private",
        )
        self.private_community.members.add(self.profile_user)
        Post.objects.create(
            community=self.private_community,
            author=self.profile_user,
            post_type="discussion",
            title="A private profile post",
            content="Private content.",
        )

    def test_profile_endpoint_returns_user_and_only_public_activity(self):
        response = self.client.get("/api/profiles/profile_owner/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["user"]["id"], self.profile_user.pk)
        self.assertEqual(response.data["user"]["username"], "profile_owner")
        self.assertEqual(
            [post["title"] for post in response.data["posts"]],
            ["A public profile post"],
        )
        self.assertEqual(
            [comment["post_title"] for comment in response.data["comments"]],
            ["A public profile post"],
        )
        self.assertEqual(
            [community["slug"] for community in response.data["communities"]],
            ["public-profile"],
        )

    def test_profile_endpoint_is_public_and_username_case_insensitive(self):
        response = self.client.get("/api/profiles/PROFILE_OWNER/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_profile_endpoint_returns_404_for_unknown_username(self):
        response = self.client.get("/api/profiles/does-not-exist/")

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


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
