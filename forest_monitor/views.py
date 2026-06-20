from django.shortcuts import render


def index(request):
    """综合首页"""
    return render(request, "forest_monitor/index.html", {"page": "index"})
