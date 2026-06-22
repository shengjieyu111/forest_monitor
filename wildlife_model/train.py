"""
YOLOv8 野生动物目标检测 — 训练流水线

功能:
1. 自动将 COCO 格式标注转为 YOLO 格式
2. 生成 data.yaml 配置文件
3. 自动选择 YOLOv8n/s/m 模型，开始训练
4. 支持断点续训、模型导出

数据要求 (COCO 格式):
    datasets/Web/coco_network/
    ├── annotations/
    │   ├── wildlife_instance_train2017.json
    │   ├── wildlife_instance_val2017.json
    │   └── wildlife_instance_test2017.json
    └── images/
        ├── train2017/
        └── val2017/

用法:
    python -m wildlife_model.train --epochs 50 --model yolov8s.pt
"""
import json
import os
import shutil
from pathlib import Path
from typing import Dict, List

# ============================================================
# COCO → YOLO 格式转换
# ============================================================

def coco_to_yolo(coco_json_path: str, images_dir: str, labels_dir: str,
                 class_map: Dict[int, int] = None):
    """
    将 COCO instance 标注转为 YOLO 格式

    YOLO 格式: class_id cx cy w h (归一化 0~1)
    每张图片对应一个同名的 .txt 文件
    """
    os.makedirs(labels_dir, exist_ok=True)

    with open(coco_json_path, "r", encoding="utf-8") as f:
        coco = json.load(f)

    # 建立 image_id → image_info 映射
    id_to_image = {img["id"]: img for img in coco["images"]}

    # 建立 COCO category_id → 0-index 映射
    if class_map is None:
        cat_ids = sorted(c["id"] for c in coco["categories"])
        class_map = {cid: i for i, cid in enumerate(cat_ids)}

    # 按 image_id 聚合标注
    anns_by_image: Dict[int, list] = {}
    for ann in coco["annotations"]:
        # 跳过非 bbox 标注（如仅 keypoints）
        if "bbox" not in ann:
            continue
        img_id = ann["image_id"]
        anns_by_image.setdefault(img_id, []).append(ann)

    converted = 0
    for img_id, anns in anns_by_image.items():
        img_info = id_to_image.get(img_id)
        if img_info is None:
            continue

        img_w, img_h = img_info["width"], img_info["height"]
        file_name = Path(img_info["file_name"]).stem
        label_path = os.path.join(labels_dir, f"{file_name}.txt")

        lines = []
        for ann in anns:
            cat_id = ann["category_id"]
            if cat_id not in class_map:
                continue
            cls_idx = class_map[cat_id]
            x, y, w, h = ann["bbox"]
            # 归一化到 0~1
            cx = (x + w / 2) / img_w
            cy = (y + h / 2) / img_h
            nw = w / img_w
            nh = h / img_h
            lines.append(f"{cls_idx} {cx:.6f} {cy:.6f} {nw:.6f} {nh:.6f}")

        with open(label_path, "w", encoding="utf-8") as lf:
            lf.write("\n".join(lines))

        converted += 1

    print(f"  COCO→YOLO 转换完成: {converted} 张图片 → {labels_dir}")
    return class_map


