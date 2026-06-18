from django.urls import path

from . import views

app_name = "visitor"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("api/records/", views.visitor_record_list_api, name="record-list-api"),
    path("api/daily/", views.visitor_daily_stat_api, name="daily-stat-api"),
    path("api/hourly/", views.visitor_hourly_stat_api, name="hourly-stat-api"),
    path("api/gates/", views.visitor_gate_stat_api, name="gate-stat-api"),
    path(
        "api/peak-warning/",
        views.peak_warning_api,
        name="peak-warning-api",
    ),
    path("run-mr/import/", views.run_all_mr_and_import_api, name="run-mr-import-api"),
    path("run-mr/status/", views.visitor_mr_status_api, name="run-mr-status-api"),
]
