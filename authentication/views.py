import hashlib
import secrets
from datetime import timedelta
from urllib.parse import urlencode

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.validators import RegexValidator
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.http import Http404
from django.shortcuts import redirect
from django.utils import timezone
from allauth.account.models import EmailAddress
from allauth.account.utils import setup_user_email
from rest_framework import serializers, status
from rest_framework.authtoken.models import Token
from rest_framework.authentication import SessionAuthentication
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import OAuthLoginCode, UserProfile
from .usernames import generate_unique_username
from communities.models import Community
from communities.serializers import CommunitySerializer
from posts.models import Comment, Post
from posts.serializers import CommentSerializer, PostSerializer

User = get_user_model()


class EmailPasswordSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, trim_whitespace=False)


class SignupSerializer(EmailPasswordSerializer):
    password = serializers.CharField(
        write_only=True,
        trim_whitespace=False,
        min_length=8,
    )

    def validate_email(self, value):
        normalized = value.strip().lower()
        if User.objects.filter(email__iexact=normalized).exists():
            raise serializers.ValidationError("An account with this email already exists.")
        return normalized

    def validate_password(self, value):
        try:
            validate_password(value)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(list(exc.messages)) from exc
        return value


class UsernameUpdateSerializer(serializers.Serializer):
    username = serializers.CharField(
        min_length=3,
        max_length=30,
        validators=[
            RegexValidator(
                regex=r"^[a-zA-Z0-9_]+$",
                message="Use only letters, numbers, and underscores.",
            ),
        ],
    )

    def validate_username(self, value):
        username = value.strip().lower()
        profiles = UserProfile.objects.filter(username__iexact=username)
        user = self.context["request"].user
        profiles = profiles.exclude(user=user)
        existing_users = User.objects.filter(username__iexact=username).exclude(pk=user.pk)
        if profiles.exists() or existing_users.exists():
            raise serializers.ValidationError("This username is already taken.")
        return username


def user_data(user):
    return {
        "id": user.pk,
        "username": user.profile.username,
        "email": user.email,
        "first_name": user.first_name,
        "last_name": user.last_name,
    }


def issue_token(user):
    token, _ = Token.objects.get_or_create(user=user)
    return token.key


class SignupView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        serializer = SignupSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data["email"]
        user = User.objects.create_user(
            username=generate_unique_username(),
            email=email,
            password=serializer.validated_data["password"],
        )
        setup_user_email(request._request, user, [])
        EmailAddress.objects.get_primary(user).send_confirmation(
            request._request,
            signup=True,
        )
        return Response(
            {
                "detail": "Check your email to verify your account before logging in.",
                "username": user.profile.username,
            },
            status=status.HTTP_201_CREATED,
        )


class LoginView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        serializer = EmailPasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        credentials = serializer.validated_data
        user = User.objects.filter(email__iexact=credentials["email"]).first()
        if user is None or not user.check_password(credentials["password"]) or not user.is_active:
            return Response(
                {"detail": "Email or password is incorrect."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not EmailAddress.objects.filter(
            user=user,
            email__iexact=user.email,
            verified=True,
        ).exists():
            return Response(
                {"detail": "Verify your email address before logging in."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response({"token": issue_token(user), "user": user_data(user)})


class CurrentUserView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(user_data(request.user))

    def patch(self, request):
        serializer = UsernameUpdateSerializer(
            data=request.data,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)
        profile = request.user.profile
        username = serializer.validated_data["username"]
        try:
            with transaction.atomic():
                profile.username = username
                profile.save(update_fields=["username"])
                request.user.username = username
                request.user.save(update_fields=["username"])
        except IntegrityError as exc:
            raise serializers.ValidationError({
                "username": "This username is already taken.",
            }) from exc
        return Response(user_data(request.user))


class PublicProfileView(APIView):
    permission_classes = [AllowAny]

    def get(self, request, username):
        profile_user = User.objects.filter(
            profile__username__iexact=username,
        ).first()
        if profile_user is None:
            raise Http404("Profile not found.")

        posts = Post.objects.filter(
            author=profile_user,
            community__visibility="public",
        ).select_related("author", "community").prefetch_related("images", "comments__replies")
        comments = Comment.objects.filter(
            author=profile_user,
            post__community__visibility="public",
        ).select_related("author", "post", "post__community").prefetch_related("replies")
        communities = Community.objects.filter(visibility="public").filter(
            Q(owner=profile_user)
            | Q(members=profile_user)
            | Q(moderators=profile_user)
            | Q(posts__author=profile_user)
            | Q(posts__comments__author=profile_user)
        ).select_related("owner").prefetch_related("members", "moderators").distinct()

        serialized_comments = CommentSerializer(
            comments,
            many=True,
            context={"request": request},
        ).data
        for comment, serialized_comment in zip(comments, serialized_comments):
            serialized_comment["post_title"] = comment.post.title
            serialized_comment["post_slug"] = comment.post.slug

        return Response({
            "user": {
                "id": profile_user.pk,
                "username": profile_user.profile.username,
                "first_name": profile_user.first_name,
                "last_name": profile_user.last_name,
                "date_joined": profile_user.date_joined,
            },
            "posts": PostSerializer(
                posts,
                many=True,
                context={"request": request},
            ).data,
            "comments": serialized_comments,
            "communities": CommunitySerializer(
                communities,
                many=True,
                context={"request": request},
            ).data,
        })


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        if isinstance(request.auth, Token):
            request.auth.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class GoogleLoginCompleteView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = [SessionAuthentication]

    def get(self, request):
        frontend_url = settings.FRONTEND_URL.rstrip("/")
        if not request.user.is_authenticated:
            response = redirect(f"{frontend_url}/auth/callback?error=google_auth_failed")
            response["Cache-Control"] = "no-store"
            response["Referrer-Policy"] = "no-referrer"
            return response

        raw_code = secrets.token_urlsafe(32)
        OAuthLoginCode.objects.create(
            code_hash=hashlib.sha256(raw_code.encode()).hexdigest(),
            user=request.user,
            expires_at=timezone.now() + timedelta(minutes=2),
        )
        response = redirect(f"{frontend_url}/auth/callback?{urlencode({'code': raw_code})}")
        response["Cache-Control"] = "no-store"
        response["Referrer-Policy"] = "no-referrer"
        return response


class GoogleTokenExchangeView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        code = request.data.get("code")
        if not isinstance(code, str) or not code:
            return Response(
                {"detail": "A login code is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        code_hash = hashlib.sha256(code.encode()).hexdigest()
        with transaction.atomic():
            login_code = (
                OAuthLoginCode.objects.select_for_update()
                .filter(code_hash=code_hash, used_at__isnull=True, expires_at__gt=timezone.now())
                .first()
            )
            if login_code is None:
                return Response(
                    {"detail": "This Google login code is invalid or expired."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            login_code.used_at = timezone.now()
            login_code.save(update_fields=["used_at"])
            token = issue_token(login_code.user)
            user = user_data(login_code.user)

        return Response({"token": token, "user": user})
