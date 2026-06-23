from django import forms
from django.contrib.auth.forms import AuthenticationForm, PasswordChangeForm, UserCreationForm
from django.contrib.auth.models import User


class StyledAuthenticationForm(AuthenticationForm):
    username = forms.CharField(
        label="用户名",
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "请输入用户名",
                "autocomplete": "username",
            }
        ),
    )
    password = forms.CharField(
        label="密码",
        strip=False,
        widget=forms.PasswordInput(
            attrs={
                "class": "form-control",
                "placeholder": "请输入密码",
                "autocomplete": "current-password",
            }
        ),
    )


class RegisterForm(UserCreationForm):
    first_name = forms.CharField(
        label="真实姓名",
        max_length=150,
        required=False,
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "请输入真实姓名",
            }
        ),
    )
    email = forms.EmailField(
        label="邮箱",
        required=False,
        widget=forms.EmailInput(
            attrs={
                "class": "form-control",
                "placeholder": "请输入邮箱",
                "autocomplete": "email",
            }
        ),
    )

    class Meta:
        model = User
        fields = ("username", "first_name", "email", "password1", "password2")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["username"].label = "用户名"
        self.fields["username"].widget.attrs.update(
            {
                "class": "form-control",
                "placeholder": "请输入用户名",
                "autocomplete": "username",
            }
        )
        self.fields["password1"].label = "密码"
        self.fields["password1"].widget.attrs.update(
            {
                "class": "form-control",
                "placeholder": "请输入密码",
                "autocomplete": "new-password",
            }
        )
        self.fields["password2"].label = "确认密码"
        self.fields["password2"].widget.attrs.update(
            {
                "class": "form-control",
                "placeholder": "请再次输入密码",
                "autocomplete": "new-password",
            }
        )


class ProfileForm(forms.ModelForm):
    first_name = forms.CharField(
        label="真实姓名",
        required=False,
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "请输入真实姓名",
            }
        ),
    )
    email = forms.EmailField(
        label="邮箱",
        required=False,
        widget=forms.EmailInput(
            attrs={
                "class": "form-control",
                "placeholder": "请输入邮箱",
                "autocomplete": "email",
            }
        ),
    )

    class Meta:
        model = User
        fields = ("first_name", "email")


class StyledPasswordChangeForm(PasswordChangeForm):
    old_password = forms.CharField(
        label="当前密码",
        strip=False,
        widget=forms.PasswordInput(
            attrs={
                "class": "form-control",
                "placeholder": "请输入当前密码",
                "autocomplete": "current-password",
            }
        ),
    )
    new_password1 = forms.CharField(
        label="新密码",
        strip=False,
        widget=forms.PasswordInput(
            attrs={
                "class": "form-control",
                "placeholder": "请输入新密码",
                "autocomplete": "new-password",
            }
        ),
    )
    new_password2 = forms.CharField(
        label="确认新密码",
        strip=False,
        widget=forms.PasswordInput(
            attrs={
                "class": "form-control",
                "placeholder": "请再次输入新密码",
                "autocomplete": "new-password",
            }
        ),
    )
