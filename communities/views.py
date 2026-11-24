from django.http import Http404
from django.db import transaction
from django.db.models import Q
from rest_framework import permissions, serializers, status, viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import Community, CommunityJoinRequest
from .serializers import CommunitySerializer
from notifications.models import Notification
from notifications.services import create_notification


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def debug_auth(request):
    return Response({
        "user": str(request.user),
        "auth": str(request.auth_token),
    })


class IsCommunityOwnerOrReadOnly(permissions.BasePermission):
    def has_object_permission(self, request, view, obj):
        if request.method in permissions.SAFE_METHODS:
            return True
        if getattr(view, "action", None) in {"join", "leave", "join_requests"}:
            return True
        return obj.owner_id == request.user.id


class CommunityViewSet(viewsets.ModelViewSet):
    queryset = Community.objects.select_related("owner").prefetch_related(
        "members",
    )
    serializer_class = CommunitySerializer
    lookup_field = "slug"
    permission_classes = [
        permissions.IsAuthenticatedOrReadOnly,
        IsCommunityOwnerOrReadOnly,
    ]

    def get_queryset(self):
        queryset = super().get_queryset()
        if getattr(self, "action", None) in {"join", "join_requests"}:
            return queryset
        if not self.request.user.is_authenticated:
            return queryset.filter(visibility="public")
        return queryset.filter(
            Q(visibility="public") | Q(members=self.request.user)
        ).distinct()

    def get_object(self):
        lookup_url_kwarg = self.lookup_url_kwarg or self.lookup_field
        slug_from_url = self.kwargs.get(lookup_url_kwarg)
        queryset = self.filter_queryset(self.get_queryset())
        community_url = slug_from_url
        if not community_url.startswith("c/"):
            community_url = f"c/{community_url}"
        community = queryset.filter(community_url=community_url).first()
        if community is None:
            community = queryset.filter(
                community_url=f"c/{slug_from_url.lower()}"
            ).first()
        if community is None:
            raise Http404(f"No community found with slug: {slug_from_url}")
        self.check_object_permissions(self.request, community)
        return community

    @action(detail=False, methods=["get"])
    def my_communities(self, request):
        communities = self.get_queryset().filter(owner=request.user)
        serializer = self.get_serializer(communities, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=["post"])
    def join(self, request, slug=None):
        community = self.get_object()
        user = request.user

        if community.members.filter(pk=user.pk).exists():
            return Response(
                {"detail": "User is already a member of this community."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if community.join_policy == "approval":
            join_request, created = CommunityJoinRequest.objects.get_or_create(
                community=community,
                user=user,
                defaults={"status": CommunityJoinRequest.PENDING},
            )
            if join_request.status != CommunityJoinRequest.PENDING:
                join_request.status = CommunityJoinRequest.PENDING
                join_request.save(update_fields=["status", "updated_at"])
                created = True
            if created:
                moderators = community.moderators.all()
                recipients = {community.owner_id: community.owner}
                recipients.update({moderator.pk: moderator for moderator in moderators})
                for recipient in recipients.values():
                    create_notification(
                        recipient=recipient,
                        actor=user,
                        notification_type=Notification.COMMUNITY_JOIN_REQUEST,
                        message=f"{user.username} requested to join {community.name}.",
                        target=join_request,
                    )
            return Response(
                {"detail": "Membership request submitted.", "status": join_request.status},
                status=status.HTTP_202_ACCEPTED,
            )

        community.members.add(user)
        community.member_count = community.members.count()
        community.save(update_fields=["member_count"])
        return Response(
            {"detail": "Successfully joined the community."},
            status=status.HTTP_200_OK,
        )

    @action(detail=True, methods=["get", "post"])
    def join_requests(self, request, slug=None):
        community = self.get_object()
        if (
            community.owner_id != request.user.pk
            and not community.moderators.filter(pk=request.user.pk).exists()
        ):
            return Response(
                {"detail": "Only the owner or a moderator can manage join requests."},
                status=status.HTTP_403_FORBIDDEN,
            )

        if request.method == "GET":
            pending_requests = community.join_requests.filter(
                status=CommunityJoinRequest.PENDING
            ).select_related("user")
            data = [
                {
                    "id": join_request.pk,
                    "user_id": join_request.user_id,
                    "username": join_request.user.username,
                    "created_at": join_request.created_at,
                }
                for join_request in pending_requests
            ]
            return Response(data)

        user_id = request.data.get("user_id")
        decision = request.data.get("decision")
        if not user_id or decision not in {"approve", "reject"}:
            raise serializers.ValidationError({
                "detail": "Provide user_id and decision ('approve' or 'reject')."
            })

        try:
            join_request = community.join_requests.get(
                user_id=user_id,
                status=CommunityJoinRequest.PENDING,
            )
        except CommunityJoinRequest.DoesNotExist:
            return Response(
                {"detail": "No pending membership request exists for that user."},
                status=status.HTTP_404_NOT_FOUND,
            )

        with transaction.atomic():
            if decision == "approve":
                community.members.add(join_request.user)
                community.member_count = community.members.count()
                community.save(update_fields=["member_count"])
                join_request.status = CommunityJoinRequest.APPROVED
            else:
                join_request.status = CommunityJoinRequest.REJECTED
            join_request.save(update_fields=["status", "updated_at"])
            decision_text = "approved" if decision == "approve" else "rejected"
            create_notification(
                recipient=join_request.user,
                actor=request.user,
                notification_type=Notification.JOIN_REQUEST_DECISION,
                message=f"Your request to join {community.name} was {decision_text}.",
                target=community,
            )
        return Response({"status": join_request.status})

    @action(detail=True, methods=["post"])
    def leave(self, request, slug=None):
        community = self.get_object()
        user = request.user

        if not community.members.filter(pk=user.pk).exists():
            return Response(
                {"detail": "User is not a member of this community."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if user == community.owner:
            return Response(
                {"detail": "Owner cannot leave the community. Transfer ownership first."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        community.moderators.remove(user)
        community.members.remove(user)
        community.member_count = community.members.count()
        community.save(update_fields=["member_count"])
        return Response(
            {"detail": "Successfully left the community."},
            status=status.HTTP_200_OK,
        )

    @action(detail=True, methods=["post"], url_path="transfer-ownership")
    def transfer_ownership(self, request, slug=None):
        community = self.get_object()
        user_id = request.data.get("user_id")
        if not user_id:
            return Response(
                {"detail": "user_id is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user_id = serializers.IntegerField(min_value=1).run_validation(user_id)
        new_owner = community.members.filter(pk=user_id).first()
        if new_owner is None:
            return Response(
                {"detail": "Ownership can only be transferred to a community member."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if new_owner.pk == community.owner_id:
            return Response(
                {"detail": "This user is already the community owner."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        with transaction.atomic():
            community.owner = new_owner
            community.save(update_fields=["owner"])
            community.moderators.remove(request.user)
            community.moderators.add(new_owner)

        return Response(self.get_serializer(community).data)

    @action(detail=True, methods=["post", "delete"])
    def moderators(self, request, slug=None):
        community = self.get_object()
        user_id = request.data.get("user_id")
        if not user_id:
            return Response(
                {"detail": "user_id is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if request.method == "POST":
            if not community.members.filter(pk=user_id).exists():
                return Response(
                    {"detail": "Moderators must be community members."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            community.moderators.add(community.members.get(pk=user_id))
            return Response(self.get_serializer(community).data)

        moderator = community.moderators.filter(pk=user_id).first()
        if moderator is None:
            return Response(
                {"detail": "User is not a moderator of this community."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        community.moderators.remove(moderator)
        return Response(status=status.HTTP_204_NO_CONTENT)
