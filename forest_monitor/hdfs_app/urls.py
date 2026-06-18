from django.urls import path

from . import views


app_name = 'hdfs_app'

urlpatterns = [
    path('', views.hdfs_index, name='index'),
    path('files/', views.files, name='files'),
    path('upload/', views.upload, name='upload'),
    path('delete/', views.delete, name='delete'),
    path('preview/', views.preview, name='preview'),
    path('jobs/start/', views.start_job, name='start-job'),
    path('jobs/status/', views.job_status, name='job-status'),
    path('sync/', views.sync_results, name='sync-results'),
]
