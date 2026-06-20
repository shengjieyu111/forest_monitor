from django.http import JsonResponse
from django.shortcuts import render
from django.views import View
from django.db.models import Avg, Sum
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from .models import (
    Device,
    DeviceHealthAnalysis,
    FaultTimeRegionAnalysis,
    FaultTypeDistribution,
    DeviceWorkAnalysis,
)
from .services import run_device_full_pipeline


def devices_dashboard(request):
    return render(request, "../templates/devices_dashboard.html", {"page": "devices"})

# =========================
# 1. 概览数据
# =========================
class DeviceOverviewView(View):
    def get(self, request):
        total = Device.objects.count()
        online = Device.objects.filter(status='ONLINE').count()
        fault = Device.objects.filter(status__in=['FAULT', 'OFFLINE']).count()

        return JsonResponse({
            "total": total,
            "online": online,
            "fault": fault,
            "rate": round((online / total * 100) if total > 0 else 0, 1)
        })

# =========================
# 2. 地图数据
# =========================
class DeviceMapView(View):
    def get(self, request):
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
# 3. 故障类型分布（折线图）
# =========================
class FaultTypeView(View):
    def get(self, request):
        # 获取所有数据，包含设备类型
        data = FaultTypeDistribution.objects.all()

        result = []
        for d in data:
            result.append({
                "fault_type": d.fault_type,  # 故障类型 (如 NETWORK_OFFLINE)
                "device_type": d.device_type,  # 设备类型 (如 CAMERA) -> 用于折线图的系列(Series)
                "count": d.fault_count  # 数量 -> 用于Y轴
            })

        return JsonResponse(result, safe=False)


# =========================
# =========================
# 4. 故障时间区域分析（5个雷达图）
# =========================
class FaultTimeRegionView(View):
    def get(self, request):
        data = FaultTimeRegionAnalysis.objects.values(
            'location', 'analysis_date', 'fault_type', 'fault_count'
        )
        result = []
        for d in data:
            result.append({
                "location": d['location'],
                "month": str(d['analysis_date'])[:7],
                "fault_type": d['fault_type'],
                "fault_count": d['fault_count']
            })
        return JsonResponse(result, safe=False)


# =========================
# 5. 各区域健康度低于65的设备数量
# =========================
class RegionLowHealthView(View):
    def get(self, request):
        from django.db.models import Count
        locations = ['CORE_SCENIC', 'FIRE_ZONE', 'ENTRANCE_GATE', 'INFRA_AREA', 'TRAIL_ZONE']
        
        result = []
        for loc in locations:
            count = DeviceHealthAnalysis.objects.filter(
                device__location=loc,
                health_score__lt=65
            ).values('device').distinct().count()
            result.append({
                "location": loc,
                "low_health_count": count
            })
        return JsonResponse(result, safe=False)


# =========================
# 6. 健康度最低Bottom10（保持不变）
# =========================
class WorstHealthView(View):
    def get(self, request):
        data = DeviceHealthAnalysis.objects.order_by("health_score")[:10]

        LOCATION_MAP = {
            "CORE_SCENIC": "核心景区",
            "FIRE_ZONE": "森林防火区",
            "ENTRANCE_GATE": "出入口及卡口",
            "INFRA_AREA": "基础设施区",
            "TRAIL_ZONE": "步道与游览区",
        }

        return JsonResponse([
            {
                "rank": i + 1,
                "device_id": d.device.device_id,
                "location": LOCATION_MAP.get(d.device.location, d.device.location),
                "score": round(float(d.health_score), 2)
            }
            for i, d in enumerate(data)
        ], safe=False)


# =========================
# 7. 设备工作情况统计
# =========================
class DeviceWorkView(View):
    def get(self, request):
        data = DeviceWorkAnalysis.objects.all()

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
# 8. 设备工作统计（用于表格展示）
# =========================
class DeviceSevenDayView(View):
    def get(self, request):
        data = DeviceWorkAnalysis.objects.all()

        return JsonResponse([
            {
                "device_id": d.device.device_id,
                "avg_cpu": round(float(d.avg_cpu), 2),
                "avg_memory": round(float(d.avg_memory), 2),
                "avg_temperature": round(float(d.avg_temperature), 2),
                "avg_power": round(float(d.avg_power), 2),
                "avg_network_delay": round(float(d.avg_network_delay), 2)
            }
            for d in data
        ], safe=False)

# =========================
# 9. MapReduce触发接口
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