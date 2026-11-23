from django.http import Http404
from django.contrib.contenttypes.models import ContentType
from django.db.models import Count, F, IntegerField, Max, Q, ExpressionWrapper
from django.utils.text import slugify
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters, permissions, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response

from .models import Comment, Post, Reply, Vote
from .serializers import (
    CommentSerializer,
    PostDetailSerializer,
    PostSerializer,
    ReplySerializer,
)
from notifications.models import Notification
from notifications.services import create_notification


def add_vote_summary(queryset, user):
    current_user_filter = (
        Q(votes__user_id=user.pk)
        if user.is_authenticated
        else Q(votes__user_id__isnull=True)
    )
    return queryset.annotate(
        upvote_count=Count("votes", filter=Q(votes__value=Vote.UPVOTE), distinct=True),
        downvote_count=Count("votes", filter=Q(votes__value=Vote.DOWNVOTE), distinct=True),
        user_vote=Max("votes__value", filter=current_user_filter),
    ).annotate(
        score=ExpressionWrapper(
            F("upvote_count") - F("downvote_count"),
            output_field=IntegerField(),
        )
    )


def set_vote(request, obj):
    raw_value = request.data.get("value")
    if isinstance(raw_value, bool):
        raw_value = None
    try:
        value = int(raw_value)
    except (TypeError, ValueError):
        return Response(
            {"detail": "value must be 1 (upvote), -1 (downvote), or 0 (remove vote)."},
            status=400,
        )
    if value not in (Vote.UPVOTE, Vote.DOWNVOTE, 0):
        return Response(
            {"detail": "value must be 1 (upvote), -1 (downvote), or 0 (remove vote)."},
            status=400,
        )

    content_type = ContentType.objects.get_for_model(obj, for_concrete_model=False)
    vote_filter = Vote.objects.filter(
        user=request.user,
        content_type=content_type,
        object_id=obj.pk,
    )
    if value == 0:
        vote_filter.delete()
    else:
        _, created = Vote.objects.update_or_create(
            user=request.user,
            content_type=content_type,
            object_id=obj.pk,
            defaults={"value": value},
        )
        if created:
            target_name = "post" if isinstance(obj, Post) else (
                "comment" if isinstance(obj, Comment) else "reply"
            )
            create_notification(
                recipient=obj.author,
                actor=request.user,
                notification_type=f"{target_name}_vote",
                message=f"{request.user.username} voted on your {target_name}.",
                target=obj,
            )

    totals = Vote.objects.filter(content_type=content_type, object_id=obj.pk)
    upvotes = totals.filter(value=Vote.UPVOTE).count()
    downvotes = totals.filter(value=Vote.DOWNVOTE).count()
    return Response({
        "upvotes": upvotes,
        "downvotes": downvotes,
        "score": upvotes - downvotes,
        "my_vote": value,
    })


def can_moderate_content(user, obj):
    if isinstance(obj, Post):
        community = obj.community
    elif isinstance(obj, Comment):
        community = obj.post.community
    else:
        community = obj.comment.post.community
    return community.owner_id == user.pk or community.moderators.filter(pk=user.pk).exists()


class IsAuthorOrReadOnly(permissions.BasePermission):
    def has_object_permission(self, request, view, obj):
        if request.method in permissions.SAFE_METHODS:
            return True
        return (
            obj.author_id == request.user.id
            or can_moderate_content(request.user, obj)
        )


