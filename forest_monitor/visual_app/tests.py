from django.test import TestCase
from django.urls import reverse
from unittest.mock import patch

from . import data_service


HDFS_RESULT = """2026-06-02\ttemp_avg=23.50,temp_peak=26.6,humidity_avg=75.91,humidity_peak=88.4,pm25_avg=31.54,pm25_peak=50.0,illumination_avg=22360.37,illumination_peak=81750.8,risk_warning=正常
2026-06-03\ttemp_avg=23.98,temp_peak=27.1,humidity_avg=74.77,humidity_peak=87.2,pm25_avg=32.94,pm25_peak=51.1,illumination_avg=22163.72,illumination_peak=84749.2,risk_warning=正常
2026-06-04\ttemp_avg=24.39,temp_peak=27.5,humidity_avg=73.48,humidity_peak=85.8,pm25_avg=34.91,pm25_peak=53.1,illumination_avg=22133.61,illumination_peak=81793.7,risk_warning=正常
2026-06-05\ttemp_avg=24.82,temp_peak=27.9,humidity_avg=72.11,humidity_peak=84.9,pm25_avg=36.88,pm25_peak=54.5,illumination_avg=21614.05,illumination_peak=80920.8,risk_warning=正常
2026-06-06\ttemp_avg=25.33,temp_peak=28.5,humidity_avg=70.90,humidity_peak=83.6,pm25_avg=57.94,pm25_peak=90.9,illumination_avg=22047.59,illumination_peak=81997.7,risk_warning=PM2.5污染预警、火灾预警
2026-06-07\ttemp_avg=25.75,temp_peak=28.7,humidity_avg=69.89,humidity_peak=82.4,pm25_avg=40.18,pm25_peak=58.9,illumination_avg=22373.68,illumination_peak=81340.9,risk_warning=火灾预警
2026-06-08\ttemp_avg=26.19,temp_peak=29.2,humidity_avg=68.23,humidity_peak=81.1,pm25_avg=42.48,pm25_peak=59.9,illumination_avg=23966.79,illumination_peak=81259.1,risk_warning=火灾预警
"""


class DashboardViewsTests(TestCase):
    def setUp(self):
        data_service._memory_cache.update({
            'loaded_at': 0.0,
            'rows': None,
            'status': None,
        })
        self.hdfs_patch = patch(
            'visual_app.data_service._read_url',
            return_value=HDFS_RESULT,
        )
        self.cache_patch = patch('visual_app.data_service._write_cache')
        self.hdfs_patch.start()
        self.cache_patch.start()

    def tearDown(self):
        self.hdfs_patch.stop()
        self.cache_patch.stop()

    def test_dashboard_page_renders(self):
        response = self.client.get(reverse('visual_app:dashboard'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '森林环境监测中心')

    def test_dashboard_api_returns_chart_data(self):
        response = self.client.get(reverse('visual_app:dashboard-data'))
        payload = response.json()

        self.assertEqual(response.status_code, 200)
        self.assertFalse(payload['empty'])
        self.assertEqual(payload['meta']['record_count'], 7)
        self.assertEqual(payload['source']['mode'], 'hdfs')
        self.assertEqual(len(payload['daily']), 7)
        self.assertEqual(len(payload['peak_comparison']), 7)
        self.assertTrue(payload['trend']['times'])
        self.assertTrue(payload['heatmap'])

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
        self.assertLessEqual(len(payload['results']), 5)
        self.assertTrue(all(item['risk'] == '中风险' for item in payload['results']))
        self.assertTrue(all('warning' in item for item in payload['results']))
