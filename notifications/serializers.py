from rest_framework import serializers

from communities.serializers import UserSerializer
from .models import Notification


class NotificationSerializer(serializers.ModelSerializer):
    actor = UserSerializer(read_only=True)
    target_type = serializers.SerializerMethodField()
    target_id = serializers.IntegerField(source="object_id", read_only=True)

    class Meta:
        model = Notification
        fields = [
            "id",
            "notification_type",
            "message",
            "actor",
            "target_type",
            "target_id",
            "is_read",
            "created_at",
            "read_at",
        ]
        read_only_fields = fields

    def get_target_type(self, obj):
        return obj.content_type.model if obj.content_type_id else None
