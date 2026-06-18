from django.http import JsonResponse
from django.shortcuts import render
from django.views import View
from django.db.models import Avg
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from .models import (
    Device,
    DeviceHealthAnalysis,
    DeviceWorstHealth,
    FaultTypeDistribution,
    Device7DayAnalysis,
)
from .services import run_device_full_pipeline

def devices_dashboard(request):
    return render(request, "../templates/devices_dashboard.html")
# =========================
# 1. 概览卡片
# =========================
class DeviceOverviewView(View):
    def get(self, request):

        total = Device.objects.count()
        online = Device.objects.filter(status="ONLINE").count()
        fault = Device.objects.filter(status="FAULT").count()
        offline = total - online

        online_rate = round((online / total) * 100, 2) if total else 0

        avg_health = DeviceHealthAnalysis.objects.aggregate(
            avg=Avg("health_score")
        )["avg"] or 0

        return JsonResponse({
            "total": total,
            "online": online,
            "offline": offline,
            "fault": fault,
            "online_rate": online_rate,
            "avg_health": round(float(avg_health), 2)
        })


# =========================
# 2. 地图数据（核心：融合MR）
# =========================
class DeviceMapView(View):
    def get(self, request):

        # device_id -> health_score
        health_map = {
            d.device.device_id: d.health_score
            for d in DeviceHealthAnalysis.objects.all()
        }

        return JsonResponse([
            {
                "device_id": d.device_id,
                "device_name": d.device_name,
                "device_type": d.device_type.upper(),
                "status": d.status,
                "longitude": d.longitude,
                "latitude": d.latitude,
                "location": d.location,
                "health_score": round(float(health_map.get(d.device_id, 0)), 2)
            }
            for d in Device.objects.all()
        ], safe=False)


# =========================
# 3. 故障类型分布（饼图）
# =========================
class FaultTypeView(View):
    def get(self, request):

        data = FaultTypeDistribution.objects.all()

        return JsonResponse([
            {
                "type": d.fault_type,
                "count": d.fault_count
            }
            for d in data
        ], safe=False)


# =========================
# 4. 健康度最低Top10
# =========================
class WorstHealthView(View):
    def get(self, request):

        data = DeviceHealthAnalysis.objects.order_by("health_score")[:10]

        return JsonResponse([
            {
                "rank": i + 1,
                "device_id": d.device.device_id,
                "score": round(float(d.health_score), 2)
            }
            for i, d in enumerate(data)
        ], safe=False)


# =========================
# 5. 设备7天工作情况统计
# =========================
class Device7DayView(View):
    def get(self, request):

        data = Device7DayAnalysis.objects.all()

        return JsonResponse([
            {
                "device_id": d.device.device_id,
                "stat_date": str(d.stat_date),
                "avg_cpu": round(float(d.avg_cpu), 2),
                "avg_memory": round(float(d.avg_memory), 2),
                "avg_temperature": round(float(d.avg_temperature), 2),
                "avg_power": round(float(d.avg_power), 2),
                "avg_network_delay": round(float(d.avg_network_delay), 2),
                "health_score": round(float(d.health_score), 2)
            }
            for d in data
        ], safe=False)


# =========================
# 6. MapReduce触发接口
# =========================
from django.utils.decorators import method_decorator

@method_decorator(csrf_exempt, name='dispatch')
class RunAnalysisView(View):
    def post(self, request):

        try:
            run_device_full_pipeline()
            return JsonResponse({"status": "success"})
        except Exception as e:
            return JsonResponse({
                "status": "error",
                "message": str(e)
            }, status=500)

# =========================
# pipeline（核心）
# =========================
@require_POST
@csrf_exempt
def run_device_pipeline(request):
    try:
        print("===== START DEVICE PIPELINE 1=====")

        result = run_device_full_pipeline()

        print("PIPELINE SUCCESS:", result)

        return JsonResponse({
            "success": True,
            "msg": "执行成功",
            "data": result
        })

    except Exception as e:
        print("PIPELINE FAILED:", str(e))

        return JsonResponse({
            "success": False,
            "msg": str(e)
        }, status=500)