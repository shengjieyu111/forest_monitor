from datetime import date

from django.test import TestCase
from django.urls import reverse

from mapreduce_app.models import (
    DailyComfortStat,
    DailyRiskStat,
    DailyWeatherStat,
    HourlyWeatherProfile,
    MapReduceSyncLog,
    TopRiskDay,
)


class DashboardViewsTests(TestCase):
    def setUp(self):
        for day in range(2, 9):
            stat_date = date(2026, 6, day)
            DailyWeatherStat.objects.create(
                date=stat_date,
                temperature_avg=22 + day / 2,
                temperature_peak=25 + day / 2,
                humidity_avg=78 - day,
                humidity_peak=88 - day / 2,
                pm25_avg=30 + day,
                pm25_peak=45 + day,
                illumination_avg=22000 + day * 100,
                illumination_peak=81000 + day * 100,
                risk_warning='火灾预警' if day >= 7 else '正常',
            )
            DailyRiskStat.objects.create(
                date=stat_date,
                sample_count=288,
                high_temp_count=day,
                high_humidity_count=2,
                pollution_count=day * 2,
                fire_risk_count=1 if day >= 7 else 0,
                normal_count=250,
                risk_rate=13.19,
            )
            DailyComfortStat.objects.create(
                date=stat_date,
                sample_count=288,
                comfort_index_avg=23,
                comfortable_count=250,
                attention_count=30,
                uncomfortable_count=8,
                comfort_rate=86.81,
            )

        for hour in range(24):
            HourlyWeatherProfile.objects.create(
                hour=hour,
                sample_count=84,
                temperature_avg=20 + hour / 3,
                humidity_avg=80 - hour / 2,
                pm25_avg=35 + hour / 5,
                illumination_avg=max(0, 80000 - abs(12 - hour) * 8000),
            )

        MapReduceSyncLog.objects.create(
            job_type='comfort',
            source_path='/waether/comfort_output/part-r-00000',
            record_count=7,
            status='success',
        )
        TopRiskDay.objects.create(
            rank=1,
            date=date(2026, 6, 8),
            risk_score=18.25,
            dangerous_count=42,
            temperature_peak=35.2,
            humidity_low=41.3,
            pm25_peak=88,
            illumination_peak=90200,
        )

    def test_dashboard_page_renders(self):
        response = self.client.get(reverse('visual_app:dashboard'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '森林环境监测中心')
        self.assertContains(response, 'riskTrendChart')
        self.assertContains(response, 'comfortTrendChart')
        self.assertNotContains(response, 'hdfsUploadForm')

    def test_hdfs_console_page_renders_separately(self):
        response = self.client.get(reverse('visual_app:hdfs-console'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'hdfsUploadForm')
        self.assertContains(response, 'HDFS 文件与 MapReduce 作业控制台')

    def test_dashboard_api_returns_database_results(self):
        response = self.client.get(reverse('visual_app:dashboard-data'))
        payload = response.json()

        self.assertEqual(response.status_code, 200)
        self.assertFalse(payload['empty'])
        self.assertEqual(payload['source']['mode'], 'database')
        self.assertEqual(payload['meta']['record_count'], 7)
        self.assertEqual(len(payload['hourly']), 24)
        self.assertEqual(len(payload['risk_detail']), 7)
        self.assertEqual(len(payload['comfort_detail']), 7)
        self.assertEqual(len(payload['topn']), 1)

    def test_dashboard_api_supports_date_filter(self):
        response = self.client.get(
            reverse('visual_app:dashboard-data'),
            {'start_date': '2026-06-03', 'end_date': '2026-06-03'},
        )
        payload = response.json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload['meta']['start_date'], '2026-06-03')
        self.assertEqual(payload['meta']['end_date'], '2026-06-03')
        self.assertEqual(len(payload['daily']), 1)

    def test_records_api_supports_pagination_and_risk_filter(self):
        response = self.client.get(
            reverse('visual_app:records-data'),
            {'page': 1, 'page_size': 5, 'risk': '中风险'},
        )
        payload = response.json()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(payload['results'])
        self.assertTrue(all(item['risk'] == '中风险' for item in payload['results']))
