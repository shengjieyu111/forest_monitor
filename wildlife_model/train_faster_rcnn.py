"""
Faster R-CNN 野生动物检测 — 训练脚本（两阶段 CNN）

功能:
1. 读取 COCO 格式野生动物数据集（与 YOLOv8 同一份数据）
2. 使用 torchvision 预训练 Faster R-CNN ResNet-50 FPN
3. 替换 head 为 11 类野生动物分类器
4. 微调训练，输出 faster_rcnn_wildlife.pt

数据要求:
    datasets/Web/coco_network/
    ├── annotations/
    │   ├── wildlife_instance_train2017.json
    │   └── wildlife_instance_val2017.json
    └── images/
        ├── train2017/
        └── val2017/

用法:
    # CPU 训练
    python -m wildlife_model.train_faster_rcnn --epochs 10 --batch 4
    # GPU 训练（推荐）
    python -m wildlife_model.train_faster_rcnn --epochs 10 --batch 8 --device cuda
    # GPU 快速训练（小图 + 大batch）
    python -m wildlife_model.train_faster_rcnn --epochs 10 --batch 8 --device cuda --imgsz 416 --workers 8
"""
import json
import os
import sys
import time
from pathlib import Path
from typing import Dict, List, Tuple, Optional

import cv2
import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import Dataset, DataLoader
from torchvision import transforms as T
from torchvision.models.detection import fasterrcnn_resnet50_fpn
from torchvision.models.detection.faster_rcnn import FastRCNNPredictor
from torchvision.ops import box_iou


# ============================================================
# 数据集
# ============================================================

class WildlifeCocoDataset(Dataset):
    """COCO 格式野生动物数据集，返回 (image_tensor, target_dict)"""

    def __init__(self, coco_json: str, images_dir: str, transforms=None, target_size: int = 640):
        self.images_dir = Path(images_dir)
        self.target_size = target_size
        self.transforms = transforms or T.Compose([T.ToTensor()])

        with open(coco_json, "r", encoding="utf-8") as f:
            coco = json.load(f)

        # 图片信息
        self.images = coco["images"]
        self.id_to_image = {img["id"]: img for img in self.images}

        # 类别: COCO category_id -> 1-indexed label (0=background)
        self.categories = sorted(coco["categories"], key=lambda c: c["id"])
        self.cat_id_to_label = {c["id"]: i + 1 for i, c in enumerate(self.categories)}
        self.num_classes = len(self.categories) + 1  # + background

        # 按 image_id 聚合标注
        self.anns_by_image: Dict[int, list] = {}
        for ann in coco["annotations"]:
            if "bbox" not in ann:
                continue
            img_id = ann["image_id"]
            self.anns_by_image.setdefault(img_id, []).append(ann)

        # 只保留有标注 + 可读取的图片
        self.valid_images = []
        self._bad_images = []
        for img in self.images:
            if img["id"] not in self.anns_by_image:
                continue
            img_path = self.images_dir / img["file_name"]
            test = cv2.imread(str(img_path))
            if test is not None:
                self.valid_images.append(img)
            else:
                self._bad_images.append(str(img_path))
        if self._bad_images:
            print(f"  [警告] 跳过 {len(self._bad_images)} 张损坏图片: {self._bad_images[:5]}...")

    def __len__(self):
        return len(self.valid_images)

    def __getitem__(self, idx):
        img_info = self.valid_images[idx]
        img_path = self.images_dir / img_info["file_name"]
        image = cv2.imread(str(img_path))
        if image is None:
            # 兜底：跳过损坏图片，随机取另一张
            new_idx = (idx + 1) % len(self.valid_images)
            return self.__getitem__(new_idx)
        image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)

        # 缩放图像加速训练（保持宽高比，短边对齐 target_size）
        h, w_orig = image.shape[:2]
        scale = self.target_size / min(h, w_orig)
        if scale < 1.0:  # 只缩小不放大的图
            new_h, new_w = int(h * scale), int(w_orig * scale)
            image = cv2.resize(image, (new_w, new_h), interpolation=cv2.INTER_AREA)
            scale_x, scale_y = new_w / w_orig, new_h / h
        else:
            scale_x, scale_y = 1.0, 1.0

        anns = self.anns_by_image.get(img_info["id"], [])
        boxes = []
        labels = []
        for ann in anns:
            x, y, w, h = ann["bbox"]
            if w <= 0 or h <= 0:
                continue
            boxes.append([
                x * scale_x,
                y * scale_y,
                (x + w) * scale_x,
                (y + h) * scale_y,
            ])
            labels.append(self.cat_id_to_label.get(ann["category_id"], 0))

        if len(boxes) == 0:
            # 无标注则给一个 dummy
            boxes = torch.zeros((0, 4), dtype=torch.float32)
            labels = torch.zeros((0,), dtype=torch.int64)
        else:
            boxes = torch.tensor(boxes, dtype=torch.float32)
            labels = torch.tensor(labels, dtype=torch.int64)

        target = {
            "boxes": boxes,
            "labels": labels,
            "image_id": torch.tensor([img_info["id"]]),
            "area": (boxes[:, 3] - boxes[:, 1]) * (boxes[:, 2] - boxes[:, 0]),
            "iscrowd": torch.zeros((len(boxes),), dtype=torch.int64),
        }

        if self.transforms:
            image = self.transforms(image)

        return image, target

    @staticmethod
    def collate_fn(batch):
        return tuple(zip(*batch))


