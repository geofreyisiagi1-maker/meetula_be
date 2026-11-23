from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey, GenericRelation
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.db.models import Q
from django.utils.text import slugify
from cloudinary.models import CloudinaryField


class Post(models.Model):
    POST_TYPE_CHOICES = [
        ("discussion", "Discussion"),
        ("question", "Question"),
    ]

    title = models.CharField(max_length=200)
    slug = models.SlugField(max_length=250, unique=True, blank=True, null=True)
    content = models.TextField()
    post_type = models.CharField(max_length=20, choices=POST_TYPE_CHOICES)
    community = models.ForeignKey(
        "communities.Community",
        on_delete=models.CASCADE,
        related_name="posts",
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="posts",
    )
    accepted_answer = models.ForeignKey(
        "Comment",
        on_delete=models.SET_NULL,
        related_name="accepted_for_posts",
        blank=True,
        null=True,
    )
    votes = GenericRelation("posts.Vote", related_query_name="post")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(
                fields=["community", "-created_at"],
                name="post_community_newest_idx",
            )
        ]

    def save(self, *args, **kwargs):
        if not self.slug:
            base_slug = slugify(self.title)[:230] or "post"
            candidate = base_slug
            suffix = 2
            while Post.objects.filter(slug=candidate).exclude(pk=self.pk).exists():
                candidate = f"{base_slug}-{suffix}"
                suffix += 1
            self.slug = candidate
        super().save(*args, **kwargs)

    def __str__(self):
        return self.title


class PostImage(models.Model):
    post = models.ForeignKey(Post, on_delete=models.CASCADE, related_name="images")
    image = CloudinaryField("image", folder="posts")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return self.post.title


class Comment(models.Model):
    post = models.ForeignKey(Post, on_delete=models.CASCADE, related_name="comments")
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="post_comments",
    )
    votes = GenericRelation("posts.Vote", related_query_name="comment")
    content = models.TextField()
    image = CloudinaryField("image", folder="comments", blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"Comment on {self.post.title}"


class Reply(models.Model):
    comment = models.ForeignKey(
        Comment,
        on_delete=models.CASCADE,
        related_name="replies",
    )
    parent_reply = models.ForeignKey(
        "self",
        on_delete=models.CASCADE,
        related_name="child_replies",
        blank=True,
        null=True,
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="comment_replies",
    )
    votes = GenericRelation("posts.Vote", related_query_name="reply")
    content = models.TextField()
    image = CloudinaryField("image", folder="replies", blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"Reply to comment {self.comment_id}"


class Vote(models.Model):
    UPVOTE = 1
    DOWNVOTE = -1
    VALUE_CHOICES = [
        (UPVOTE, "Upvote"),
        (DOWNVOTE, "Downvote"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="content_votes",
    )
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveBigIntegerField()
    target = GenericForeignKey("content_type", "object_id")
    value = models.SmallIntegerField(choices=VALUE_CHOICES)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "content_type", "object_id"],
                name="unique_user_content_vote",
            ),
            models.CheckConstraint(
                check=Q(value__in=[1, -1]),
                name="vote_value_is_up_or_down",
            ),
        ]
        indexes = [
            models.Index(
                fields=["content_type", "object_id"],
                name="vote_content_target_idx",
            )
        ]

    def __str__(self):
        return f"{self.user_id}: {self.value} on {self.content_type_id}:{self.object_id}"
