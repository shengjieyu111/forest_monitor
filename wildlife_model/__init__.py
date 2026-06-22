"""
野生动物 AI 模型模块 (YOLOv8 目标检测)

目录结构:
    train.py          — 训练流水线 (COCO→YOLO + YOLOv8 训练)
    predict.py        — 推理预测 (目标检测 + 画框)
    templates/        — Web 前端模板
    management/        — Django 管理命令
    scripts/          — 数据工具脚本

快速开始:
    训练: python -m wildlife_model.train --epochs 50
    推理: python -m wildlife_model.predict test.jpg --save
"""