# ============================================================
# 训练
# ============================================================

def get_model(num_classes: int, device: str = "cpu") -> nn.Module:
    """构建 Faster R-CNN，head 替换为 num_classes"""
    model = fasterrcnn_resnet50_fpn(
        weights="DEFAULT",
        rpn_pre_nms_top_n_train=500,      # 减少 RPN 候选框（默认2000）→ 提速
        rpn_post_nms_top_n_train=250,
        rpn_pre_nms_top_n_test=250,
        rpn_post_nms_top_n_test=100,
    )
    in_features = model.roi_heads.box_predictor.cls_score.in_features
    model.roi_heads.box_predictor = FastRCNNPredictor(in_features, num_classes)
    model.to(device)
    return model


class AverageMeter:
    def __init__(self):
        self.reset()

    def reset(self):
        self.val = 0.0
        self.avg = 0.0
        self.sum = 0.0
        self.count = 0

    def update(self, val, n=1):
        self.val = val
        self.sum += val * n
        self.count += n
        self.avg = self.sum / self.count


def train_one_epoch(model, loader, optimizer, device, epoch, scaler=None):
    model.train()
    loss_meter = AverageMeter()
    loss_cls_meter = AverageMeter()
    loss_box_meter = AverageMeter()
    loss_rpn_meter = AverageMeter()
    loss_obj_meter = AverageMeter()

    start = time.time()
    for batch_idx, (images, targets) in enumerate(loader):
        images = [img.to(device, non_blocking=True) for img in images]
        targets = [{k: v.to(device, non_blocking=True) for k, v in t.items()} for t in targets]

        # AMP 混合精度前向
        if scaler is not None:
            with torch.amp.autocast('cuda'):
                loss_dict = model(images, targets)
                losses = sum(loss for loss in loss_dict.values())
            optimizer.zero_grad()
            scaler.scale(losses).backward()
            scaler.step(optimizer)
            scaler.update()
        else:
            loss_dict = model(images, targets)
            losses = sum(loss for loss in loss_dict.values())
            optimizer.zero_grad()
            losses.backward()
            optimizer.step()

        n = len(images)
        loss_meter.update(losses.item(), n)
        loss_cls_meter.update(loss_dict.get("loss_classifier", 0).item(), n)
        loss_box_meter.update(loss_dict.get("loss_box_reg", 0).item(), n)
        loss_rpn_meter.update(loss_dict.get("loss_rpn_box_reg", 0).item(), n)
        loss_obj_meter.update(loss_dict.get("loss_objectness", 0).item(), n)

        if batch_idx % 20 == 0 or batch_idx == len(loader) - 1:
            elapsed = time.time() - start
            eta = (elapsed / (batch_idx + 1)) * (len(loader) - batch_idx - 1)
            print(f"  Epoch {epoch:3d} [{batch_idx+1:4d}/{len(loader):4d}]  "
                  f"loss={loss_meter.avg:.4f}  cls={loss_cls_meter.avg:.4f}  "
                  f"box={loss_box_meter.avg:.4f}  rpn={loss_rpn_meter.avg:.4f}  "
                  f"obj={loss_obj_meter.avg:.4f}  [{elapsed:.0f}s/{eta:.0f}s]")

    return loss_meter.avg


