"""URL configuration for FrontPorch."""

from django.contrib import admin
from allauth.account import views as account_views
from django.urls import include, path


urlpatterns = [
    path("", include("directory.urls")),
    # Keep the existing template/URL names while allauth owns the login flow.
    path("accounts/login/", account_views.LoginView.as_view(), name="login"),
    path("accounts/logout/", account_views.LogoutView.as_view(), name="logout"),
    path("accounts/", include("allauth.urls")),
    path("admin/", admin.site.urls),
]
