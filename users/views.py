from django.contrib import messages
from django.contrib.auth import login, logout, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render

from .forms import (
    ProfileForm,
    RegisterForm,
    StyledAuthenticationForm,
    StyledPasswordChangeForm,
)


def _role_display(user):
    if user.is_superuser or user.is_staff:
        return "管理员"
    return "普通用户"


def _profile_context(request, profile_form=None, password_form=None):
    return {
        "page": "users",
        "role_display": _role_display(request.user),
        "profile_form": profile_form or ProfileForm(instance=request.user),
        "password_form": password_form or StyledPasswordChangeForm(request.user),
    }


def user_center(request):
    return redirect("profile")


def user_login(request):
    if request.user.is_authenticated:
        return redirect("home")

    next_url = request.GET.get("next") or request.POST.get("next") or "/"
    if request.method == "POST":
        form = StyledAuthenticationForm(request, data=request.POST)
        if form.is_valid():
            login(request, form.get_user())
            messages.success(request, "登录成功。")
            return redirect(next_url)
    else:
        form = StyledAuthenticationForm(request)

    return render(
        request,
        "accounts/login.html",
        {"form": form, "next": next_url},
    )


def user_register(request):
    if request.user.is_authenticated:
        return redirect("home")

    if request.method == "POST":
        form = RegisterForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            messages.success(request, "注册成功，已自动登录。")
            return redirect("home")
    else:
        form = RegisterForm()

    return render(request, "accounts/register.html", {"form": form})


def user_logout(request):
    logout(request)
    messages.info(request, "您已退出登录。")
    return redirect("user_login")


@login_required
def profile(request):
    return render(request, "accounts/profile.html", _profile_context(request))


@login_required
def profile_edit(request):
    if request.method != "POST":
        return redirect("profile")

    profile_form = ProfileForm(request.POST, instance=request.user)
    password_form = StyledPasswordChangeForm(request.user)
    if profile_form.is_valid():
        profile_form.save()
        messages.success(request, "个人信息已更新。")
        return redirect("profile")

    return render(
        request,
        "accounts/profile.html",
        _profile_context(
            request,
            profile_form=profile_form,
            password_form=password_form,
        ),
    )


@login_required
def password_change(request):
    if request.method != "POST":
        return redirect("profile")

    profile_form = ProfileForm(instance=request.user)
    password_form = StyledPasswordChangeForm(request.user, request.POST)
    if password_form.is_valid():
        user = password_form.save()
        update_session_auth_hash(request, user)
        messages.success(request, "密码修改成功。")
        return redirect("profile")

    return render(
        request,
        "accounts/profile.html",
        _profile_context(
            request,
            profile_form=profile_form,
            password_form=password_form,
        ),
    )
