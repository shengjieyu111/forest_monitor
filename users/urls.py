from django.urls import path

from . import views


urlpatterns = [
    path("", views.user_center, name="user_center"),
    path("login/", views.user_login, name="user_login"),
    path("register/", views.user_register, name="user_register"),
    path("logout/", views.user_logout, name="user_logout"),
    path("profile/", views.profile, name="profile"),
    path("profile/edit/", views.profile_edit, name="profile_edit"),
    path("password/", views.password_change, name="password_change"),
]
