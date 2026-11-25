from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse
from types import SimpleNamespace
from rest_framework import status
from rest_framework.test import APIClient
from unittest.mock import Mock, patch

from communities.models import Community
from communities.serializers import CommunitySerializer
from server.storage import CloudflareR2Storage, LEGACY_CLOUDINARY_PREFIX
from .models import Comment, Post, Reply


class CloudflareR2StorageTests(TestCase):
    @override_settings(R2_PUBLIC_URL="https://images.example.com")
    def test_r2_urls_use_the_public_bucket_domain(self):
        storage = CloudflareR2Storage(bucket_name="test-bucket")

        self.assertEqual(
            storage.url("posts/an image.png"),
            "https://images.example.com/posts/an%20image.png",
        )

    @override_settings(CLOUDINARY_CLOUD_NAME="legacy-cloud")
    @patch(
        "cloudinary.utils.cloudinary_url",
        return_value=("https://res.cloudinary.com/legacy-cloud/image/upload/old.png", {}),
    )
    def test_legacy_cloudinary_images_keep_their_urls(self, cloudinary_url):
        storage = CloudflareR2Storage(bucket_name="test-bucket")

        url = storage.url(f"{LEGACY_CLOUDINARY_PREFIX}communities/old.png")

        self.assertEqual(
            url,
            "https://res.cloudinary.com/legacy-cloud/image/upload/old.png",
        )
        cloudinary_url.assert_called_once_with("communities/old.png")


class PostApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(username="post-author")
        self.client.force_authenticate(user=self.user)
        self.community = Community.objects.create(
            name="Developers",
            community_url="c/developers",
            description="A developer community",
            category="TECH",
            owner=self.user,
        )
        self.community.members.add(self.user)

    def test_create_post_in_community(self):
        response = self.client.post(
            reverse("post-list"),
            {
                "community": self.community.pk,
                "post_type": "discussion",
                "title": "Welcome",
                "content": "Let's introduce ourselves.",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        post = Post.objects.get()
        self.assertEqual(post.author, self.user)
        self.assertEqual(post.community, self.community)
        self.assertEqual(response.data["images"], [])

    def test_multiline_content_is_preserved_when_created_edited_and_retrieved(self):
        post_content = "\nFirst paragraph.\n\nSecond paragraph.\n"
        response = self.client.post(
            reverse("post-list"),
            {
                "community": self.community.pk,
                "post_type": "discussion",
                "title": "Multiline post",
                "content": post_content,
            },
            format="multipart",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        post = Post.objects.get()
        self.assertEqual(post.content, post_content)
        self.assertEqual(response.data["content"], post_content)

        updated_post_content = "Updated first paragraph.\n\nUpdated second paragraph."
        response = self.client.patch(
            reverse("post-detail", args=[post.slug]),
            {"content": updated_post_content},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        post.refresh_from_db()
        self.assertEqual(post.content, updated_post_content)
        self.assertEqual(
            self.client.get(reverse("post-detail", args=[post.slug])).data["content"],
            updated_post_content,
        )

        comment_content = "\nComment first paragraph.\n\nComment second paragraph.\n"
        response = self.client.post(
            reverse("comment-list"),
            {"post": post.pk, "content": comment_content},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        comment = Comment.objects.get()
        self.assertEqual(comment.content, comment_content)

        reply_content = "\nReply first paragraph.\n\nReply second paragraph.\n"
        response = self.client.post(
            reverse("reply-list"),
            {"comment": comment.pk, "content": reply_content},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        reply = Reply.objects.get()
        self.assertEqual(reply.content, reply_content)

        updated_comment_content = "Edited comment.\n\nWith a second paragraph."
        response = self.client.patch(
            reverse("comment-detail", args=[comment.pk]),
            {"content": updated_comment_content},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        comment.refresh_from_db()
        self.assertEqual(comment.content, updated_comment_content)
        self.assertEqual(
            self.client.get(reverse("comment-detail", args=[comment.pk])).data["content"],
            updated_comment_content,
        )

        updated_reply_content = "Edited reply.\n\nWith a second paragraph."
        response = self.client.patch(
            reverse("reply-detail", args=[reply.pk]),
            {"content": updated_reply_content},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        reply.refresh_from_db()
        self.assertEqual(reply.content, updated_reply_content)
        self.assertEqual(
            self.client.get(reverse("reply-detail", args=[reply.pk])).data["content"],
            updated_reply_content,
        )

    def test_authors_can_edit_posts_comments_and_replies(self):
        author = User.objects.create_user(username="content-author")
        self.community.members.add(author)
        post = Post.objects.create(
            community=self.community,
            author=author,
            post_type="discussion",
            title="Original post",
            content="Original content",
        )
        self.client.force_authenticate(user=author)
        response = self.client.patch(
            reverse("post-detail", args=[post.slug]),
            {"title": "Edited post", "content": "Edited content"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        post.refresh_from_db()
        self.assertEqual(post.title, "Edited post")

        comment = Comment.objects.create(
            post=post,
            author=author,
            content="Original comment",
        )
        response = self.client.patch(
            reverse("comment-detail", args=[comment.pk]),
            {"content": "Edited comment"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        comment.refresh_from_db()
        self.assertEqual(comment.content, "Edited comment")

        reply = Reply.objects.create(
            comment=comment,
            author=author,
            content="Original reply",
        )
        response = self.client.patch(
            reverse("reply-detail", args=[reply.pk]),
            {"content": "Edited reply"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        reply.refresh_from_db()
        self.assertEqual(reply.content, "Edited reply")

    def test_non_author_cannot_edit_posts_comments_or_replies(self):
        author = User.objects.create_user(username="content-author")
        outsider = User.objects.create_user(username="content-outsider")
        self.community.members.add(author, outsider)
        post = Post.objects.create(
            community=self.community,
            author=author,
            post_type="discussion",
            title="Original post",
            content="Original content",
        )
        comment = Comment.objects.create(
            post=post,
            author=author,
            content="Original comment",
        )
        reply = Reply.objects.create(
            comment=comment,
            author=author,
            content="Original reply",
        )
        self.client.force_authenticate(user=outsider)

        post_response = self.client.patch(
            reverse("post-detail", args=[post.slug]),
            {"title": "Changed"},
            format="json",
        )
        comment_response = self.client.patch(
            reverse("comment-detail", args=[comment.pk]),
            {"content": "Changed"},
            format="json",
        )
        reply_response = self.client.patch(
            reverse("reply-detail", args=[reply.pk]),
            {"content": "Changed"},
            format="json",
        )

        self.assertEqual(post_response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(comment_response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(reply_response.status_code, status.HTTP_403_FORBIDDEN)

    def test_question_author_can_accept_replace_and_unaccept_one_answer(self):
        question_author = User.objects.create_user(username="question-author")
        self.community.members.add(question_author)
        self.client.force_authenticate(user=question_author)
        post = Post.objects.create(
            community=self.community,
            author=question_author,
            post_type="question",
            title="Question",
            content="Question content",
        )
        first_answer = Comment.objects.create(
            post=post,
            author=self.user,
            content="First answer",
        )
        second_answer = Comment.objects.create(
            post=post,
            author=self.user,
            content="Second answer",
        )
        url = reverse("post-accept-answer", args=[post.slug])

        response = self.client.post(
            url,
            {"comment_id": first_answer.pk},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["accepted_answer"], first_answer.pk)
        self.assertTrue(response.data["is_answered"])
        post.refresh_from_db()
        self.assertEqual(post.accepted_answer, first_answer)

        detail = self.client.get(reverse("post-detail", args=[post.slug]))
        self.assertEqual(detail.data["accepted_answer"], first_answer.pk)
        self.assertTrue(detail.data["is_answered"])
        self.assertTrue(
            next(
                comment["is_accepted_answer"]
                for comment in detail.data["comments"]
                if comment["id"] == first_answer.pk
            )
        )

        response = self.client.post(
            url,
            {"comment_id": second_answer.pk},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["accepted_answer"], second_answer.pk)

        other_post = Post.objects.create(
            community=self.community,
            author=self.user,
            post_type="question",
            title="Another question",
            content="Another question",
        )
        unrelated_comment = Comment.objects.create(
            post=other_post,
            author=self.user,
            content="Unrelated answer",
        )
        response = self.client.post(
            url,
            {"comment_id": unrelated_comment.pk},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        post.refresh_from_db()
        self.assertEqual(post.accepted_answer, second_answer)

        response = self.client.delete(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsNone(response.data["accepted_answer"])
        self.assertFalse(response.data["is_answered"])

    def test_only_question_author_can_accept_an_answer(self):
        other_user = User.objects.create_user(username="another-user")
        post = Post.objects.create(
            community=self.community,
            author=other_user,
            post_type="question",
            title="Question",
            content="Question content",
        )
        answer = Comment.objects.create(
            post=post,
            author=self.user,
            content="Answer",
        )

        response = self.client.post(
            reverse("post-accept-answer", args=[post.slug]),
            {"comment_id": answer.pk},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        post.refresh_from_db()
        self.assertIsNone(post.accepted_answer)

    def test_discussion_cannot_accept_an_answer(self):
        post = Post.objects.create(
            community=self.community,
            author=self.user,
            post_type="discussion",
            title="Discussion",
            content="Discussion content",
        )

        response = self.client.post(
            reverse("post-accept-answer", args=[post.slug]),
            {"comment_id": "1"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_changing_question_to_discussion_clears_accepted_answer(self):
        post = Post.objects.create(
            community=self.community,
            author=self.user,
            post_type="question",
            title="Question",
            content="Question content",
        )
        answer = Comment.objects.create(
            post=post,
            author=self.user,
            content="Answer",
        )
        post.accepted_answer = answer
        post.save(update_fields=["accepted_answer"])

        response = self.client.patch(
            reverse("post-detail", args=[post.slug]),
            {"post_type": "discussion"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        post.refresh_from_db()
        self.assertIsNone(post.accepted_answer)
        self.assertFalse(response.data["is_answered"])

    def test_post_type_must_be_discussion_or_question(self):
        response = self.client.post(
            reverse("post-list"),
            {
                "community": self.community.pk,
                "post_type": "announcement",
                "title": "Welcome",
                "content": "Hello",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("post_type", response.data)

    def test_post_vote_can_be_changed_or_removed(self):
        post = Post.objects.create(
            community=self.community,
            author=self.user,
            post_type="discussion",
            title="Voting",
            content="Vote on this post.",
        )
        vote_url = reverse("post-vote", args=[post.slug])

        response = self.client.post(vote_url, {"value": 1}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["score"], 1)
        self.assertEqual(response.data["my_vote"], 1)

        response = self.client.post(vote_url, {"value": -1}, format="json")
        self.assertEqual(response.data["upvotes"], 0)
        self.assertEqual(response.data["downvotes"], 1)
        self.assertEqual(response.data["score"], -1)

        response = self.client.post(vote_url, {"value": 0}, format="json")
        self.assertEqual(response.data["score"], 0)
        self.assertEqual(response.data["my_vote"], 0)

    def test_duplicate_post_titles_receive_distinct_slugs(self):
        first = Post.objects.create(
            community=self.community,
            author=self.user,
            post_type="discussion",
            title="Same title",
            content="First",
        )
        second = Post.objects.create(
            community=self.community,
            author=self.user,
            post_type="discussion",
            title="Same title",
            content="Second",
        )

        self.assertNotEqual(first.slug, second.slug)

    def test_same_community_name_can_have_unique_custom_urls(self):
        another_community = Community.objects.create(
            name=self.community.name,
            community_url="c/developers-two",
            description="Another community with the same name",
            category="SOCIAL",
            owner=self.user,
        )
        self.assertNotEqual(self.community.community_url, another_community.community_url)

    def test_create_community_uses_custom_community_url(self):
        response = self.client.post(
            reverse("community-list"),
            {
                "name": "Food recipes",
                "community_url": "c/food-recipes",
                "description": "Recipes and cooking.",
                "visibility": "private",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["slug"], "food-recipes")
        self.assertEqual(response.data["community_url"], "c/food-recipes")
        self.assertEqual(response.data["visibility"], "private")
        self.assertEqual(response.data["category"], "OTHER")
        self.assertTrue(
            Community.objects.get(community_url="c/food-recipes").members.filter(
                pk=self.user.pk
            ).exists()
        )

    def test_duplicate_custom_community_url_is_rejected(self):
        response = self.client.post(
            reverse("community-list"),
            {
                "name": "Another food community",
                "community_url": "c/developers",
                "description": "A duplicate URL.",
                "visibility": "public",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("community_url", response.data)

    @patch("communities.serializers.Community.objects.create")
    def test_community_model_stores_profile_and_cover_images(self, create_community):
        profile_image = object()
        cover_image = object()
        created_community = SimpleNamespace(
            members=SimpleNamespace(add=Mock()),
            moderators=SimpleNamespace(add=Mock()),
        )
        create_community.return_value = created_community
        serializer = CommunitySerializer(
            context={"request": SimpleNamespace(user=self.user)}
        )
        serializer.create({
            "name": "Cooking Club",
            "community_url": "c/cooking-club",
            "description": "Recipes and food.",
            "category": "OTHER",
            "visibility": "public",
            "profile_image": profile_image,
            "cover_image": cover_image,
        })
        self.assertEqual(
            create_community.call_args.kwargs["community_url"],
            "c/cooking-club",
        )
        self.assertEqual(create_community.call_args.kwargs["profile_image"], profile_image)
        self.assertEqual(create_community.call_args.kwargs["cover_image"], cover_image)
        self.assertEqual(create_community.call_args.kwargs["visibility"], "public")

    def test_joined_community_feed_includes_vote_summaries(self):
        post = Post.objects.create(
            community=self.community,
            author=self.user,
            post_type="question",
            title="Feed post",
            content="Show this in my feed.",
        )

        response = self.client.get(reverse("post-feed"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["results"]), 1)
        self.assertEqual(response.data["results"][0]["id"], post.pk)
        self.assertEqual(response.data["results"][0]["score"], 0)

    def test_feed_can_sort_by_vote_score(self):
        higher_scored_post = Post.objects.create(
            community=self.community,
            author=self.user,
            post_type="discussion",
            title="Higher score",
            content="Upvoted post.",
        )
        lower_scored_post = Post.objects.create(
            community=self.community,
            author=self.user,
            post_type="discussion",
            title="Lower score",
            content="Downvoted post.",
        )
        self.client.post(
            reverse("post-vote", args=[higher_scored_post.slug]),
            {"value": 1},
            format="json",
        )
        self.client.post(
            reverse("post-vote", args=[lower_scored_post.slug]),
            {"value": -1},
            format="json",
        )

        response = self.client.get(reverse("post-feed"), {"ordering": "-score"})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            [post["id"] for post in response.data["results"]],
            [higher_scored_post.pk, lower_scored_post.pk],
        )

    def test_public_post_visibility_and_personalized_listing(self):
        joined_post = Post.objects.create(
            community=self.community,
            author=self.user,
            post_type="discussion",
            title="Joined post",
            content="Visible in personalized list.",
        )
        public_community = Community.objects.create(
            name="Public community",
            community_url="c/public",
            description="Readable without joining",
            category="SOCIAL",
            owner=User.objects.create_user(username="public-owner"),
        )
        public_post = Post.objects.create(
            community=public_community,
            author=public_community.owner,
            post_type="discussion",
            title="Public post",
            content="Readable publicly.",
        )
        private_community = Community.objects.create(
            name="Private community",
            community_url="c/private",
            description="Members only",
            category="SOCIAL",
            visibility="private",
            owner=User.objects.create_user(username="private-owner"),
        )
        private_post = Post.objects.create(
            community=private_community,
            author=private_community.owner,
            post_type="discussion",
            title="Private post",
            content="Only members should see this.",
        )

        anonymous_client = APIClient()
        response = anonymous_client.get(reverse("post-list"))
        anonymous_ids = {post["id"] for post in response.data["results"]}
        self.assertEqual(anonymous_ids, {joined_post.pk, public_post.pk})
        self.assertEqual(
            anonymous_client.get(reverse("post-detail", args=[public_post.slug])).status_code,
            status.HTTP_200_OK,
        )
        self.assertEqual(
            anonymous_client.get(reverse("post-detail", args=[private_post.slug])).status_code,
            status.HTTP_404_NOT_FOUND,
        )

        self.client.force_authenticate(user=self.user)
        response = self.client.get(reverse("post-list"))
        personalized_ids = {post["id"] for post in response.data["results"]}
        self.assertEqual(personalized_ids, {joined_post.pk})
        self.assertEqual(
            self.client.get(reverse("post-detail", args=[public_post.slug])).status_code,
            status.HTTP_200_OK,
        )
        self.assertEqual(
            self.client.get(reverse("post-detail", args=[private_post.slug])).status_code,
            status.HTTP_404_NOT_FOUND,
        )

    def test_private_community_join_request_requires_owner_approval(self):
        private_community = Community.objects.create(
            name="Private group",
            community_url="c/private-group",
            description="Approval is required",
            category="SOCIAL",
            visibility="private",
            owner=self.user,
        )
        applicant = User.objects.create_user(username="applicant")
        self.client.force_authenticate(user=applicant)

        response = self.client.post(
            reverse("community-join", args=[private_community.slug]),
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)
        self.assertFalse(private_community.members.filter(pk=applicant.pk).exists())
        self.assertEqual(
            self.client.get(reverse("community-list")).status_code,
            status.HTTP_200_OK,
        )
        self.assertNotIn(
            private_community.slug,
            {item["slug"] for item in self.client.get(reverse("community-list")).data["results"]},
        )

        self.client.force_authenticate(user=self.user)
        response = self.client.post(
            reverse("community-join-requests", args=[private_community.slug]),
            {"user_id": applicant.pk, "decision": "approve"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(private_community.members.filter(pk=applicant.pk).exists())

    def test_comment_and_reply_can_be_created_without_images(self):
        post = Post.objects.create(
            community=self.community,
            author=self.user,
            post_type="question",
            title="Question",
            content="How does this work?",
        )

        comment_response = self.client.post(
            reverse("comment-list"),
            {"post": post.pk, "content": "Here is an answer."},
            format="json",
        )
        self.assertEqual(comment_response.status_code, status.HTTP_201_CREATED)
        self.assertIsNone(comment_response.data["image"])
        comment = Comment.objects.get()
        self.assertEqual(comment.author, self.user)
        self.assertFalse(comment.image)

        reply_response = self.client.post(
            reverse("reply-list"),
            {"comment": comment.pk, "content": "Thanks for explaining."},
            format="json",
        )
        self.assertEqual(reply_response.status_code, status.HTTP_201_CREATED)
        self.assertIsNone(reply_response.data["image"])
        reply = Reply.objects.get()
        self.assertEqual(reply.author, self.user)
        self.assertFalse(reply.image)

    def test_nested_replies_and_votes_work(self):
        post = Post.objects.create(
            community=self.community,
            author=self.user,
            post_type="discussion",
            title="Thread",
            content="Thread content",
        )
        comment = Comment.objects.create(
            post=post,
            author=self.user,
            content="Root comment",
        )
        parent = Reply.objects.create(
            comment=comment,
            author=self.user,
            content="First reply",
        )
        child = Reply.objects.create(
            comment=comment,
            parent_reply=parent,
            author=self.user,
            content="Nested reply",
        )

        response = self.client.post(
            reverse("comment-vote", args=[comment.pk]),
            {"value": -1},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["downvotes"], 1)

        response = self.client.post(
            reverse("reply-vote", args=[child.pk]),
            {"value": 1},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["score"], 1)

        comment_response = self.client.get(
            reverse("comment-detail", args=[comment.pk])
        )
        self.assertEqual(
            comment_response.data["replies"][0]["replies"][0]["id"],
            child.pk,
        )

        cycle_response = self.client.patch(
            reverse("reply-detail", args=[parent.pk]),
            {"parent_reply": child.pk},
            format="json",
        )
        self.assertEqual(cycle_response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_community_moderator_can_remove_another_users_post(self):
        moderator = User.objects.create_user(username="assigned-moderator")
        author = User.objects.create_user(username="post-author")
        self.community.members.add(moderator)
        self.community.moderators.add(moderator)
        post = Post.objects.create(
            community=self.community,
            author=author,
            post_type="discussion",
            title="Moderated post",
            content="This post can be removed by a moderator.",
        )
        self.client.force_authenticate(user=moderator)

        response = self.client.delete(reverse("post-detail", args=[post.slug]))

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Post.objects.filter(pk=post.pk).exists())

    def test_community_owner_can_assign_only_a_member_as_moderator(self):
        member = User.objects.create_user(username="community-member")
        nonmember = User.objects.create_user(username="nonmember")
        self.community.members.add(member)

        response = self.client.post(
            reverse("community-moderators", args=[self.community.slug]),
            {"user_id": member.pk},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(self.community.moderators.filter(pk=member.pk).exists())

        response = self.client.post(
            reverse("community-moderators", args=[self.community.slug]),
            {"user_id": nonmember.pk},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(self.community.moderators.filter(pk=nonmember.pk).exists())

        self.client.force_authenticate(user=member)
        response = self.client.post(
            reverse("community-leave", args=[self.community.slug]),
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(self.community.moderators.filter(pk=member.pk).exists())
