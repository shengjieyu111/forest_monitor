"""
Django 管理命令: 训练 YOLOv8 野生动物目标检测模型

将此文件复制到 Django 项目的 management/commands/ 目录下使用。

用法:
    python manage.py train_wildlife [选项]

选项:
    --coco_root     COCO 数据集根目录（必填）
    --model         预训练模型 (yolov8n/s/m/l.pt，默认: yolov8s.pt)
    --epochs        训练轮数（默认: 50）
    --batch         批次大小（默认: 16）
    --imgsz         图像尺寸（默认: 640）
    --device        设备 (cuda:0 / cpu，默认: 自动)
    --output_dir    输出目录（默认: ./wildlife_model/output/）
    --resume        断点续训

示例:
    python manage.py train_wildlife
    python manage.py train_wildlife --epochs 100 --model yolov8m.pt
    python manage.py train_wildlife --device cpu --batch 8
"""
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "训练 YOLOv8 野生动物目标检测模型"

    def add_arguments(self, parser):
        parser.add_argument(
            "--coco_root", type=str,
            default="./datasets/Web/coco_network/",
            help="COCO 数据集根目录"
        )
        parser.add_argument(
            "--model", type=str, default="yolov8s.pt",
            help="YOLOv8 模型 (yolov8n/s/m/l.pt)"
        )
        parser.add_argument(
            "--epochs", type=int, default=50,
            help="训练轮数"
        )
        parser.add_argument(
            "--batch", type=int, default=16,
            help="批次大小"
        )
        parser.add_argument(
            "--imgsz", type=int, default=640,
            help="输入图像尺寸"
        )
        parser.add_argument(
            "--device", type=str, default=None,
            help="设备 (cuda:0 / cpu)"
        )
        parser.add_argument(
            "--output_dir", type=str,
            default="./wildlife_model/output/",
            help="输出目录"
        )
        parser.add_argument(
            "--resume", action="store_true",
            help="断点续训"
        )

    def handle(self, *args, **options):
        import os

        coco_root = options["coco_root"]
        if not os.path.isdir(coco_root):
            raise CommandError(f"COCO 数据集目录不存在: {coco_root}")

        ann_dir = os.path.join(coco_root, "annotations")
        if not os.path.isdir(ann_dir):
            raise CommandError(f"标注目录不存在: {ann_dir}")

        self.stdout.write(self.style.SUCCESS(
            f"\n{'=' * 60}\n"
            f"  YOLOv8 野生动物目标检测训练\n"
            f"  数据集: {coco_root}\n"
            f"  模型:   {options['model']}\n"
            f"  轮数:   {options['epochs']}\n"
            f"  批次:   {options['batch']}\n"
            f"  图像尺寸: {options['imgsz']}\n"
            f"  设备:   {options['device'] or '自动'}\n"
            f"{'=' * 60}\n"
        ))

        try:
            from wildlife_model.train import run
        except ImportError as e:
            raise CommandError(
                f"导入训练模块失败: {e}\n"
                f"请确保已安装依赖: pip install ultralytics"
            )

        self.stdout.write(self.style.WARNING(
            "开始训练，这将需要一定时间...\n"
        ))

        results = run(
            coco_root=coco_root,
            model_name=options["model"],
            epochs=options["epochs"],
            batch=options["batch"],
            imgsz=options["imgsz"],
            device=options["device"],
            output_dir=options["output_dir"],
            resume=options["resume"],
        )

        self.stdout.write(self.style.SUCCESS(
            f"\n{'=' * 60}\n"
            f"  ✓ 训练完成!\n"
            f"  模型保存在: {options['output_dir']}\n"
            f"{'=' * 60}\n"
        ))
