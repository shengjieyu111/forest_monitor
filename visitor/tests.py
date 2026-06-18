from datetime import date, datetime
from unittest.mock import Mock, patch

from django.test import TestCase
from django.utils import timezone

from .models import VisitorDailyStat, VisitorGateStat, VisitorHourlyStat


class VisitorApiTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        VisitorDailyStat.objects.create(stat_date=date(2024, 1, 1), total_count=100)
        VisitorHourlyStat.objects.create(hour=10, total_count=200)
        VisitorGateStat.objects.create(gate="东门", total_count=300)

    def test_daily_stat_api(self):
        response = self.client.get("/visitor/api/daily/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["data"]["values"], [100])

    def test_hourly_stat_api(self):
        response = self.client.get("/visitor/api/hourly/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["data"]["peak"]["hour"], "10:00")

    def test_gate_stat_api(self):
        response = self.client.get("/visitor/api/gates/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["data"], [{"name": "东门", "value": 300}])

    def test_peak_warning_api(self):
        response = self.client.get("/visitor/api/peak-warning/")
        payload = response.json()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["code"], 0)
        self.assertEqual(payload["data"]["level"], "normal")
        self.assertEqual(payload["data"]["peak_hour"], "10:00-11:00")

    def test_peak_warning_without_data(self):
        from .services import get_peak_warning

        VisitorDailyStat.objects.all().delete()
        VisitorHourlyStat.objects.all().delete()
        warning = get_peak_warning()
        self.assertEqual(warning["level"], "none")
        self.assertEqual(warning["advice"], "请先运行 MapReduce 统计任务")

    def test_peak_warning_danger_by_ratio(self):
        from .services import get_peak_warning

        VisitorDailyStat.objects.all().delete()
        VisitorHourlyStat.objects.all().delete()
        VisitorDailyStat.objects.bulk_create(
            [
                VisitorDailyStat(stat_date=date(2024, 1, day), total_count=100)
                for day in range(1, 11)
            ]
        )
        VisitorHourlyStat.objects.bulk_create(
            [
                VisitorHourlyStat(hour=8, total_count=1000),
                VisitorHourlyStat(hour=9, total_count=1000),
                VisitorHourlyStat(hour=10, total_count=2000),
            ]
        )
        warning = get_peak_warning()
        self.assertEqual(warning["level"], "danger")
        self.assertEqual(warning["peak_ratio"], 1.5)

    @patch("visitor.views.import_gate_result", return_value=3)
    @patch("visitor.views.import_hourly_result", return_value=11)
    @patch("visitor.views.import_daily_result", return_value=894)
    @patch(
        "visitor.views.import_local_date_partitions",
        return_value={"imported_files": 1, "imported_rows": 396},
    )
    @patch("visitor.views.run_gate_mapreduce_remote", return_value={"jar": "gate"})
    @patch("visitor.views.run_hourly_mapreduce_remote", return_value={"jar": "hourly"})
    @patch("visitor.views.run_daily_mapreduce_remote", return_value={"jar": "daily"})
    @patch("visitor.views.upload_visitor_csv_to_hdfs_remote", return_value={"hdfs_path": "input"})
    @patch("visitor.views.import_visitor_records_from_csv")
    def test_run_all_mapreduce_and_import_api(
        self,
        import_records,
        upload_csv,
        run_daily,
        run_hourly,
        run_gate,
        import_partitions,
        import_daily,
        import_hourly,
        import_gate,
    ):
        import_records.return_value = Mock(imported_rows=355212, skipped_rows=0)
        response = self.client.post("/visitor/run-mr/import/")
        payload = response.json()
        self.assertEqual(response.status_code, 200)
        self.assertTrue(payload["success"])
        self.assertEqual(len(payload["data"]["steps"]), 8)
        self.assertEqual(payload["data"]["steps"][1]["imported_rows"], 355212)
        self.assertEqual(payload["data"]["steps"][1]["partition_rows"], 396)
        self.assertEqual(payload["data"]["steps"][3]["imported_rows"], 894)

    def test_run_all_mapreduce_requires_post(self):
        response = self.client.get("/visitor/run-mr/import/")
        self.assertEqual(response.status_code, 405)

    @patch("visitor.views.import_gate_result", return_value=3)
    @patch("visitor.views.import_hourly_result", return_value=11)
    @patch("visitor.views.import_daily_result", return_value=894)
    @patch("visitor.views.run_gate_mapreduce_remote", return_value={"jar": "gate"})
    @patch("visitor.views.run_hourly_mapreduce_remote", return_value={"jar": "hourly"})
    @patch("visitor.views.run_daily_mapreduce_remote", return_value={"jar": "daily"})
    @patch("visitor.views.upload_visitor_csv_to_hdfs_remote", return_value={"hdfs_path": "input"})
    @patch("visitor.views.import_local_date_partitions")
    @patch("visitor.views.import_visitor_records_from_csv")
    def test_run_mapreduce_skips_full_raw_import_when_mysql_has_records(
        self,
        import_records,
        import_partitions,
        upload_csv,
        run_daily,
        run_hourly,
        run_gate,
        import_daily,
        import_hourly,
        import_gate,
    ):
        from .models import VisitorRecord

        VisitorRecord.objects.create(
            visit_time=timezone.make_aware(datetime(2026, 6, 15, 8, 0)),
            gate="东门",
            visitor_count=10,
            weather="晴",
            ticket_type="成人票",
        )
        response = self.client.post("/visitor/run-mr/import/")
        raw_step = response.json()["data"]["steps"][1]

        self.assertEqual(response.status_code, 200)
        self.assertTrue(raw_step["skipped"])
        self.assertEqual(raw_step["existing_rows"], 1)
        import_records.assert_not_called()
        import_partitions.assert_not_called()

    @patch("visitor.services._download_remote_file", return_value="result.txt")
    @patch("visitor.services._upload_local_file")
    @patch("visitor.services.run_ssh_command")
    def test_daily_mapreduce_command_contains_main_class(
        self, run_command, upload, download
    ):
        from .services import run_daily_mapreduce_remote

        run_command.return_value = Mock(exit_status=0, stdout="ok")
        run_daily_mapreduce_remote()
        command = run_command.call_args.args[0]
        self.assertIn("VisitorDailyCount", command)
        self.assertIn("visitor-daily-count.jar", command)
        self.assertIn("/forest/visitor/input", command)
        self.assertNotIn("/forest/visitor/input/visitor_records.csv", command)
        self.assertIn("hdfs dfs -rm -r -f /forest/visitor/output/daily", command)

    @patch("visitor.services._download_remote_file", return_value="result.txt")
    @patch("visitor.services._upload_local_file")
    @patch("visitor.services.run_ssh_command")
    def test_hourly_mapreduce_uses_partition_root(
        self, run_command, upload, download
    ):
        from .services import run_hourly_mapreduce_remote

        run_command.return_value = Mock(exit_status=0, stdout="ok")
        run_hourly_mapreduce_remote()
        command = run_command.call_args.args[0]
        self.assertIn("VisitorHourlyCount", command)
        self.assertIn("/forest/visitor/input", command)
        self.assertNotIn("/forest/visitor/input/visitor_records.csv", command)
        self.assertIn("hdfs dfs -rm -r -f /forest/visitor/output/hourly", command)

    @patch("visitor.services._download_remote_file", return_value="result.txt")
    @patch("visitor.services._upload_local_file")
    @patch("visitor.services.run_ssh_command")
    def test_gate_mapreduce_uses_partition_root(
        self, run_command, upload, download
    ):
        from .services import run_gate_mapreduce_remote

        run_command.return_value = Mock(exit_status=0, stdout="ok")
        run_gate_mapreduce_remote()
        command = run_command.call_args.args[0]
        self.assertIn("VisitorGateCount", command)
        self.assertIn("/forest/visitor/input", command)
        self.assertNotIn("/forest/visitor/input/visitor_records.csv", command)
        self.assertIn("hdfs dfs -rm -r -f /forest/visitor/output/gate", command)
