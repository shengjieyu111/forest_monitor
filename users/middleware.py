from django.conf import settings
from django.contrib import messages
from django.shortcuts import redirect


class LoginRequiredMiddleware:
    EXEMPT_PREFIXES = (
        "/users/login/",
        "/users/register/",
        "/users/profile/",
        "/users/password/",
        "/users/logout/",
        "/admin/",
        "/static/",
        "/media/",
        "/favicon.ico",
    )
    ADMIN_ONLY_PREFIXES = (
        "/weather/",
        "/devices/",
        "/visitor/",
        "/hdfs/",
    )

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated or any(
            request.path.startswith(prefix) for prefix in self.EXEMPT_PREFIXES
        ):
            if request.user.is_authenticated and self._requires_admin(request.path):
                if not (request.user.is_staff or request.user.is_superuser):
                    messages.info(request, "当前账号为普通用户，请在个人中心管理账户信息。")
                    return redirect("/users/profile/")
            return self.get_response(request)

        login_url = getattr(settings, "LOGIN_URL", "/users/login/")
        return redirect(f"{login_url}?next={request.get_full_path()}")

    def _requires_admin(self, path):
        return path == "/" or any(
            path.startswith(prefix) for prefix in self.ADMIN_ONLY_PREFIXES
        )
