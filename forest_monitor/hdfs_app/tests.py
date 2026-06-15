import json
from datetime import timedelta
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import MapReduceRun
from .services import normalize_hdfs_path, reconcile_run


class HdfsPathTests(TestCase):
    def test_path_is_restricted_to_project_root(self):
        self.assertEqual(normalize_hdfs_path('/waether/input'), '/waether/input')
        with self.assertRaises(ValueError):
            normalize_hdfs_path('/user/root')
        with self.assertRaises(ValueError):
            normalize_hdfs_path('/waether/../user/root')


class HdfsApiTests(TestCase):
    @patch('hdfs_app.views.list_hdfs')
    def test_files_api_returns_directory_items(self, list_hdfs):
        list_hdfs.return_value = {
            'path': '/waether/input',
            'parent': '/waether',
            'items': [{'name': 'weather.csv', 'type': 'file'}],
        }

        response = self.client.get(
            reverse('hdfs_app:files'),
            {'path': '/waether/input'},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['items'][0]['name'], 'weather.csv')

    @patch('hdfs_app.views.clear_hdfs_directory')
    @patch('hdfs_app.views.upload_hdfs')
    def test_upload_api_accepts_csv(self, upload_hdfs, clear_hdfs_directory):
        upload_hdfs.return_value = '/waether/input/weather.csv'
        upload = SimpleUploadedFile(
            'weather.csv',
            b'city,date,hour,temperature,humidity,pm25,illumination\n',
            content_type='text/csv',
        )

        response = self.client.post(
            reverse('hdfs_app:upload'),
            {'file': upload, 'auto_run': 'false'},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['path'], '/waether/input/weather.csv')
        clear_hdfs_directory.assert_called_once_with('/waether/input')

    @patch('hdfs_app.views.delete_hdfs')
    def test_delete_api_calls_hdfs_service(self, delete_hdfs):
        response = self.client.post(
            reverse('hdfs_app:delete'),
            data=json.dumps({'path': '/waether/input/weather.csv'}),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        delete_hdfs.assert_called_once_with(
            '/waether/input/weather.csv',
            recursive=False,
        )

    def test_job_status_returns_latest_run(self):
        run = MapReduceRun.objects.create(status='success', message='done')

        response = self.client.get(reverse('hdfs_app:job-status'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['job']['id'], run.pk)
        self.assertEqual(response.json()['job']['status'], 'success')

    def test_stale_running_job_is_marked_failed(self):
        run = MapReduceRun.objects.create(
            status='running',
            started_at=timezone.now() - timedelta(minutes=5),
            message='running',
        )

        reconcile_run(run)

        run.refresh_from_db()
        self.assertEqual(run.status, 'failed')
        self.assertIn('任务已中断', run.message)
