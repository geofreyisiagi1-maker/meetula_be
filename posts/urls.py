from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import CommentViewSet, PostViewSet, ReplyViewSet

router = DefaultRouter()
router.register(r"posts", PostViewSet)
router.register(r"comments", CommentViewSet)
router.register(r"replies", ReplyViewSet)

urlpatterns = [
    path("", include(router.urls)),
]