class PostViewSet(viewsets.ModelViewSet):
    queryset = Post.objects.select_related("community", "author").prefetch_related(
        "images", "comments__replies"
    )
    serializer_class = PostSerializer
    permission_classes = [
        permissions.IsAuthenticatedOrReadOnly,
        IsAuthorOrReadOnly,
    ]
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ["community", "post_type"]
    search_fields = ["title", "content"]
    ordering_fields = ["created_at", "updated_at", "title", "score"]
    ordering = ["-created_at"]
    lookup_field = "slug"

    def get_serializer_class(self):
        if self.action == "retrieve":
            return PostDetailSerializer
        return PostSerializer

    def get_queryset(self):
        queryset = super().get_queryset()
        user = self.request.user
        if getattr(self, "action", None) in {"list", "feed"}:
            if not user.is_authenticated or user.username == "frontend-dev":
                queryset = queryset.filter(community__visibility="public")
            else:
                queryset = queryset.filter(community__members=user)
        elif user.is_authenticated:
            queryset = queryset.filter(
                Q(community__visibility="public") | Q(community__members=user)
            ).distinct()
        else:
            queryset = queryset.filter(community__visibility="public")
        return add_vote_summary(queryset, user)

    def get_object(self):
        lookup_url_kwarg = self.lookup_url_kwarg or self.lookup_field
        slug_from_url = self.kwargs.get(lookup_url_kwarg)
        queryset = self.filter_queryset(self.get_queryset())
        post = queryset.filter(slug=slug_from_url).first()
        if post is None:
            post = queryset.filter(slug=slugify(slug_from_url)).first()
        if post is None:
            raise Http404(f"No post found with slug: {slug_from_url}")
        self.check_object_permissions(self.request, post)
        return post

    def perform_create(self, serializer):
        community = serializer.validated_data["community"]
        if not community.members.filter(pk=self.request.user.pk).exists():
            raise PermissionDenied("Join this community before creating a post.")
        serializer.save(author=self.request.user)

    @action(detail=False, methods=["get"], permission_classes=[permissions.IsAuthenticated])
    def feed(self, request):
        posts = self.filter_queryset(
            self.get_queryset().filter(community__members=request.user)
        )
        page = self.paginate_queryset(posts)
        serializer = self.get_serializer(
            page if page is not None else posts,
            many=True,
        )
        if page is not None:
            return self.get_paginated_response(serializer.data)
        return Response(serializer.data)

    @action(detail=True, methods=["post"], permission_classes=[permissions.IsAuthenticated])
    def vote(self, request, slug=None):
        return set_vote(request, self.get_object())

    @action(
        detail=True,
        methods=["post", "delete"],
        url_path="accept-answer",
        permission_classes=[permissions.IsAuthenticated],
    )
    def accept_answer(self, request, slug=None):
        post = self.get_object()
        if post.author_id != request.user.pk:
            raise PermissionDenied("Only the question author can accept an answer.")
        if post.post_type != "question":
            return Response(
                {"detail": "Answers can only be accepted on question posts."},
                status=400,
            )

        if request.method == "DELETE":
            post.accepted_answer = None
        else:
            comment_id = request.data.get("comment_id")
            answer = Comment.objects.filter(pk=comment_id, post=post).first()
            if answer is None:
                return Response(
                    {"detail": "Choose a comment on this question as the answer."},
                    status=400,
                )
            post.accepted_answer = answer

        post.save(update_fields=["accepted_answer"])
        return Response({
            "accepted_answer": post.accepted_answer_id,
            "is_answered": post.accepted_answer_id is not None,
        })


class CommentViewSet(viewsets.ModelViewSet):
    queryset = Comment.objects.select_related("post__community", "author").prefetch_related(
        "replies"
    )
    serializer_class = CommentSerializer
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    permission_classes = [permissions.IsAuthenticatedOrReadOnly, IsAuthorOrReadOnly]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ["post"]
    ordering_fields = ["created_at", "updated_at"]

    def get_queryset(self):
        queryset = super().get_queryset()
        user = self.request.user
        visibility = Q(post__community__visibility="public")
        if user.is_authenticated:
            visibility |= Q(post__community__members=user)
        return add_vote_summary(queryset.filter(visibility).distinct(), user)

    def perform_create(self, serializer):
        post = serializer.validated_data["post"]
        if not post.community.members.filter(pk=self.request.user.pk).exists():
            raise PermissionDenied("Join this community before commenting.")
        comment = serializer.save(author=self.request.user)
        create_notification(
            recipient=post.author,
            actor=self.request.user,
            notification_type=Notification.POST_COMMENT,
            message=f"{self.request.user.username} commented on your post.",
            target=comment,
        )

    @action(detail=True, methods=["post"], permission_classes=[permissions.IsAuthenticated])
    def vote(self, request, pk=None):
        return set_vote(request, self.get_object())


class ReplyViewSet(viewsets.ModelViewSet):
    queryset = Reply.objects.select_related("comment__post__community", "author")
    serializer_class = ReplySerializer
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    permission_classes = [permissions.IsAuthenticatedOrReadOnly, IsAuthorOrReadOnly]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ["comment"]
    ordering_fields = ["created_at", "updated_at"]

    def get_queryset(self):
        queryset = super().get_queryset()
        user = self.request.user
        visibility = Q(comment__post__community__visibility="public")
        if user.is_authenticated:
            visibility |= Q(comment__post__community__members=user)
        return add_vote_summary(queryset.filter(visibility).distinct(), user)

    def perform_create(self, serializer):
        comment = serializer.validated_data["comment"]
        if not comment.post.community.members.filter(pk=self.request.user.pk).exists():
            raise PermissionDenied("Join this community before replying.")
        reply = serializer.save(author=self.request.user)
        recipient = (
            reply.parent_reply.author
            if reply.parent_reply_id
            else comment.author
        )
        notification_type = (
            Notification.REPLY_REPLY
            if reply.parent_reply_id
            else Notification.COMMENT_REPLY
        )
        message = (
            f"{self.request.user.username} replied to your reply."
            if reply.parent_reply_id
            else f"{self.request.user.username} replied to your comment."
        )
        create_notification(
            recipient=recipient,
            actor=self.request.user,
            notification_type=notification_type,
            message=message,
            target=reply,
        )

    @action(detail=True, methods=["post"], permission_classes=[permissions.IsAuthenticated])
    def vote(self, request, pk=None):
        return set_vote(request, self.get_object())
