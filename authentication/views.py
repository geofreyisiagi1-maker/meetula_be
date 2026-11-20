from rest_framework.exceptions import AuthenticationFailed
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny
from rest_framework import status
from .auth import ClerkAuthentication


class VerifyTokenView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = [ClerkAuthentication]

    def handle_exception(self, exc):
        if isinstance(exc, AuthenticationFailed):
            return Response({"valid": False}, status=status.HTTP_401_UNAUTHORIZED)
        return super().handle_exception(exc)

    def post(self, request):
        if not request.user.is_authenticated:
            return Response({"valid": False}, status=status.HTTP_401_UNAUTHORIZED)

        return Response({
            "valid": True,
            "clerk_id": request.user.username,
        })
