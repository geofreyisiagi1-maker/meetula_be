from django.urls import path
from .views import (
    CurrentUserView,
    GoogleLoginCompleteView,
    GoogleTokenExchangeView,
    LoginView,
    LogoutView,
    PublicProfileView,
    SignupView,
)

urlpatterns = [
    path('auth/signup/', SignupView.as_view(), name='auth-signup'),
    path('auth/login/', LoginView.as_view(), name='auth-login'),
    path('auth/logout/', LogoutView.as_view(), name='auth-logout'),
    path('auth/me/', CurrentUserView.as_view(), name='auth-me'),
    path('profiles/<str:username>/', PublicProfileView.as_view(), name='public-profile'),
    path('auth/google/complete/', GoogleLoginCompleteView.as_view(), name='auth-google-complete'),
    path('auth/google/exchange/', GoogleTokenExchangeView.as_view(), name='auth-google-exchange'),
]