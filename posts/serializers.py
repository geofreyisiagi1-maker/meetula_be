from rest_framework import serializers

from communities.serializers import UserSerializer
from .models import Comment, Post, PostImage, Reply


class VoteSummarySerializerMixin:
    def get_upvotes(self, obj):
        if hasattr(obj, "upvote_count"):
            return obj.upvote_count
        return obj.votes.filter(value=1).count()

    def get_downvotes(self, obj):
        if hasattr(obj, "downvote_count"):
            return obj.downvote_count
        return obj.votes.filter(value=-1).count()

    def get_score(self, obj):
        return self.get_upvotes(obj) - self.get_downvotes(obj)

    def get_my_vote(self, obj):
        if hasattr(obj, "user_vote"):
            return obj.user_vote or 0
        request = self.context.get("request")
        if request is None or not request.user.is_authenticated:
            return 0
        vote = obj.votes.filter(user=request.user).values_list("value", flat=True).first()
        return vote or 0


class PostImageSerializer(serializers.ModelSerializer):
    image = serializers.SerializerMethodField()

    class Meta:
        model = PostImage
        fields = ["id", "image", "created_at"]

    def get_image(self, obj):
        if not obj.image:
            return None
        image_url = obj.image.url
        request = self.context.get("request")
        if request is not None:
            return request.build_absolute_uri(image_url)
        return image_url


class PostSerializer(VoteSummarySerializerMixin, serializers.ModelSerializer):
    content = serializers.CharField(trim_whitespace=False)
    author = UserSerializer(read_only=True)
    comment_count = serializers.IntegerField(source="comments.count", read_only=True)
    accepted_answer = serializers.PrimaryKeyRelatedField(read_only=True)
    is_answered = serializers.SerializerMethodField()
    upvotes = serializers.SerializerMethodField()
    downvotes = serializers.SerializerMethodField()
    score = serializers.SerializerMethodField()
    my_vote = serializers.SerializerMethodField()
    images = PostImageSerializer(many=True, read_only=True)
    uploaded_images = serializers.ListField(
        child=serializers.ImageField(
            max_length=1_000_000,
            allow_empty_file=False,
            use_url=False,
        ),
        write_only=True,
        required=False,
    )

    class Meta:
        model = Post
        fields = [
            "id",
            "community",
            "post_type",
            "title",
            "content",
            "author",
            "images",
            "uploaded_images",
            "slug",
            "created_at",
            "updated_at",
            "upvotes",
            "downvotes",
            "score",
            "my_vote",
            "comment_count",
            "accepted_answer",
            "is_answered",
        ]
        read_only_fields = ["slug", "created_at", "updated_at"]

    def get_is_answered(self, obj):
        return obj.post_type == "question" and obj.accepted_answer_id is not None

    def create(self, validated_data):
        images = validated_data.pop("uploaded_images", [])
        post = Post.objects.create(**validated_data)
        for image in images:
            PostImage.objects.create(post=post, image=image)
        return post

    def update(self, instance, validated_data):
        images = validated_data.pop("uploaded_images", [])
        if validated_data.get("post_type", instance.post_type) != "question":
            instance.accepted_answer = None
        instance = super().update(instance, validated_data)
        for image in images:
            PostImage.objects.create(post=instance, image=image)
        return instance


class CommentSerializer(VoteSummarySerializerMixin, serializers.ModelSerializer):
    content = serializers.CharField(trim_whitespace=False)
    author = UserSerializer(read_only=True)
    replies = serializers.SerializerMethodField()
    is_accepted_answer = serializers.SerializerMethodField()
    upvotes = serializers.SerializerMethodField()
    downvotes = serializers.SerializerMethodField()
    score = serializers.SerializerMethodField()
    my_vote = serializers.SerializerMethodField()

    class Meta:
        model = Comment
        fields = [
            "id",
            "post",
            "content",
            "image",
            "author",
            "replies",
            "is_accepted_answer",
            "upvotes",
            "downvotes",
            "score",
            "my_vote",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["created_at", "updated_at"]

    def get_replies(self, obj):
        roots = obj.replies.filter(parent_reply__isnull=True)
        return ReplySerializer(roots, many=True, context=self.context).data

    def get_is_accepted_answer(self, obj):
        if "accepted_answer_id" in self.context:
            return self.context["accepted_answer_id"] == obj.pk
        return obj.post.accepted_answer_id == obj.pk


class ReplySerializer(VoteSummarySerializerMixin, serializers.ModelSerializer):
    content = serializers.CharField(trim_whitespace=False)
    author = UserSerializer(read_only=True)
    replies = serializers.SerializerMethodField()
    upvotes = serializers.SerializerMethodField()
    downvotes = serializers.SerializerMethodField()
    score = serializers.SerializerMethodField()
    my_vote = serializers.SerializerMethodField()

    class Meta:
        model = Reply
        fields = [
            "id",
            "comment",
            "content",
            "image",
            "author",
            "parent_reply",
            "replies",
            "upvotes",
            "downvotes",
            "score",
            "my_vote",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["created_at", "updated_at"]

    def get_replies(self, obj):
        return ReplySerializer(obj.child_replies.all(), many=True, context=self.context).data

    def validate(self, attrs):
        parent_reply = attrs.get(
            "parent_reply",
            getattr(self.instance, "parent_reply", None),
        )
        comment = attrs.get("comment", getattr(self.instance, "comment", None))
        if parent_reply and parent_reply.comment_id != getattr(comment, "pk", None):
            raise serializers.ValidationError({
                "parent_reply": "Parent reply must belong to the same comment."
            })
        ancestor = parent_reply
        while ancestor is not None:
            if self.instance and ancestor.pk == self.instance.pk:
                raise serializers.ValidationError({
                    "parent_reply": "A reply cannot be nested beneath itself or its descendants."
                })
            ancestor = ancestor.parent_reply
        if (
            self.instance
            and self.instance.child_replies.exists()
            and comment.pk != self.instance.comment_id
        ):
            raise serializers.ValidationError({
                "comment": "A reply with nested replies cannot be moved to another comment."
            })
        return attrs


class PostDetailSerializer(PostSerializer):
    comments = serializers.SerializerMethodField()

    class Meta(PostSerializer.Meta):
        fields = PostSerializer.Meta.fields + ["comments"]

    def get_comments(self, obj):
        return CommentSerializer(
            obj.comments.all(),
            many=True,
            context={
                **self.context,
                "accepted_answer_id": obj.accepted_answer_id,
            },
        ).data
