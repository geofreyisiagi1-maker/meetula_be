from rest_framework import serializers

from communities.models import Community, CommunityJoinRequest
from communities.serializers import UserSerializer
from posts.models import Comment, Post, Reply
from .models import Notification


class NotificationSerializer(serializers.ModelSerializer):
    actor = UserSerializer(read_only=True)
    target_type = serializers.SerializerMethodField()
    target_id = serializers.IntegerField(source="object_id", read_only=True)
    target_url = serializers.SerializerMethodField()

    class Meta:
        model = Notification
        fields = [
            "id",
            "notification_type",
            "message",
            "actor",
            "target_type",
            "target_id",
            "target_url",
            "is_read",
            "created_at",
            "read_at",
        ]
        read_only_fields = fields

    def get_target_type(self, obj):
        return obj.content_type.model if obj.content_type_id else None

    def get_target_url(self, obj):
        target = obj.target
        if isinstance(target, Post):
            return f"/post/{target.slug or target.pk}"
        if isinstance(target, Comment):
            return f"/post/{target.post.slug or target.post_id}"
        if isinstance(target, Reply):
            post = target.comment.post
            return f"/post/{post.slug or post.pk}"
        if isinstance(target, Community):
            return f"/c/{target.slug}"
        if isinstance(target, CommunityJoinRequest):
            return f"/c/{target.community.slug}"
        return None
