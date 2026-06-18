from django.urls import path

from . import views

app_name = 'ai_app'

urlpatterns = [
    path('wildlife/analyze/', views.wildlife_analyze, name='wildlife-analyze'),
]
