from django.urls import path

from . import views


app_name = "hdfs_app"

urlpatterns = [
    path("", views.hdfs_index, name="index"),
]
