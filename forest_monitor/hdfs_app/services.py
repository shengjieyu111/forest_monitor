import subprocess
import threading
import posixpath
from pathlib import Path, PurePosixPath
from urllib.parse import quote

import requests
import psutil
from django.conf import settings
from django.db import close_old_connections
from django.utils import timezone

from .models import MapReduceRun


HDFS_ROOT = '/waether'


def normalize_hdfs_path(path):
    raw_path = path or HDFS_ROOT
    normalized = posixpath.normpath('/' + str(raw_path).lstrip('/'))
    if normalized != HDFS_ROOT and not normalized.startswith(f'{HDFS_ROOT}/'):
        raise ValueError(f'只允许访问 {HDFS_ROOT} 目录')
    return normalized


def _webhdfs_url(path):
    normalized = normalize_hdfs_path(path)
    return (
        f'http://{settings.HDFS_WEB_HOST}:{settings.HDFS_WEB_PORT}'
        f'/webhdfs/v1{quote(normalized, safe="/")}'
    )


def _request(method, path, **kwargs):
    params = kwargs.pop('params', {})
    params['user.name'] = settings.HDFS_USER
    response = requests.request(
        method,
        _webhdfs_url(path),
        params=params,
        timeout=settings.HDFS_TIMEOUT,
        **kwargs,
    )
    response.raise_for_status()
    return response


def list_hdfs(path=HDFS_ROOT):
    normalized = normalize_hdfs_path(path)
    response = _request('GET', normalized, params={'op': 'LISTSTATUS'})
    statuses = response.json()['FileStatuses']['FileStatus']
    return {
        'path': normalized,
        'parent': (
            str(PurePosixPath(normalized).parent)
            if normalized != HDFS_ROOT
            else None
        ),
        'items': [
            {
                'name': item['pathSuffix'],
                'path': f"{normalized.rstrip('/')}/{item['pathSuffix']}",
                'type': item['type'].lower(),
                'length': item['length'],
                'modification_time': item['modificationTime'],
                'permission': item['permission'],
                'owner': item['owner'],
            }
            for item in statuses
        ],
    }


def upload_hdfs(uploaded_file, directory='/waether/input', overwrite=True):
    directory = normalize_hdfs_path(directory)
    filename = PurePosixPath(str(uploaded_file.name).replace('\\', '/')).name
    if not filename or filename in {'.', '..'}:
        raise ValueError('文件名无效')
    target = f"{directory.rstrip('/')}/{filename}"
    _request('PUT', directory, params={'op': 'MKDIRS'})
    _request(
        'PUT',
        target,
        params={'op': 'CREATE', 'overwrite': str(overwrite).lower()},
        data=uploaded_file.read(),
        allow_redirects=True,
        headers={'Content-Type': 'application/octet-stream'},
    )
    return target


def clear_hdfs_directory(path):
    normalized = normalize_hdfs_path(path)
    if normalized == HDFS_ROOT:
        raise ValueError('禁止清空 HDFS 项目根目录')
    response = _request(
        'DELETE',
        normalized,
        params={'op': 'DELETE', 'recursive': 'true'},
    )
    if not response.json().get('boolean'):
        # The directory may not exist yet; MKDIRS below creates it.
        pass
    _request('PUT', normalized, params={'op': 'MKDIRS'})


def delete_hdfs(path, recursive=False):
    normalized = normalize_hdfs_path(path)
    if normalized == HDFS_ROOT:
        raise ValueError('禁止删除 HDFS 项目根目录')
    response = _request(
        'DELETE',
        normalized,
        params={'op': 'DELETE', 'recursive': str(recursive).lower()},
    )
    if not response.json().get('boolean'):
        raise RuntimeError('HDFS 删除失败')


def preview_hdfs(path, limit=65536):
    normalized = normalize_hdfs_path(path)
    response = _request(
        'GET',
        normalized,
        params={'op': 'OPEN', 'offset': 0, 'length': min(limit, 65536)},
        allow_redirects=True,
    )
    return response.content.decode('utf-8', errors='replace')


