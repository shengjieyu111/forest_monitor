from django.contrib.auth.models import User
from django.test import TestCase


class UserFeatureTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            username="tester",
            password="OldPassword123",
            email="old@example.com",
            first_name="旧姓名",
        )
        cls.admin_user = User.objects.create_user(
            username="admin_user",
            password="AdminPassword123",
            email="admin@example.com",
            first_name="管理员",
            is_staff=True,
        )

    def test_login_page_renders(self):
        response = self.client.get("/users/login/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "用户登录")

    def test_login_with_valid_credentials_redirects_home(self):
        response = self.client.post(
            "/users/login/",
            {"username": "tester", "password": "OldPassword123"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/")

    def test_profile_requires_login(self):
        response = self.client.get("/users/profile/")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/users/login/", response.url)

    def test_profile_page_renders_for_logged_in_user(self):
        self.client.login(username="tester", password="OldPassword123")
        response = self.client.get("/users/profile/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "个人信息")
        self.assertContains(response, "tester")

    def test_profile_edit_updates_existing_user_fields(self):
        self.client.login(username="tester", password="OldPassword123")
        response = self.client.post(
            "/users/profile/edit/",
            {
                "first_name": "新姓名",
                "email": "new@example.com",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/users/profile/")

        self.user.refresh_from_db()
        self.assertEqual(self.user.first_name, "新姓名")
        self.assertEqual(self.user.email, "new@example.com")

    def test_password_change_updates_password_hash(self):
        self.client.login(username="tester", password="OldPassword123")
        response = self.client.post(
            "/users/password/",
            {
                "old_password": "OldPassword123",
                "new_password1": "NewPassword456",
                "new_password2": "NewPassword456",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/users/profile/")

        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("NewPassword456"))

    def test_main_home_requires_login(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/users/login/", response.url)

    def test_main_feature_pages_require_login(self):
        protected_paths = ["/weather/", "/devices/", "/visitor/", "/hdfs/"]
        for path in protected_paths:
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 302)
                self.assertIn("/users/login/", response.url)

    def test_non_admin_is_redirected_from_main_feature_pages(self):
        self.client.login(username="tester", password="OldPassword123")
        protected_paths = ["/weather/", "/devices/", "/visitor/", "/hdfs/"]
        for path in protected_paths:
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 302)
                self.assertEqual(response.url, "/users/profile/")

    def test_admin_can_access_main_feature_pages(self):
        self.client.login(username="admin_user", password="AdminPassword123")
        allowed_paths = ["/", "/weather/", "/devices/", "/visitor/", "/hdfs/"]
        for path in allowed_paths:
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 200)

    def test_home_redirects_non_admin_to_profile(self):
        self.client.login(username="tester", password="OldPassword123")
        response = self.client.get("/")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/users/profile/")

    def test_home_shows_module_cards_for_admin(self):
        self.client.login(username="admin_user", password="AdminPassword123")
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "设备情况")
        self.assertContains(response, "HDFS管理")