@torch.no_grad()
def evaluate(model, loader, device):
    model.train()  # 评估也用 train() 以获取 loss
    loss_meter = AverageMeter()
    for images, targets in loader:
        # 逐张推理，避免验证时 batch 过大导致显存溢出
        for i in range(len(images)):
            single_img = [images[i].to(device)]
            single_tgt = [{k: v.to(device) for k, v in targets[i].items()}]
            try:
                loss_dict = model(single_img, single_tgt)
                losses = sum(loss for loss in loss_dict.values())
                loss_meter.update(losses.item(), 1)
            except RuntimeError as e:
                if "out of memory" in str(e):
                    torch.cuda.empty_cache()
                    print(f"  [警告] 验证OOM，跳过第 {i} 张图")
                    continue
                raise
    return loss_meter.avg


def train(
    coco_root: str = "./datasets/Web/coco_network/",
    epochs: int = 10,
    batch: int = 4,
    lr: float = 1e-3,
    device: str = None,
    output_path: str = "./wildlife_model/output/faster_rcnn_wildlife.pt",
    imgsz: int = 640,
    workers: int = 4,
    amp: bool = True,
    resume: str = None,
):
    """一键训练 Faster R-CNN 野生动物检测模型

    Args:
        resume: checkpoint 路径，从该 checkpoint 续训
    """
    # 设备
    if device is None:
        if torch.cuda.is_available():
            try:
                _ = torch.zeros(1, device="cuda")
                device = "cuda"
            except Exception:
                device = "cpu"
        else:
            device = "cpu"

    coco_root = Path(coco_root)
    ann_dir = coco_root / "annotations"
    img_dir = coco_root / "images"

    # 数据集
    print(f"\n{'=' * 60}")
    print(f"  Faster R-CNN 野生动物检测 — 训练")
    print(f"{'=' * 60}")
    print(f"  数据根目录: {coco_root}")

    train_dataset = WildlifeCocoDataset(
        str(ann_dir / "wildlife_instance_train2017.json"),
        str(img_dir / "train2017"),
        target_size=imgsz,
    )
    val_dataset = WildlifeCocoDataset(
        str(ann_dir / "wildlife_instance_val2017.json"),
        str(img_dir / "val2017"),
        target_size=imgsz,
    )

    num_classes = train_dataset.num_classes
    class_names = [c["name"] for c in train_dataset.categories]
    print(f"  训练集: {len(train_dataset)} 张")
    print(f"  验证集: {len(val_dataset)} 张")
    print(f"  类别数: {num_classes - 1} (含背景共{num_classes})")
    print(f"  类别: {', '.join(class_names)}")
    print(f"  设备: {device}")
    print(f"  轮数: {epochs}, 批次: {batch}, 学习率: {lr}")
    print(f"  图像尺寸: {imgsz}, workers: {workers}, AMP: {amp}")
    print(f"{'=' * 60}\n")

    train_loader = DataLoader(
        train_dataset, batch_size=batch, shuffle=True,
        collate_fn=WildlifeCocoDataset.collate_fn,
        num_workers=workers, pin_memory=True,
    )
    val_loader = DataLoader(
        val_dataset, batch_size=batch, shuffle=False,
        collate_fn=WildlifeCocoDataset.collate_fn,
        num_workers=workers, pin_memory=True,
    )

    # 模型 & 优化器
    model = get_model(num_classes, device)
    params = [p for p in model.parameters() if p.requires_grad]
    optimizer = torch.optim.SGD(params, lr=lr, momentum=0.9, weight_decay=1e-4)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=epochs)

    # AMP 混合精度（仅 CUDA 有效）
    scaler = torch.amp.GradScaler('cuda') if (amp and device == "cuda") else None
    if scaler is not None:
        print("  [AMP] 混合精度训练已启用\n")

    # ---- 断点续训 ----
    start_epoch = 1
    best_val_loss = float("inf")
    if resume:
        resume_path = Path(resume)
        if not resume_path.exists():
            raise FileNotFoundError(f"Checkpoint 不存在: {resume_path}")
        ckpt = torch.load(str(resume_path), map_location=device, weights_only=False)
        model.load_state_dict(ckpt["model_state_dict"])
        optimizer.load_state_dict(ckpt["optimizer_state_dict"])
        start_epoch = ckpt["epoch"] + 1
        best_val_loss = ckpt.get("val_loss", float("inf"))
        print(f"  [续训] 从 {resume_path} 恢复")
        print(f"  [续训] Epoch {ckpt['epoch']} 已完成, val_loss={ckpt['val_loss']:.4f}")
        print(f"  [续训] 将从 Epoch {start_epoch} 继续\n")

    # ---- 训练循环 ----
    for epoch in range(start_epoch, epochs + 1):
        print(f"--- Epoch {epoch}/{epochs} ---")
        train_loss = train_one_epoch(model, train_loader, optimizer, device, epoch, scaler)
        if device == "cuda":
            torch.cuda.empty_cache()  # 清理训练残存显存
        val_loss = evaluate(model, val_loader, device)
        scheduler.step()

        is_best = val_loss < best_val_loss
        if is_best:
            best_val_loss = val_loss

        print(f"  Epoch {epoch:3d}  train_loss={train_loss:.4f}  "
              f"val_loss={val_loss:.4f}  lr={scheduler.get_last_lr()[0]:.2e}  "
              f"{'[BEST]' if is_best else ''}")

        # 每轮都保存
        ckpt = {
            "epoch": epoch,
            "model_state_dict": model.state_dict(),
            "optimizer_state_dict": optimizer.state_dict(),
            "val_loss": val_loss,
            "num_classes": num_classes,
            "class_names": class_names,
        }
        torch.save(ckpt, output_path)
        if is_best:
            best_path = str(Path(output_path).with_suffix("")) + "_best.pt"
            torch.save(ckpt, best_path)

    print(f"\n{'=' * 60}")
    print(f"  训练完成!")
    print(f"  最佳验证 loss: {best_val_loss:.4f}")
    print(f"  模型已保存: {output_path}")
    print(f"  类别映射: {class_names}")
    print(f"{'=' * 60}")

    # 同时保存 class_names.json（与 YOLOv8 格式一致）
    class_json_path = Path(output_path).parent / "faster_rcnn_class_names.json"
    with open(class_json_path, "w", encoding="utf-8") as f:
        json.dump({
            "class_names": class_names,
            "num_classes": len(class_names),
            "model": "faster_rcnn_resnet50_fpn",
        }, f, ensure_ascii=False, indent=2)
    print(f"  类别文件: {class_json_path}")


