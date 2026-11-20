from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models


class Notification(models.Model):
    POST_COMMENT = "post_comment"
    COMMENT_REPLY = "comment_reply"
    REPLY_REPLY = "reply_reply"
    POST_VOTE = "post_vote"
    COMMENT_VOTE = "comment_vote"
    REPLY_VOTE = "reply_vote"
    COMMUNITY_JOIN_REQUEST = "community_join_request"
    JOIN_REQUEST_DECISION = "join_request_decision"
    TYPE_CHOICES = [
        (POST_COMMENT, "Comment on your post"),
        (COMMENT_REPLY, "Reply to your comment"),
        (REPLY_REPLY, "Reply to your reply"),
        (POST_VOTE, "Vote on your post"),
        (COMMENT_VOTE, "Vote on your comment"),
        (REPLY_VOTE, "Vote on your reply"),
        (COMMUNITY_JOIN_REQUEST, "Private community join request"),
        (JOIN_REQUEST_DECISION, "Private community join request decision"),
    ]

    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notifications",
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="notifications_sent",
        blank=True,
        null=True,
    )
    notification_type = models.CharField(max_length=32, choices=TYPE_CHOICES)
    message = models.CharField(max_length=255)
    content_type = models.ForeignKey(
        ContentType,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
    )
    object_id = models.PositiveBigIntegerField(blank=True, null=True)
    target = GenericForeignKey("content_type", "object_id")
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    read_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(
                fields=["recipient", "is_read", "-created_at"],
                name="notification_inbox_idx",
            )
        ]

    def __str__(self):
        return f"{self.recipient_id}: {self.message}"
