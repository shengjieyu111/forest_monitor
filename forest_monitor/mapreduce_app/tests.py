from unittest.mock import patch

from django.test import TestCase

from .hdfs_sync import sync_all_results
from .models import (
    DailyComfortStat,
    DailyRiskStat,
    DailyWeatherStat,
    HourlyWeatherProfile,
    TopRiskDay,
)


RESULTS = {
    '/waether/output/part-r-00000': (
        '2026-06-02\ttemp_avg=23.50,temp_peak=26.6,humidity_avg=75.91,'
        'humidity_peak=88.4,pm25_avg=31.54,pm25_peak=50.0,'
        'illumination_avg=22360.37,illumination_peak=81750.8,risk_warning=正常\n'
    ),
    '/waether/hourly_output/part-r-00000': (
        '00\tsample_count=84,temp_avg=21.29,humidity_avg=80.40,'
        'pm25_avg=34.25,illumination_avg=0.00\n'
    ),
    '/waether/risk_output/part-r-00000': (
        '2026-06-02\tsample_count=288,high_temp_count=0,'
        'high_humidity_count=32,pollution_count=0,fire_risk_count=0,'
        'normal_count=256,risk_rate=11.11\n'
    ),
    '/waether/comfort_output/part-r-00000': (
        '2026-06-02\tsample_count=288,comfort_index_avg=22.25,'
        'comfortable_count=288,attention_count=0,uncomfortable_count=0,'
        'comfort_rate=100.00\n'
    ),
    '/waether/topn_output/part-r-00000': (
        '01\tdate=2026-06-08,risk_score=18.25,dangerous_count=42,'
        'temp_peak=35.2,humidity_low=41.3,pm25_peak=88.0,illumination_peak=90200.0\n'
    ),
}


class HdfsSyncTests(TestCase):
    @patch('mapreduce_app.hdfs_sync.read_hdfs_result')
    def test_sync_all_results_writes_each_result_table(self, read_result):
        read_result.side_effect = lambda path: RESULTS[path]

        counts = sync_all_results()

        self.assertEqual(counts, {
            'daily': 1,
            'hourly': 1,
            'risk': 1,
            'comfort': 1,
            'topn': 1,
        })
        self.assertEqual(DailyWeatherStat.objects.count(), 1)
        self.assertEqual(HourlyWeatherProfile.objects.count(), 1)
        self.assertEqual(DailyRiskStat.objects.count(), 1)
        self.assertEqual(DailyComfortStat.objects.count(), 1)
        self.assertEqual(TopRiskDay.objects.count(), 1)
