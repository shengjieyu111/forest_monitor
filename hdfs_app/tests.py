from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.utils import timezone

from datetime import datetime
from visitor.models import VisitorRecord

from .services import get_hdfs_date_dir, validate_date_str


SUCCESS_RESULT = {
    "success": True,
    "stdout": (
        "drwxr-xr-x - root supergroup 0 2026-06-15 10:00 "
        "/forest/visitor/input/date=2026-06-15"
    ),
    "stderr": "",
    "returncode": 0,
}


class DatePartitionServiceTests(TestCase):
    def test_get_hdfs_date_dir(self):
        self.assertEqual(
            get_hdfs_date_dir("2026-06-15"),
            "/forest/visitor/input/date=2026-06-15",
        )

    def test_invalid_date_is_rejected(self):
        invalid_dates = ["2026-6-15", "2026-02-30", "2026-06-15;rm -rf /", ""]
        for date_str in invalid_dates:
            with self.subTest(date_str=date_str):
                with self.assertRaises(ValueError):
                    validate_date_str(date_str)


class HdfsIndexTests(TestCase):
    @patch("hdfs_app.views.hdfs_list", return_value=SUCCESS_RESULT)
    def test_get_lists_all_date_partitions(self, hdfs_list):
        response = self.client.get("/hdfs/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "HDFS 日期分区数据管理")
        self.assertContains(response, "date=2026-06-15")
        hdfs_list.assert_called_once()

    @patch("hdfs_app.views.hdfs_list", return_value=SUCCESS_RESULT)
    @patch("hdfs_app.views.hdfs_upload_history", return_value=SUCCESS_RESULT)
    def test_upload_history(self, upload_history, hdfs_list):
        response = self.client.post("/hdfs/", {"action": "upload_history"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "历史游客数据已上传到 HDFS history 目录")
        upload_history.assert_called_once_with()

    @patch("hdfs_app.views.hdfs_list", return_value=SUCCESS_RESULT)
    @patch(
        "hdfs_app.views.hdfs_preview_history",
        return_value={
            "success": True,
            "stdout": "record_id,visit_time,gate,visitor_count,weather,ticket_type",
            "stderr": "",
            "returncode": 0,
        },
    )
    def test_preview_history(self, preview_history, hdfs_list):
        response = self.client.post("/hdfs/", {"action": "preview_history"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "record_id,visit_time")
        preview_history.assert_called_once_with()

    @patch("hdfs_app.views.hdfs_list", return_value=SUCCESS_RESULT)
    @patch("hdfs_app.views.hdfs_upload_by_date", return_value=SUCCESS_RESULT)
    def test_upload_by_date(self, upload_by_date, hdfs_list):
        uploaded_file = SimpleUploadedFile(
            "visitor_today.csv",
            (
                "record_id,visit_time,gate,visitor_count,weather,ticket_type\n"
                "1,2026-06-15 08:00:00,东门,10,晴,成人票\n"
            ).encode("utf-8"),
            content_type="text/csv",
        )
        with TemporaryDirectory() as temp_dir:
            with patch("hdfs_app.views.UPLOAD_DIR", Path(temp_dir)):
                response = self.client.post(
                    "/hdfs/",
                    {
                        "action": "upload_by_date",
                        "date_str": "2026-06-15",
                        "csv_file": uploaded_file,
                    },
                )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "已上传 2026-06-15 游客数据到 HDFS 日期分区")
        local_path, date_str = upload_by_date.call_args.args
        self.assertEqual(local_path.name, "visitor_records_2026-06-15.csv")
        self.assertEqual(date_str, "2026-06-15")

    @patch("hdfs_app.views.hdfs_list", return_value=SUCCESS_RESULT)
    @patch("hdfs_app.views.hdfs_upload_by_date", return_value=SUCCESS_RESULT)
    def test_upload_by_date_without_action_uses_form_fields(
        self, upload_by_date, hdfs_list
    ):
        uploaded_file = SimpleUploadedFile(
            "visitor_today.csv",
            (
                "record_id,visit_time,gate,visitor_count,weather,ticket_type\n"
                "1,2026-06-15 08:00:00,东门,10,晴,成人票\n"
            ).encode("utf-8"),
            content_type="text/csv",
        )
        with TemporaryDirectory() as temp_dir:
            with patch("hdfs_app.views.UPLOAD_DIR", Path(temp_dir)):
                response = self.client.post(
                    "/hdfs/",
                    {
                        "date_str": "2026-06-15",
                        "csv_file": uploaded_file,
                    },
                )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "已上传 2026-06-15 游客数据到 HDFS 日期分区")
        upload_by_date.assert_called_once()

    @patch("hdfs_app.views.hdfs_list", return_value=SUCCESS_RESULT)
    @patch(
        "hdfs_app.views.hdfs_preview_by_date",
        return_value={
            "success": True,
            "stdout": "record_id,visit_time,gate,visitor_count,weather,ticket_type",
            "stderr": "",
            "returncode": 0,
        },
    )
    def test_preview_by_date(self, preview_by_date, hdfs_list):
        response = self.client.post(
            "/hdfs/",
            {"action": "preview_by_date", "preview_date": "2026-06-15"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "record_id,visit_time")
        preview_by_date.assert_called_once_with("2026-06-15")

    @patch("hdfs_app.views.hdfs_list", return_value=SUCCESS_RESULT)
    @patch("hdfs_app.views.hdfs_delete_by_date", return_value=SUCCESS_RESULT)
    def test_delete_by_date(self, delete_by_date, hdfs_list):
        VisitorRecord.objects.create(
            visit_time=timezone.make_aware(datetime(2026, 6, 15, 8, 0)),
            gate="东门",
            visitor_count=10,
            weather="晴",
            ticket_type="成人票",
        )
        with TemporaryDirectory() as temp_dir:
            local_path = Path(temp_dir) / "visitor_records_2026-06-15.csv"
            local_path.write_text("test", encoding="utf-8")
            with patch("hdfs_app.views.UPLOAD_DIR", Path(temp_dir)):
                response = self.client.post(
                    "/hdfs/",
                    {"action": "delete_by_date", "delete_date": "2026-06-15"},
                )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "并同步删除 MySQL 中 1 条游客记录")
        delete_by_date.assert_called_once_with("2026-06-15")
        self.assertFalse(
            VisitorRecord.objects.filter(pk__isnull=False).exists()
        )
        self.assertFalse(local_path.exists())

    @patch("hdfs_app.views.hdfs_list", return_value=SUCCESS_RESULT)
    def test_upload_rejects_non_csv_file(self, hdfs_list):
        uploaded_file = SimpleUploadedFile("data.txt", b"not csv")
        response = self.client.post(
            "/hdfs/",
            {
                "action": "upload_by_date",
                "date_str": "2026-06-15",
                "csv_file": uploaded_file,
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "只能上传 .csv 文件")
