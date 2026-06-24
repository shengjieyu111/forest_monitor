from django.shortcuts import render
from django.http import JsonResponse
import json
import os

def wildlife_page(request):
    """野生动物AI识别页面"""
    model_list = [
        {
            "id": "wildlife_best",
            "icon": "🎯",
            "name": "野生动物检测模型",
            "arch": "YOLOv8n",
            "desc": "针对鹫峰林场11种野生动物训练的YOLOv8检测模型，支持红外相机照片识别。",
            "num_classes": 11,
            "device": "CPU"
        },
        {
            "id": "wildlife_sensitive",
            "icon": "🔍",
            "name": "敏感物种检测",
            "arch": "YOLOv8s",
            "desc": "高精度模型，重点检测国家保护动物（大熊猫、川金丝猴等）。",
            "num_classes": 11,
            "device": "CPU"
        }
    ]

    # 物种信息数据
    species_data_path = os.path.join(os.path.dirname(__file__), 'species_data.json')
    species_info = {}
    if os.path.exists(species_data_path):
        with open(species_data_path, 'r', encoding='utf-8') as f:
            species_info = json.load(f)

    return render(request, 'wildlife_model/wildlife.html', {
        'page': 'ai',
        'model_list': model_list,
        'model_list_json': json.dumps(model_list, ensure_ascii=False),
    })
