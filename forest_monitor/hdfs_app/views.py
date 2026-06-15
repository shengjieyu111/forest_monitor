import json

from django.http import JsonResponse
from django.views.decorators.http import require_GET, require_POST

from mapreduce_app.hdfs_sync import sync_all_results

from .models import MapReduceRun
from .services import (
    clear_hdfs_directory,
    delete_hdfs,
    list_hdfs,
    preview_hdfs,
    reconcile_run,
    start_mapreduce,
    upload_hdfs,
)


def _json_body(request):
    return json.loads(request.body.decode('utf-8') or '{}')


def _run_payload(run):
    return {
        'id': run.pk,
        'status': run.status,
        'message': run.message,
        'auto_refresh': run.auto_refresh,
        'created_at': run.created_at.isoformat(),
        'started_at': run.started_at.isoformat() if run.started_at else None,
        'finished_at': run.finished_at.isoformat() if run.finished_at else None,
        'output_log': run.output_log,
        'process_id': run.process_id,
        'heartbeat_at': run.heartbeat_at.isoformat() if run.heartbeat_at else None,
    }


@require_GET
def files(request):
    try:
        return JsonResponse(
            list_hdfs(request.GET.get('path', '/waether')),
            json_dumps_params={'ensure_ascii': False},
        )
    except Exception as error:
        return JsonResponse({'error': str(error)}, status=503)


@require_POST
def upload(request):
    uploaded_file = request.FILES.get('file')
    if not uploaded_file:
        return JsonResponse({'error': '请选择要上传的文件'}, status=400)
    if uploaded_file.size > 100 * 1024 * 1024:
        return JsonResponse({'error': '文件不能超过 100 MB'}, status=400)
    try:
        target_directory = request.POST.get('path', '/waether/input')
        if request.POST.get('clear_input', 'true') == 'true':
            clear_hdfs_directory(target_directory)
        target = upload_hdfs(
            uploaded_file,
            target_directory,
            overwrite=request.POST.get('overwrite', 'true') == 'true',
        )
        run = None
        if request.POST.get('auto_run', 'false') == 'true':
            run, _ = start_mapreduce(
                auto_refresh=request.POST.get('auto_refresh', 'true') == 'true'
            )
        return JsonResponse({
            'message': f'已上传到 {target}',
            'path': target,
            'job': _run_payload(run) if run else None,
        }, json_dumps_params={'ensure_ascii': False})
    except Exception as error:
        return JsonResponse({'error': str(error)}, status=503)


@require_POST
def delete(request):
    try:
        body = _json_body(request)
        delete_hdfs(body.get('path'), recursive=bool(body.get('recursive')))
        return JsonResponse({'message': '删除成功'})
    except Exception as error:
        return JsonResponse({'error': str(error)}, status=400)


@require_GET
def preview(request):
    try:
        content = preview_hdfs(request.GET.get('path'))
        return JsonResponse({'content': content}, json_dumps_params={'ensure_ascii': False})
    except Exception as error:
        return JsonResponse({'error': str(error)}, status=503)


@require_POST
def start_job(request):
    try:
        body = _json_body(request)
        run, created = start_mapreduce(auto_refresh=body.get('auto_refresh', True))
        return JsonResponse(
            {'created': created, 'job': _run_payload(run)},
            status=202 if created else 409,
            json_dumps_params={'ensure_ascii': False},
        )
    except Exception as error:
        return JsonResponse({'error': str(error)}, status=503)


@require_GET
def job_status(request):
    run_id = request.GET.get('id')
    run = (
        MapReduceRun.objects.filter(pk=run_id).first()
        if run_id
        else MapReduceRun.objects.first()
    )
    run = reconcile_run(run)
    return JsonResponse({'job': _run_payload(run) if run else None})


@require_POST
def sync_results(request):
    try:
        counts = sync_all_results()
        return JsonResponse({'message': '数据库同步完成', 'counts': counts})
    except Exception as error:
        return JsonResponse({'error': str(error)}, status=503)
