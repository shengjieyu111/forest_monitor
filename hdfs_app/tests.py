from unittest.mock import patch

from django.test import TestCase


SUCCESS_RESULT = {
    "success": True,
    "stdout": "-rw-r--r-- 1 root supergroup 18 M visitor_records.csv",
    "stderr": "",
    "returncode": 0,
}


class HdfsIndexTests(TestCase):
    @patch("hdfs_app.views.hdfs_list", return_value=SUCCESS_RESULT)
    def test_index_page(self, hdfs_list):
        response = self.client.get("/hdfs/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "HDFS 数据管理")
        self.assertContains(response, "visitor_records.csv")

    @patch("hdfs_app.views.hdfs_list", return_value=SUCCESS_RESULT)
    @patch(
        "hdfs_app.views.hdfs_preview",
        return_value={
            "success": True,
            "stdout": "record_id,visit_time,gate,visitor_count,weather,ticket_type",
            "stderr": "",
            "returncode": 0,
        },
    )
    def test_preview_action(self, hdfs_preview, hdfs_list):
        response = self.client.post("/hdfs/", {"action": "preview"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "record_id,visit_time")

    @patch("hdfs_app.views.hdfs_list", return_value=SUCCESS_RESULT)
    @patch("hdfs_app.views.hdfs_upload", return_value=SUCCESS_RESULT)
    def test_upload_action(self, hdfs_upload, hdfs_list):
        response = self.client.post("/hdfs/", {"action": "upload"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "上传/覆盖文件成功")

    @patch("hdfs_app.views.hdfs_list", return_value=SUCCESS_RESULT)
    @patch("hdfs_app.views.hdfs_delete", return_value=SUCCESS_RESULT)
    def test_delete_action(self, hdfs_delete, hdfs_list):
        response = self.client.post("/hdfs/", {"action": "delete"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "删除文件成功")
