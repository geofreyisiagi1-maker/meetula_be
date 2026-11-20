import re

from django.contrib.auth.models import User
from rest_framework import serializers

from .models import Community


class UserSerializer(serializers.ModelSerializer):
    clerk_id = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ["id", "username", "email", "first_name", "last_name", "clerk_id"]

    def get_clerk_id(self, obj):
        return obj.username


class CommunitySerializer(serializers.ModelSerializer):
    slug = serializers.ReadOnlyField()
    owner = UserSerializer(read_only=True)
    members = UserSerializer(many=True, read_only=True)
    moderators = UserSerializer(many=True, read_only=True)
    member_count = serializers.ReadOnlyField()
    post_count = serializers.ReadOnlyField()
    rules = serializers.ListField(
        child=serializers.CharField(max_length=500, allow_blank=False),
        required=False,
        allow_empty=True,
    )
    profile_image = serializers.ImageField(required=False, allow_null=True)
    cover_image = serializers.ImageField(required=False, allow_null=True)

    class Meta:
        model = Community
        fields = [
            "id",
            "name",
            "community_url",
            "slug",
            "description",
            "country",
            "rules",
            "category",
            "visibility",
            "profile_image",
            "cover_image",
            "member_count",
            "post_count",
            "created_at",
            "owner",
            "members",
            "moderators",
        ]
        read_only_fields = [
            "slug",
            "created_at",
            "member_count",
            "post_count",
            "owner",
            "members",
            "moderators",
        ]

    def validate_community_url(self, value):
        normalized = value.strip().lower()
        if re.fullmatch(r"c/[a-z0-9]+(?:-[a-z0-9]+)*", normalized) is None:
            raise serializers.ValidationError(
                "Enter a community URL in the format c/food or c/food-recipes."
            )
        communities = Community.objects.filter(community_url=normalized)
        if self.instance is not None:
            communities = communities.exclude(pk=self.instance.pk)
        if communities.exists():
            raise serializers.ValidationError("This community URL is already in use.")
        return normalized

    def create(self, validated_data):
        user = self.context["request"].user
        community = Community.objects.create(owner=user, **validated_data)
        community.members.add(user)
        return community
