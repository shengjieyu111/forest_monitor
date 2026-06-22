from django.urls import path
from . import views

app_name = 'wildlife_model'

urlpatterns = [
    path('', views.wildlife_page, name='wildlife-page'),
]
