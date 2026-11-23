from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from communities.models import Community
from notifications.models import Notification
from posts.models import Comment, Post, Reply


class NotificationApiTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username="content-owner")
        self.actor = User.objects.create_user(username="interacting-user")
        self.community = Community.objects.create(
            name="Notifications",
            community_url="c/notifications",
            description="Notification test community",
            category="SOCIAL",
            owner=self.owner,
        )
        self.community.members.add(self.actor)
        self.post = Post.objects.create(
            community=self.community,
            author=self.owner,
            post_type="discussion",
            title="Notify me",
            content="Post content",
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.actor)

    def test_comment_and_vote_create_notifications_for_content_author(self):
        response = self.client.post(
            reverse("comment-list"),
            {"post": self.post.pk, "content": "A comment"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(
            Notification.objects.filter(
                recipient=self.owner,
                notification_type=Notification.POST_COMMENT,
            ).exists()
        )

        response = self.client.post(
            reverse("post-vote", args=[self.post.slug]),
            {"value": 1},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            Notification.objects.filter(
                recipient=self.owner,
                notification_type=Notification.POST_VOTE,
            ).count(),
            1,
        )

    def test_replies_and_votes_notify_comment_and_reply_authors(self):
        comment = Comment.objects.create(
            post=self.post,
            author=self.owner,
            content="A comment to reply to",
        )
        response = self.client.post(
            reverse("reply-list"),
            {"comment": comment.pk, "content": "A reply"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        reply = Reply.objects.get()
        self.assertTrue(
            Notification.objects.filter(
                recipient=self.owner,
                notification_type=Notification.COMMENT_REPLY,
            ).exists()
        )

        voter = User.objects.create_user(username="voting-user")
        self.community.members.add(voter)
        self.client.force_authenticate(user=voter)
        self.client.post(
            reverse("comment-vote", args=[comment.pk]),
            {"value": 1},
            format="json",
        )
        self.client.post(
            reverse("reply-vote", args=[reply.pk]),
            {"value": 1},
            format="json",
        )
        self.assertTrue(
            Notification.objects.filter(
                recipient=self.owner,
                notification_type=Notification.COMMENT_VOTE,
            ).exists()
        )
        self.assertTrue(
            Notification.objects.filter(
                recipient=self.actor,
                notification_type=Notification.REPLY_VOTE,
            ).exists()
        )

    def test_nested_reply_notifies_parent_reply_author(self):
        comment = Comment.objects.create(
            post=self.post,
            author=self.actor,
            content="A comment by the actor",
        )
        parent = Reply.objects.create(
            comment=comment,
            author=self.owner,
            content="Parent reply",
        )

        response = self.client.post(
            reverse("reply-list"),
            {
                "comment": comment.pk,
                "parent_reply": parent.pk,
                "content": "A nested reply",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(
            Notification.objects.filter(
                recipient=self.owner,
                notification_type=Notification.REPLY_REPLY,
            ).exists()
        )

        self.client.post(
            reverse("post-vote", args=[self.post.slug]),
            {"value": -1},
            format="json",
        )
        self.assertEqual(
            Notification.objects.filter(
                recipient=self.owner,
                notification_type=Notification.POST_VOTE,
            ).count(),
            1,
        )

    def test_private_join_request_notifies_owner_and_moderator_once(self):
        moderator = User.objects.create_user(username="community-moderator")
        applicant = User.objects.create_user(username="community-applicant")
        self.community.visibility = "private"
        self.community.save(update_fields=["visibility"])
        self.community.members.add(moderator)
        self.community.moderators.add(moderator)
        self.client.force_authenticate(user=applicant)
        join_url = reverse("community-join", args=[self.community.slug])

        response = self.client.post(join_url, format="json")
        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)
        self.client.post(join_url, format="json")

        self.assertEqual(
            Notification.objects.filter(
                notification_type=Notification.COMMUNITY_JOIN_REQUEST,
            ).count(),
            2,
        )
        self.assertEqual(
            set(Notification.objects.values_list("recipient_id", flat=True)),
            {self.owner.pk, moderator.pk},
        )

        self.client.force_authenticate(user=self.owner)
        response = self.client.post(
            reverse("community-join-requests", args=[self.community.slug]),
            {"user_id": applicant.pk, "decision": "approve"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        decision_notification = Notification.objects.get(
            recipient=applicant,
            notification_type=Notification.JOIN_REQUEST_DECISION,
        )
        self.client.force_authenticate(user=applicant)
        notification_response = self.client.get(reverse("notification-list"))
        self.assertEqual(notification_response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            next(
                item["target_url"]
                for item in notification_response.data["results"]
                if item["id"] == decision_notification.pk
            ),
            "/c/notifications",
        )

    def test_notifications_are_private_and_can_be_marked_read(self):
        notification = Notification.objects.create(
            recipient=self.actor,
            actor=self.owner,
            notification_type=Notification.POST_COMMENT,
            message="Someone commented on your post.",
            target=self.post,
        )
        other = User.objects.create_user(username="another-user")
        Notification.objects.create(
            recipient=other,
            notification_type=Notification.POST_COMMENT,
            message="Private to another user.",
        )

        response = self.client.get(reverse("notification-list"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["results"]), 1)
        self.assertEqual(response.data["results"][0]["target_type"], "post")
        self.assertEqual(response.data["results"][0]["target_id"], self.post.pk)
        self.assertEqual(response.data["results"][0]["target_url"], f"/post/{self.post.slug}")

        response = self.client.get(reverse("notification-unread-count"))
        self.assertEqual(response.data["unread_count"], 1)

        response = self.client.post(
            reverse("notification-read", args=[notification.pk]),
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["is_read"])

        response = self.client.post(reverse("notification-read-all"))
        self.assertEqual(response.data["marked_read"], 0)

    def test_comment_and_reply_notifications_link_to_their_post(self):
        comment = Comment.objects.create(
            post=self.post,
            author=self.owner,
            content="A comment",
        )
        reply = Reply.objects.create(
            comment=comment,
            author=self.owner,
            content="A reply",
        )
        comment_notification = Notification.objects.create(
            recipient=self.actor,
            actor=self.owner,
            notification_type=Notification.COMMENT_REPLY,
            message="Someone replied to your comment.",
            target=comment,
        )
        reply_notification = Notification.objects.create(
            recipient=self.actor,
            actor=self.owner,
            notification_type=Notification.REPLY_REPLY,
            message="Someone replied to your reply.",
            target=reply,
        )

        response = self.client.get(reverse("notification-list"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        notifications_by_id = {
            str(item["id"]): item for item in response.data["results"]
        }
        self.assertEqual(
            notifications_by_id[str(comment_notification.pk)]["target_url"],
            f"/post/{self.post.slug}",
        )
        self.assertEqual(
            notifications_by_id[str(reply_notification.pk)]["target_url"],
            f"/post/{self.post.slug}",
        )
