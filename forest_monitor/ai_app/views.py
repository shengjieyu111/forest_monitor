from django.http import JsonResponse
from django.views.decorators.http import require_POST

from .services.wildlife_ai import analyze_wildlife


@require_POST
def wildlife_analyze(request):
    image = request.FILES.get('image')
    if not image:
        return JsonResponse({'error': '请上传需要识别的野生动物图片'}, status=400, json_dumps_params={'ensure_ascii': False})
    if not image.content_type.startswith('image/'):
        return JsonResponse({'error': '文件类型必须是图片'}, status=400, json_dumps_params={'ensure_ascii': False})
    if image.size > 8 * 1024 * 1024:
        return JsonResponse({'error': '图片不能超过 8 MB'}, status=400, json_dumps_params={'ensure_ascii': False})

    try:
        payload = analyze_wildlife(
            image,
            request.POST.get('mode', 'ensemble'),
            request.POST.get('category', 'auto'),
        )
    except Exception as error:
        return JsonResponse({'error': f'识别失败：{error}'}, status=500, json_dumps_params={'ensure_ascii': False})
    return JsonResponse(payload, json_dumps_params={'ensure_ascii': False})
