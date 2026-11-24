from io import BytesIO
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from PIL import Image
from rest_framework import status
from rest_framework.test import APIClient

from .serializers import CommunitySerializer
from .models import Community


class CommunityRulesApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(username="rules-owner")
        self.client.force_authenticate(user=self.user)

    def test_create_and_update_custom_rules(self):
        response = self.client.post(
            reverse("community-list"),
            {
                "name": "Food recipes",
                "community_url": "c/food-recipes",
                "description": "Recipes and cooking.",
                "rules": ["Be respectful.", "Stay on topic."],
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["rules"], ["Be respectful.", "Stay on topic."])
        self.assertIn(self.user.pk, [moderator["id"] for moderator in response.data["moderators"]])

        response = self.client.patch(
            reverse("community-detail", args=["food-recipes"]),
            {"rules": ["Be respectful.", "No spam."]},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["rules"], ["Be respectful.", "No spam."])

    def test_create_and_update_community_country(self):
        response = self.client.post(
            reverse("community-list"),
            {
                "name": "Kampala Creatives",
                "community_url": "c/kampala-creatives",
                "description": "Creative people in Kampala.",
                "country": "Uganda",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["country"], "Uganda")

        response = self.client.patch(
            reverse("community-detail", args=["kampala-creatives"]),
            {"country": "Kenya"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["country"], "Kenya")

    def test_multiline_community_description_is_preserved_on_create_and_update(self):
        description = "\nFirst paragraph.\n\nSecond paragraph.\n"
        response = self.client.post(
            reverse("community-list"),
            {
                "name": "Multiline description",
                "community_url": "c/multiline-description",
                "description": description,
            },
            format="multipart",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        community = Community.objects.get(community_url="c/multiline-description")
        self.assertEqual(community.description, description)
        self.assertEqual(response.data["description"], description)

        updated_description = "Updated first paragraph.\n\nUpdated second paragraph."
        response = self.client.patch(
            reverse("community-detail", args=["multiline-description"]),
            {"description": updated_description},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        community.refresh_from_db()
        self.assertEqual(community.description, updated_description)
        self.assertEqual(response.data["description"], updated_description)
        self.assertEqual(
            self.client.get(
                reverse("community-detail", args=["multiline-description"])
            ).data["description"],
            updated_description,
        )

    def test_public_community_can_require_approval_to_join(self):
        response = self.client.post(
            reverse("community-list"),
            {
                "name": "Reviewed community",
                "community_url": "c/reviewed-community",
                "description": "Membership is reviewed.",
                "visibility": "public",
                "join_policy": "approval",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["visibility"], "public")
        self.assertEqual(response.data["join_policy"], "approval")

        member = User.objects.create_user(username="approval-member")
        self.client.force_authenticate(user=member)
        join_response = self.client.post(
            reverse("community-join", args=["reviewed-community"]),
            format="json",
        )

        self.assertEqual(join_response.status_code, status.HTTP_202_ACCEPTED)
        self.assertEqual(join_response.data["status"], "pending")
        community = Community.objects.get(community_url="c/reviewed-community")
        self.assertFalse(community.members.filter(pk=member.pk).exists())

    def test_private_community_defaults_to_approval_for_legacy_clients(self):
        response = self.client.post(
            reverse("community-list"),
            {
                "name": "Private community",
                "community_url": "c/private-community",
                "description": "Members only.",
                "visibility": "private",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["visibility"], "private")
        self.assertEqual(response.data["join_policy"], "approval")

    def test_updating_to_private_defaults_to_approval_for_legacy_clients(self):
        community = Community.objects.create(
            name="Public community",
            community_url="c/public-community",
            description="Changing its visibility.",
            owner=self.user,
        )

        response = self.client.patch(
            reverse("community-detail", args=["public-community"]),
            {"visibility": "private"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["visibility"], "private")
        self.assertEqual(response.data["join_policy"], "approval")
        community.refresh_from_db()
        self.assertEqual(community.join_policy, "approval")

    def test_private_community_cannot_allow_open_joining(self):
        response = self.client.post(
            reverse("community-list"),
            {
                "name": "Invalid private community",
                "community_url": "c/invalid-private-community",
                "description": "Private membership must be approved.",
                "visibility": "private",
                "join_policy": "open",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("join_policy", response.data)

    def test_create_community_accepts_distinct_categories(self):
        for category in ("SPORTS", "NEWS", "CULTURE", "BUSINESS", "ENTERTAINMENT", "LIFESTYLE"):
            with self.subTest(category=category):
                response = self.client.post(
                    reverse("community-list"),
                    {
                        "name": f"{category.title()} community",
                        "community_url": f"c/{category.lower()}-community",
                        "description": "A community with its own category.",
                        "category": category,
                    },
                    format="json",
                )

                self.assertEqual(response.status_code, status.HTTP_201_CREATED)
                self.assertEqual(response.data["category"], category)

    def test_community_country_is_optional(self):
        response = self.client.post(
            reverse("community-list"),
            {
                "name": "Pan-African Creatives",
                "community_url": "c/pan-african-creatives",
                "description": "Creative people across Africa.",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["country"], "")

    def test_create_community_with_multipart_form_fields(self):
        response = self.client.post(
            reverse("community-list"),
            {
                "name": "Kampala Creatives",
                "community_url": "c/kampala-creatives-multipart",
                "description": "Creative people in Kampala.",
                "country": "Uganda",
                "category": "OTHER",
                "visibility": "public",
                "rules[0]": "Be kind.",
                "rules[1]": "Stay on topic.",
            },
            format="multipart",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["country"], "Uganda")
        self.assertEqual(response.data["rules"], ["Be kind.", "Stay on topic."])

    def test_community_image_field_accepts_uploaded_image(self):
        image_data = BytesIO()
        Image.new("RGB", (1, 1)).save(image_data, format="PNG")
        image = SimpleUploadedFile(
            "community.png",
            image_data.getvalue(),
            content_type="image/png",
        )
        with patch("communities.serializers.Community.objects.create") as create:
            community = create.return_value
            community.members.add.return_value = None
            serializer = CommunitySerializer(
                data={
                    "name": "Image community",
                    "community_url": "c/image-community",
                    "description": "A community with an image.",
                    "profile_image": image,
                },
                context={"request": SimpleNamespace(user=self.user)},
            )
            self.assertTrue(serializer.is_valid(), serializer.errors)
            serializer.save()

        self.assertEqual(create.call_args.kwargs["profile_image"].name, "community.png")

    def test_frontend_development_header_is_allowed_by_cors(self):
        response = self.client.options(
            reverse("community-list"),
            HTTP_ORIGIN="http://192.168.1.3:3000",
            HTTP_ACCESS_CONTROL_REQUEST_METHOD="POST",
            HTTP_ACCESS_CONTROL_REQUEST_HEADERS="content-type,x-development-user",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            response["Access-Control-Allow-Origin"],
            "http://192.168.1.3:3000",
        )
        self.assertIn("x-development-user", response["Access-Control-Allow-Headers"])


class CommunityMembershipApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.owner = User.objects.create_user(username="community-owner")
        self.member = User.objects.create_user(username="community-member")
        self.community = Community.objects.create(
            name="Ownership transfer",
            community_url="c/ownership-transfer",
            description="A community for ownership transfer tests.",
            owner=self.owner,
        )
        self.community.members.add(self.owner, self.member)
        self.community.moderators.add(self.owner)
        self.client.force_authenticate(user=self.owner)

    def test_owner_can_transfer_ownership_then_leave(self):
        transfer_response = self.client.post(
            reverse("community-transfer-ownership", args=["ownership-transfer"]),
            {"user_id": self.member.pk},
            format="json",
        )

        self.assertEqual(transfer_response.status_code, status.HTTP_200_OK)
        self.community.refresh_from_db()
        self.assertEqual(self.community.owner_id, self.member.pk)
        self.assertTrue(self.community.moderators.filter(pk=self.member.pk).exists())
        self.assertFalse(self.community.moderators.filter(pk=self.owner.pk).exists())

        leave_response = self.client.post(
            reverse("community-leave", args=["ownership-transfer"]),
            format="json",
        )

        self.assertEqual(leave_response.status_code, status.HTTP_200_OK)
        self.assertFalse(self.community.members.filter(pk=self.owner.pk).exists())

    def test_owner_cannot_leave_before_transferring_ownership(self):
        response = self.client.post(
            reverse("community-leave", args=["ownership-transfer"]),
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertTrue(self.community.members.filter(pk=self.owner.pk).exists())

    def test_ownership_can_only_be_transferred_to_a_member(self):
        non_member = User.objects.create_user(username="non-member")

        response = self.client.post(
            reverse("community-transfer-ownership", args=["ownership-transfer"]),
            {"user_id": non_member.pk},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.community.refresh_from_db()
        self.assertEqual(self.community.owner_id, self.owner.pk)

    def test_only_the_owner_can_transfer_ownership(self):
        self.client.force_authenticate(user=self.member)

        response = self.client.post(
            reverse("community-transfer-ownership", args=["ownership-transfer"]),
            {"user_id": self.owner.pk},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.community.refresh_from_db()
        self.assertEqual(self.community.owner_id, self.owner.pk)
