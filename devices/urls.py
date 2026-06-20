from django.urls import path
from . import views

urlpatterns = [
    path("", views.devices_dashboard, name="dashboard"),

    path("api/overview/", views.DeviceOverviewView.as_view()),
    path("api/device/map/", views.DeviceMapView.as_view()),
    path("api/device/7day/", views.DeviceSevenDayView.as_view()),
    path("api/faults/", views.FaultTypeView.as_view()),
    path("api/location/", views.FaultTimeRegionView.as_view()),
    path("api/low-health/", views.RegionLowHealthView.as_view()),
    path("api/worst-health/", views.WorstHealthView.as_view()),
    path("api/device/work/", views.DeviceWorkView.as_view()),
    path("api/run-analysis/", views.RunAnalysisView.as_view()),
]