def _decode_process_output(data):
    for encoding in ('utf-8', 'gbk'):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode('utf-8', errors='replace')


def _execute_mapreduce(run_id):
    close_old_connections()
    run = MapReduceRun.objects.get(pk=run_id)
    run.status = 'running'
    run.started_at = timezone.now()
    run.heartbeat_at = run.started_at
    run.message = '正在执行 MapReduce 分析'
    run.save(update_fields=['status', 'started_at', 'heartbeat_at', 'message'])

    project_root = Path(settings.BASE_DIR)
    script = project_root / 'sensor' / 'weather' / 'run_analytics.ps1'
    try:
        process = subprocess.Popen(
            [
                'powershell.exe',
                '-NoProfile',
                '-ExecutionPolicy',
                'Bypass',
                '-File',
                str(script),
            ],
            cwd=project_root,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
        )
        run.process_id = process.pid
        run.heartbeat_at = timezone.now()
        run.save(update_fields=['process_id', 'heartbeat_at'])

        output_parts = []
        deadline = timezone.now().timestamp() + settings.MAPREDUCE_TIMEOUT
        while True:
            line = process.stdout.readline()
            if line:
                output_parts.append(_decode_process_output(line))
                output = ''.join(output_parts)[-50000:]
                MapReduceRun.objects.filter(pk=run_id).update(
                    output_log=output,
                    heartbeat_at=timezone.now(),
                )
            if process.poll() is not None:
                break
            if timezone.now().timestamp() > deadline:
                process.kill()
                raise subprocess.TimeoutExpired(process.args, settings.MAPREDUCE_TIMEOUT)

        output = ''.join(output_parts)[-50000:]
        run.refresh_from_db()
        run.output_log = output
        run.finished_at = timezone.now()
        run.process_id = None
        run.heartbeat_at = run.finished_at
        if process.returncode == 0:
            run.status = 'success'
            run.message = '计算完成，结果已同步到 SQLite'
        else:
            run.status = 'failed'
            run.message = f'MapReduce 运行失败，退出码 {process.returncode}'
    except Exception as error:
        run.refresh_from_db()
        run.status = 'failed'
        run.message = str(error)
        run.output_log = f'{run.output_log}\n{error}'.strip()
        run.process_id = None
        run.heartbeat_at = timezone.now()
        run.finished_at = timezone.now()
    run.save(update_fields=[
        'status',
        'message',
        'output_log',
        'process_id',
        'heartbeat_at',
        'finished_at',
    ])
    close_old_connections()


def reconcile_run(run):
    if not run or run.status not in {'queued', 'running'}:
        return run

    process_alive = bool(run.process_id and psutil.pid_exists(run.process_id))
    grace_time = run.started_at or run.created_at
    stale_without_process = (
        not process_alive
        and grace_time
        and (timezone.now() - grace_time).total_seconds() > 120
    )
    if stale_without_process:
        run.status = 'failed'
        run.finished_at = timezone.now()
        run.heartbeat_at = run.finished_at
        run.message = 'Django 服务重启或后台进程已退出，任务已中断，请重新运行'
        run.output_log = (
            f'{run.output_log}\n{run.message}'.strip()
        )
        run.process_id = None
        run.save(update_fields=[
            'status',
            'finished_at',
            'heartbeat_at',
            'message',
            'output_log',
            'process_id',
        ])
    return run


def start_mapreduce(auto_refresh=True):
    active = MapReduceRun.objects.filter(status__in=['queued', 'running']).first()
    active = reconcile_run(active)
    if active and active.status not in {'queued', 'running'}:
        active = None
    if active:
        return active, False
    run = MapReduceRun.objects.create(
        status='queued',
        auto_refresh=auto_refresh,
        message='任务已进入队列',
    )
    thread = threading.Thread(
        target=_execute_mapreduce,
        args=(run.pk,),
        name=f'mapreduce-run-{run.pk}',
        daemon=True,
    )
    thread.start()
    return run, True
