from django.contrib.auth.models import User
from django.db import models
from cloudinary.models import CloudinaryField


class Community(models.Model):
    CATEGORY_CHOICES = [
        ("TECH", "Technology"),
        ("SPORTS", "Sports"),
        ("NEWS", "News"),
        ("CULTURE", "Culture"),
        ("BUSINESS", "Business"),
        ("ENTERTAINMENT", "Entertainment"),
        ("LIFESTYLE", "Lifestyle"),
        ("SOCIAL", "Social"),
        ("PROFESSIONAL", "Professional"),
        ("HOBBY", "Hobbies & Interests"),
        ("HEALTH", "Health & Wellness"),
        ("EDUCATION", "Education"),
        ("OTHER", "Other"),
    ]

    name = models.CharField(max_length=255)
    community_url = models.CharField(max_length=255, unique=True)
    description = models.TextField()
    country = models.CharField(max_length=100, blank=True, default="")
    rules = models.JSONField(default=list, blank=True)
    category = models.CharField(
        max_length=50,
        choices=CATEGORY_CHOICES,
        default="OTHER",
    )
    VISIBILITY_CHOICES = [
        ("public", "Public"),
        ("private", "Private"),
    ]
    visibility = models.CharField(
        max_length=10,
        choices=VISIBILITY_CHOICES,
        default="public",
    )
    JOIN_POLICY_CHOICES = [
        ("open", "Open to all"),
        ("approval", "Requires approval"),
    ]
    join_policy = models.CharField(
        max_length=10,
        choices=JOIN_POLICY_CHOICES,
        default="open",
    )
    profile_image = CloudinaryField(
        "profile image",
        folder="communities",
        blank=True,
        null=True,
    )
    cover_image = CloudinaryField(
        "cover image",
        folder="communities",
        blank=True,
        null=True,
    )
    member_count = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    owner = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="created_communities",
    )
    members = models.ManyToManyField(User, related_name="communities")
    moderators = models.ManyToManyField(
        User,
        related_name="moderated_communities",
        blank=True,
    )

    class Meta:
        ordering = ["-created_at"]

    @property
    def slug(self):
        return self.community_url.removeprefix("c/")

    def __str__(self):
        return self.name

    @property
    def post_count(self):
        return self.posts.count()


class CommunityJoinRequest(models.Model):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    STATUS_CHOICES = [
        (PENDING, "Pending"),
        (APPROVED, "Approved"),
        (REJECTED, "Rejected"),
    ]

    community = models.ForeignKey(
        Community,
        on_delete=models.CASCADE,
        related_name="join_requests",
    )
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="community_join_requests",
    )
    status = models.CharField(
        max_length=10,
        choices=STATUS_CHOICES,
        default=PENDING,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["community", "user"],
                name="unique_community_join_request",
            )
        ]
        ordering = ["created_at"]

    def __str__(self):
        return f"{self.user_id} -> {self.community_id}: {self.status}"