def prepare_dataset(coco_root: str, yolo_root: str = None):
    """
    准备 YOLO 格式数据集

    Args:
        coco_root: COCO 数据集根目录 (datasets/Web/coco_network/)
        yolo_root:  YOLO 数据集输出目录，默认在 coco_root 旁创建 yolo_format/

    Returns:
        (data_yaml_path, class_names)
    """
    coco_root = Path(coco_root)
    if yolo_root is None:
        yolo_root = coco_root.parent / "yolo_format"
    yolo_root = Path(yolo_root)

    ann_dir = coco_root / "annotations"
    img_dir = coco_root / "images"

    # 读取类别信息
    train_json = ann_dir / "wildlife_instance_train2017.json"
    with open(train_json, "r", encoding="utf-8") as f:
        coco = json.load(f)

    class_names = [c["name"] for c in sorted(coco["categories"], key=lambda x: x["id"])]
    cat_ids = sorted(c["id"] for c in coco["categories"])
    class_map = {cid: i for i, cid in enumerate(cat_ids)}

    print(f"\n{'=' * 60}")
    print(f"  YOLO 数据集准备")
    print(f"  类别数: {len(class_names)}")
    for i, name in enumerate(class_names):
        print(f"    {i}: {name}")
    print(f"{'=' * 60}\n")

    # 转换 train / val / test
    splits = []
    for split in ["train2017", "val2017", "test2017"]:
        json_path = ann_dir / f"wildlife_instance_{split.replace('2017', '')}2017.json"
        img_path = img_dir / split
        lbl_path = yolo_root / "labels" / split

        if json_path.exists() and img_path.exists():
            print(f"[{split}] 转换中...")
            coco_to_yolo(str(json_path), str(img_path), str(lbl_path), class_map)
            # 软链接或复制图片
            yolo_img_dir = yolo_root / "images" / split
            os.makedirs(yolo_img_dir, exist_ok=True)
            for img_file in img_path.iterdir():
                src = img_file
                dst = yolo_img_dir / img_file.name
                if not dst.exists():
                    try:
                        os.symlink(os.path.abspath(src), dst)
                    except OSError:
                        shutil.copy2(src, dst)
            splits.append(split)

    # 生成 data.yaml
    data_yaml = yolo_root / "data.yaml"
    yaml_content = {
        "path": str(yolo_root.resolve()),
        "train": "images/train2017",
        "val": "images/val2017",
        "test": "images/test2017",
        "nc": len(class_names),
        "names": class_names,
    }

    with open(data_yaml, "w", encoding="utf-8") as f:
        import yaml
        yaml.dump(yaml_content, f, default_flow_style=False, allow_unicode=True)

    print(f"\n  data.yaml 已生成 → {data_yaml}")
    print(f"  YOLO 数据集就绪 → {yolo_root}")
    return str(data_yaml), class_names


# ============================================================
# YOLOv8 训练
# ============================================================

def train_yolo(
    data_yaml: str,
    model_name: str = "yolov8s.pt",
    epochs: int = 50,
    imgsz: int = 640,
    batch: int = 16,
    device: str = None,
    output_dir: str = "./wildlife_model/output/",
    resume: bool = False,
    checkpoint: str = None,
    **kwargs,
):
    """
    训练 YOLOv8 目标检测模型

    Args:
        data_yaml:   data.yaml 路径
        model_name:  预训练模型 (yolov8n.pt / yolov8s.pt / yolov8m.pt / yolov8l.pt)
        epochs:      训练轮数
        imgsz:       输入图像尺寸
        batch:       批次大小
        device:      设备 (cuda:0 / cpu / 自动)
        output_dir:  输出目录
        resume:      是否断点续训
        checkpoint:  从指定模型权重继续训练 (如 best.pt)
    """
    from ultralytics import YOLO
    import torch

    # 自动检测设备兼容性
    if device is None:
        if torch.cuda.is_available():
            # 尝试在 CUDA 上创建一个简单 tensor 测试兼容性
            try:
                _ = torch.zeros(1, device="cuda")
                device = "cuda"
            except RuntimeError as e:
                print(f"  [警告] CUDA 不兼容当前 GPU: {e}")
                print(f"  [警告] 自动切换为 CPU 训练")
                device = "cpu"
        else:
            device = "cpu"

    print(f"\n{'=' * 60}")
    print(f"  YOLOv8 野生动物目标检测训练")
    print(f"  模型:   {model_name}")
    print(f"  数据:   {data_yaml}")
    print(f"  轮数:   {epochs}")
    print(f"  图像尺寸: {imgsz}")
    print(f"  批次:   {batch}")
    print(f"  设备:   {device}")
    print(f"  输出:   {output_dir}")
    if checkpoint:
        print(f"  续训自: {checkpoint}")
    print(f"{'=' * 60}\n")

    # 如果提供 checkpoint，从已有权重加载；否则用预训练模型
    if checkpoint and Path(checkpoint).exists():
        model = YOLO(checkpoint)
        print(f"  [续训] 从 {checkpoint} 加载，继续训练 {epochs} 轮")
    else:
        model = YOLO(model_name)

    results = model.train(
        data=data_yaml,
        epochs=epochs,
        imgsz=imgsz,
        batch=batch,
        device=device,
        project=output_dir,
        name="wildlife_yolo",
        exist_ok=True,
        resume=resume,
        # 数据增强
        hsv_h=0.015,
        hsv_s=0.7,
        hsv_v=0.4,
        degrees=10.0,
        translate=0.1,
        scale=0.5,
        shear=2.0,
        perspective=0.0,
        flipud=0.0,
        fliplr=0.5,
        mosaic=1.0,
        mixup=0.1,
        # 优化
        optimizer="AdamW",
        lr0=1e-3,
        lrf=1e-4,
        warmup_epochs=3,
        weight_decay=5e-4,
        cos_lr=True,
        # 验证
        val=True,
        save=True,
        save_period=10,
        # 早停
        patience=15,
        **kwargs,
    )

    # 导出 ONNX / TorchScript
    best_pt = Path(output_dir) / "wildlife_yolo" / "weights" / "best.pt"
    if best_pt.exists():
        print(f"\n  最佳模型: {best_pt}")
        print(f"  导出模型...")
        best_model = YOLO(str(best_pt))
        best_model.export(format="onnx", imgsz=imgsz, simplify=True)

    return results


