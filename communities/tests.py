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