# ============================================================
# CLI
# ============================================================
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Faster R-CNN 野生动物检测训练")
    parser.add_argument("--coco_root", type=str, default="./datasets/Web/coco_network/")
    parser.add_argument("--epochs", type=int, default=10, help="训练轮数")
    parser.add_argument("--batch", type=int, default=4, help="批次大小")
    parser.add_argument("--lr", type=float, default=1e-3, help="学习率")
    parser.add_argument("--device", type=str, default=None, help="设备 (cuda/cpu)")
    parser.add_argument("--output", type=str,
                        default="./wildlife_model/output/faster_rcnn_wildlife.pt")
    parser.add_argument("--imgsz", type=int, default=640, help="训练图像尺寸（短边）")
    parser.add_argument("--workers", type=int, default=4, help="DataLoader 线程数")
    parser.add_argument("--no_amp", action="store_true", help="禁用混合精度")
    parser.add_argument("--resume", type=str, default=None,
                        help="从 checkpoint 续训 (如 output/faster_rcnn_wildlife.pt)")

    args = parser.parse_args()
    train(
        coco_root=args.coco_root,
        epochs=args.epochs,
        batch=args.batch,
        lr=args.lr,
        device=args.device,
        output_path=args.output,
        imgsz=args.imgsz,
        workers=args.workers,
        amp=not args.no_amp,
        resume=args.resume,
    )