# ============================================================
# 一键训练入口
# ============================================================

def run(
    coco_root: str = "./datasets/Web/coco_network/",
    model_name: str = "yolov8s.pt",
    epochs: int = 50,
    batch: int = 16,
    imgsz: int = 640,
    device: str = None,
    output_dir: str = "./wildlife_model/output/",
    resume: bool = False,
    checkpoint: str = None,
):
    """
    一键训练: COCO 数据 → YOLO 格式 → 训练

    Args:
        coco_root:  COCO 数据集根目录
        model_name: YOLOv8 模型版本
        epochs:     训练轮数
        batch:      批次大小
        imgsz:      图像尺寸
        device:     设备 (None=自动)
        output_dir: 输出目录
        resume:     是否续训
        checkpoint: 从指定权重继续训练 (如 best.pt)
    """
    # Step 1: 准备 YOLO 格式数据
    data_yaml, class_names = prepare_dataset(coco_root)

    print(f"\n  类别 ({len(class_names)}): {', '.join(class_names)}")

    # Step 2: 训练
    results = train_yolo(
        data_yaml=data_yaml,
        model_name=model_name,
        epochs=epochs,
        imgsz=imgsz,
        batch=batch,
        device=device,
        output_dir=output_dir,
        resume=resume,
        checkpoint=checkpoint,
    )

    # Step 3: 保存类名映射（与训练结果同目录）
    class_map_path = Path("runs/detect/wildlife_model/output/wildlife_yolo/class_names.json")
    os.makedirs(class_map_path.parent, exist_ok=True)
    with open(class_map_path, "w", encoding="utf-8") as f:
        json.dump({
            "class_names": class_names,
            "num_classes": len(class_names),
            "model": model_name,
        }, f, ensure_ascii=False, indent=2)

    print(f"\n{'=' * 60}")
    print(f"  训练完成!")
    print(f"  类别映射: {class_map_path}")
    print(f"  模型目录: {Path('runs/detect/wildlife_model/output/wildlife_yolo')}")
    print(f"{'=' * 60}")

    return results


# ============================================================
# CLI
# ============================================================
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="YOLOv8 野生动物检测训练")
    parser.add_argument("--coco_root", type=str,
                        default="./datasets/Web/coco_network/",
                        help="COCO 数据集根目录")
    parser.add_argument("--model", type=str, default="yolov8s.pt",
                        help="YOLOv8 模型 (yolov8n/s/m/l.pt)")
    parser.add_argument("--epochs", type=int, default=50, help="训练轮数")
    parser.add_argument("--batch", type=int, default=16, help="批次大小")
    parser.add_argument("--imgsz", type=int, default=640, help="图像尺寸")
    parser.add_argument("--device", type=str, default=None,
                        help="设备 (cuda:0 / cpu)")
    parser.add_argument("--output_dir", type=str,
                        default="./wildlife_model/output/",
                        help="输出目录")
    parser.add_argument("--resume", action="store_true", help="断点续训")
    parser.add_argument("--checkpoint", type=str, default=None,
                        help="从指定权重继续训练，如 best.pt 路径")

    args = parser.parse_args()

    run(
        coco_root=args.coco_root,
        model_name=args.model,
        epochs=args.epochs,
        batch=args.batch,
        imgsz=args.imgsz,
        device=args.device,
        output_dir=args.output_dir,
        resume=args.resume,
        checkpoint=args.checkpoint,
    )
