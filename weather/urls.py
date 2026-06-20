from django.urls import path

from . import views

app_name = "weather"

urlpatterns = [
    path("", views.weather_dashboard, name="dashboard"),
    path("api/overview/", views.weather_overview_api, name="overview-api"),
    path("api/records/", views.weather_records_api, name="records-api"),
    path("api/daily/", views.weather_daily_stat_api, name="daily-api"),
    path("api/hourly/", views.weather_hourly_stat_api, name="hourly-api"),
    path("api/comfort/", views.weather_comfort_stat_api, name="comfort-api"),
    path("api/risk/", views.weather_risk_stat_api, name="risk-api"),
    path("api/topn/", views.weather_topn_api, name="topn-api"),
    path("api/health-summary/", views.weather_health_summary_api, name="health-summary-api"),
    path("api/run-analysis/", views.run_weather_analysis_api, name="run-analysis-api"),
]