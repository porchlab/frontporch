"""URL configuration for FrontPorch."""

from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path
from directory.forms import ParentAuthenticationForm


urlpatterns = [
    path("", include("directory.urls")),
    path(
        "accounts/login/",
        auth_views.LoginView.as_view(
            template_name="directory/login.html",
            authentication_form=ParentAuthenticationForm,
        ),
        name="login",
    ),
    path("accounts/logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("admin/", admin.site.urls),
]
