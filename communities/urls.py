from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import CommunityViewSet, debug_auth

router = DefaultRouter()
router.register(r"communities", CommunityViewSet)

urlpatterns = [
    path("", include(router.urls)),
    path("debug-auth/", debug_auth, name="debug-auth"),
]
