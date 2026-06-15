from django.urls import path

from . import views

app_name = 'visual_app'

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('api/dashboard/', views.dashboard_data, name='dashboard-data'),
    path('api/records/', views.records_data, name='records-data'),
]
