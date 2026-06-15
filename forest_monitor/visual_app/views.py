from django.http import JsonResponse
from django.shortcuts import render

from .data_service import build_dashboard_payload, build_records_payload


def dashboard(request):
    return render(request, 'visual_app/dashboard.html')


def dashboard_data(request):
    try:
        payload = build_dashboard_payload(
            start_date=request.GET.get('start_date'),
            end_date=request.GET.get('end_date'),
            force=request.GET.get('refresh') == '1',
        )
    except RuntimeError as error:
        return JsonResponse({'empty': True, 'message': str(error)}, status=503)
    return JsonResponse(payload, json_dumps_params={'ensure_ascii': False})


def records_data(request):
    try:
        page = int(request.GET.get('page', 1))
        page_size = min(int(request.GET.get('page_size', 20)), 100)
    except ValueError:
        return JsonResponse({'error': '分页参数必须是整数'}, status=400)

    try:
        payload = build_records_payload(
            page=page,
            page_size=page_size,
            keyword=request.GET.get('keyword', ''),
            risk=request.GET.get('risk', ''),
            start_date=request.GET.get('start_date'),
            end_date=request.GET.get('end_date'),
        )
    except RuntimeError as error:
        return JsonResponse({'error': str(error)}, status=503)
    return JsonResponse(payload, json_dumps_params={'ensure_ascii': False})
