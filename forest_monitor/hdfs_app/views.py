import json
import shlex
from datetime import datetime, time, timedelta
from pathlib import Path

from django.core.files.base import File
from django.http import JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from mapreduce_app.hdfs_sync import sync_all_results
from visitor.models import VisitorRecord
from visitor.services import (
    HDFS_INPUT_PATH,
    REMOTE_DATASET_DIR,
    _upload_local_file,
    import_visitor_records_for_date,
    run_ssh_command,
    upload_visitor_csv_to_hdfs_remote,
)

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


UPLOAD_DIR = Path(__file__).resolve().parents[1] / 'datasets' / 'upload_date'


def _validate_date_str(date_str):
    try:
        parsed_date = datetime.strptime(date_str, '%Y-%m-%d')
    except (TypeError, ValueError) as exc:
        raise ValueError('日期必须使用 YYYY-MM-DD 格式。') from exc
    if parsed_date.strftime('%Y-%m-%d') != date_str:
        raise ValueError('日期必须使用 YYYY-MM-DD 格式。')
    return date_str


def _save_uploaded_csv(uploaded_file, date_str):
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    local_path = UPLOAD_DIR / f'visitor_records_{date_str}.csv'
    with local_path.open('wb') as target:
        for chunk in uploaded_file.chunks():
            target.write(chunk)
    return local_path


def _hdfs_date_dir(date_str):
    return f'{HDFS_INPUT_PATH}/date={_validate_date_str(date_str)}'


def _run_shell(command):
    result = run_ssh_command(f'bash -lc {shlex.quote(command)}')
    return result.stdout


def _preview_hdfs_file(date_str, tail=False):
    hdfs_file = f'{_hdfs_date_dir(date_str)}/visitor_records.csv'
    if not tail:
        return preview_hdfs(hdfs_file)
    pipe = 'tail -20' if tail else 'head -20'
    return _run_shell(f'hdfs dfs -cat {shlex.quote(hdfs_file)} | {pipe}')


def _delete_hdfs_date(date_str):
    delete_hdfs(_hdfs_date_dir(date_str), recursive=True)
    return f'已删除 {_hdfs_date_dir(date_str)}'


def _upload_hdfs_date(local_path, date_str):
    hdfs_dir = _hdfs_date_dir(date_str)
    hdfs_file = f'{hdfs_dir}/visitor_records.csv'
    with Path(local_path).open('rb') as source:
        hdfs_file_obj = File(source, name='visitor_records.csv')
        upload_hdfs(hdfs_file_obj, hdfs_dir, overwrite=True)
    return f'已上传到 {hdfs_file}'


def _format_hdfs_listing(path):
    listing = list_hdfs(path)
    lines = []
    for item in listing['items']:
        prefix = 'd' if item['type'] == 'directory' else '-'
        modified = datetime.fromtimestamp(item['modification_time'] / 1000).strftime(
            '%Y-%m-%d %H:%M'
        )
        lines.append(
            f"{prefix} {item['permission']} {item['owner']} "
            f"{item['length']:>10} {modified} {item['path']}"
        )
    return '\n'.join(lines)


def hdfs_index(request):
    message = ''
    message_type = ''
    preview_text = ''
    selected_date = ''
    file_list = ''
    should_list = False

    if request.method == 'POST':
        action = request.POST.get('action', '')
        try:
            if action == 'upload_history':
                detail = upload_visitor_csv_to_hdfs_remote()
                message = (
                    f"历史游客数据已按日期分区上传到 {detail['hdfs_path']}。\n"
                    f"来源：{detail['source_csv']}\n"
                    f"日期范围：{detail['date_start']} 至 {detail['date_end']}\n"
                    f"分区数：{detail['partition_count']}，数据行：{detail['total_rows']}"
                )
                message_type = 'success'
                should_list = True
            elif action == 'preview_history':
                source = Path(__file__).resolve().parents[1] / 'datasets' / 'visitor_records.csv'
                preview_text = ''.join(source.open('r', encoding='utf-8-sig').readlines()[:20])
                message = '历史数据前 20 行加载成功。'
                message_type = 'success'
            elif action == 'upload_by_date':
                selected_date = _validate_date_str(request.POST.get('date_str', ''))
                uploaded_file = request.FILES.get('csv_file')
                if uploaded_file is None:
                    raise ValueError('请选择需要上传的 CSV 文件。')
                if Path(uploaded_file.name).suffix.lower() != '.csv':
                    raise ValueError('只能上传 .csv 文件。')
                local_path = _save_uploaded_csv(uploaded_file, selected_date)
                detail = _upload_hdfs_date(local_path, selected_date)
                import_result = import_visitor_records_for_date(local_path, selected_date)
                message = (
                    f'已上传 {selected_date} 游客数据到 HDFS 日期分区，'
                    f'并同步 {import_result.imported_rows} 条记录到 MySQL。\n{detail}'
                )
                message_type = 'success'
                should_list = True
            elif action in {'preview_by_date', 'preview_tail_by_date'}:
                selected_date = _validate_date_str(request.POST.get('preview_date', ''))
                preview_text = _preview_hdfs_file(
                    selected_date,
                    tail=action == 'preview_tail_by_date',
                )
                message = f'{selected_date} 数据预览加载成功。'
                message_type = 'success'
            elif action == 'delete_by_date':
                selected_date = _validate_date_str(request.POST.get('delete_date', ''))
                detail = _delete_hdfs_date(selected_date)
                target_date = datetime.strptime(selected_date, '%Y-%m-%d').date()
                day_start = timezone.make_aware(datetime.combine(target_date, time.min))
                day_end = day_start + timedelta(days=1)
                records = VisitorRecord.objects.filter(
                    visit_time__gte=day_start,
                    visit_time__lt=day_end,
                )
                deleted_rows = records.count()
                records.delete()
                message = (
                    f'已删除 {selected_date} HDFS 日期分区，'
                    f'并同步删除 MySQL 中 {deleted_rows} 条游客记录。\n{detail}'
                )
                message_type = 'success'
                should_list = True
            elif action == 'list':
                should_list = True
        except Exception as exc:
            message = str(exc)
            message_type = 'error'

    if should_list:
        try:
            file_list = _format_hdfs_listing(HDFS_INPUT_PATH)
        except Exception as exc:
            if not message:
                message = str(exc)
                message_type = 'error'

    return render(
        request,
        'hdfs/index.html',
        {
            'message': message,
            'message_type': message_type,
            'file_list': file_list,
            'preview_text': preview_text,
            'selected_date': selected_date,
            'hdfs_directory': HDFS_INPUT_PATH,
            'hdfs_history_file': str(Path(__file__).resolve().parents[1] / 'datasets' / 'visitor_records.csv'),
        },
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
