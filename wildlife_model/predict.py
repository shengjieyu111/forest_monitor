# -*- coding: utf-8 -*-
"""
野生动物检测推理模块
用法:
    python -m wildlife_model.predict test.jpg --save
    python -m wildlife_model.predict test.jpg --json
"""
import base64
import json
import os
import sys
import time
from pathlib import Path
from typing import Optional, List, Dict

import cv2
import numpy as np
import torch
import warnings

# ─────────────────────────────────────────────────────────────
# PyTorch 2.6+ 兼容性修复
# 新版 PyTorch 默认 torch.load(weights_only=True)，
# 但 ultralytics==8.0.239 内部 torch.load() 未显式传 weights_only=False，
# 导致自定义 YOLO 模型加载失败 (UnpicklingError)。
# 此处将 torch.load 默认值改为 False，确保所有模型正常加载。
# ─────────────────────────────────────────────────────────────
_original_torch_load = torch.load


def _torch_load_patched(*args, **kwargs):
    kwargs.setdefault("weights_only", False)
    return _original_torch_load(*args, **kwargs)


torch.load = _torch_load_patched

from ultralytics import YOLO


class WildlifeDetector:
    """YOLOv8 野生动物检测器"""

    # 类级别缓存物种简介
    _species_info: Optional[Dict] = None

    def __init__(self, model_path: Optional[str] = None, device: str = "cpu"):
        self.device = device
        self.model_path = model_path or self._find_model()
        self.class_names: List[str] = []
        self.model = None
        self._load_model()
        self._load_species_info()

    def _find_model(self) -> str:
        candidates = [
            "runs/detect/wildlife_model/output/wildlife_yolo/weights/best.pt",
            "wildlife_model/output/wildlife_yolo/weights/best.pt",
            "yolov8s.pt",
            "yolov8n.pt",
        ]
        base = Path(__file__).resolve().parent.parent
        for path in candidates:
            full = base / path if not os.path.isabs(path) else Path(path)
            if full.exists():
                print(f"[模型] {full}")
                return str(full)
        print("[警告] 未找到训练模型，使用 yolov8n.pt")
        return "yolov8n.pt"

    def _load_model(self):
        self.model = YOLO(self.model_path)
        # 仅从模型同级目录查找 class_names.json（训练时自动生成）
        class_json = os.path.join(os.path.dirname(str(self.model_path)), "class_names.json")
        if os.path.exists(class_json):
            with open(class_json, "r", encoding="utf-8") as f:
                data = json.load(f)
                self.class_names = data.get("class_names", [])
            if self.class_names:
                print(f"[模型] 类别({len(self.class_names)}): {', '.join(self.class_names[:8])}...")
                return
        # 回退到模型自带的类别名（如 yolov8n.pt 的 COCO 80 类）
        if hasattr(self.model, "names") and self.model.names:
            self.class_names = list(self.model.names.values())
        else:
            self.class_names = [f"class_{i}" for i in range(80)]
        print(f"[模型] YOLO默认类别({len(self.class_names)})")

    @classmethod
    def _load_species_info(cls):
        """加载野生动物简介知识库"""
        if cls._species_info is not None:
            return
        info_path = Path(__file__).resolve().parent / "wildlife_info.json"
        if info_path.exists():
            with open(info_path, "r", encoding="utf-8") as f:
                cls._species_info = json.load(f)
        else:
            cls._species_info = {}

    @staticmethod
    def get_species_info(class_name: str) -> Optional[Dict]:
        WildlifeDetector._load_species_info()
        return WildlifeDetector._species_info.get(class_name)

    def detect(self, image_path: str, conf: float = 0.25, iou: float = 0.45) -> List[Dict]:
        if self.model is None:
            raise RuntimeError("模型未加载")
        results = self.model(image_path, conf=conf, iou=iou, device=self.device, verbose=False)
        detections = []
        for r in results:
            boxes = r.boxes
            if boxes is None:
                continue
            xyxy = boxes.xyxy.cpu().numpy()
            cls_ids = boxes.cls.cpu().numpy().astype(int)
            confs = boxes.conf.cpu().numpy()
            for i in range(len(cls_ids)):
                cls_id = int(cls_ids[i])
                name = self.class_names[cls_id] if cls_id < len(self.class_names) else f"class_{cls_id}"
                detections.append({
                    "class_id": cls_id,
                    "class_name": name,
                    "confidence": round(float(confs[i]), 4),
                    "bbox": [round(float(x), 1) for x in xyxy[i]],
                })
        return detections

    def detect_with_details(self, image_path: str, conf: float = 0.25, iou: float = 0.45) -> Dict:
        t0 = time.time()
        detections = self.detect(image_path, conf, iou)
        elapsed = round((time.time() - t0) * 1000)
        class_counts: Dict[str, int] = {}
        for d in detections:
            name = d["class_name"]
            class_counts[name] = class_counts.get(name, 0) + 1
        # 附加上检测到的物种简介
        species_info = {}
        for cls_name in class_counts:
            info = self.get_species_info(cls_name)
            if info:
                species_info[cls_name] = info
        return {
            "success": True,
            "total_count": len(detections),
            "inference_time_ms": elapsed,
            "class_counts": class_counts,
            "detections": detections,
            "species_info": species_info,
        }

    def render_detections(self, image_path: str, save_path: Optional[str] = None,
                          conf: float = 0.25, iou: float = 0.45) -> Optional[np.ndarray]:
        img = cv2.imread(image_path)
        if img is None:
            print(f"[错误] 无法读取: {image_path}")
            return None
        detections = self.detect(image_path, conf, iou)
        colors = self._generate_colors(len(self.class_names))
        for det in detections:
            x1, y1, x2, y2 = [int(v) for v in det["bbox"]]
            cls_id = det["class_id"]
            name = det["class_name"]
            conf_val = det["confidence"]
            rgb = colors[cls_id % len(colors)]
            color_bgr = (rgb[2], rgb[1], rgb[0])
            cv2.rectangle(img, (x1, y1), (x2, y2), color_bgr, 2)
            label = f"{name} {conf_val:.2f}"
            (tw, th), baseline = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
            cv2.rectangle(img, (x1, y1 - th - 8), (x1 + tw + 4, y1), color_bgr, -1)
            cv2.putText(img, label, (x1 + 2, y1 - 4),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
        if save_path:
            os.makedirs(os.path.dirname(save_path) or ".", exist_ok=True)
            cv2.imwrite(save_path, img)
            print(f"[保存] {save_path}")
        return img

    def render_to_base64(self, image_path: str, conf: float = 0.25, iou: float = 0.45) -> str:
        """返回标注后的图片的 base64 编码字符串（可直接用于 <img src>）"""
        img = self.render_detections(image_path, conf=conf, iou=iou)
        if img is None:
            return ""
        try:
            _, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 85])
        except Exception:
            _, buf = cv2.imencode(".jpg", img)
        return base64.b64encode(buf).decode("utf-8")

    @staticmethod
    def _generate_colors(n: int) -> List[tuple]:
        colors = []
        for i in range(n):
            hsv = np.array([[[i / n * 179, 200, 255]]], dtype=np.uint8)
            bgr = cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR)[0][0]
            colors.append(tuple(int(c) for c in bgr[::-1]))
        return colors

    def model_info(self) -> Dict:
        params = 0
        try:
            if self.model and hasattr(self.model, 'model'):
                params = sum(p.numel() for p in self.model.model.parameters())
        except Exception:
            pass
        return {
            "model_path": os.path.abspath(str(self.model_path)),
            "num_classes": len(self.class_names),
            "class_names": self.class_names,
            "device": self.device,
            "parameters": params,
        }


# ============================================================
# Faster R-CNN 检测器（两阶段 CNN 架构）
# ============================================================

class FastRCNNDetector:
    """Faster R-CNN 两阶段目标检测器 — ResNet-50 FPN 主干

    加载优先级:
    1. 训练后的 faster_rcnn_wildlife.pt（11种野生动物）
    2. torchvision 预训练 COCO 权重（fallback，91类）
    """

    _species_info: Optional[Dict] = None

    def __init__(self, device: str = "cpu", checkpoint_path: Optional[str] = None):
        self.device = device
        self.checkpoint_path = checkpoint_path
        from torchvision.models.detection import fasterrcnn_resnet50_fpn
        from torchvision.models.detection.faster_rcnn import FastRCNNPredictor
        from torchvision import transforms as T

        self._transforms = T.Compose([T.ToTensor()])

        # 查找训练好的权重
        ckpt = self._find_checkpoint()
        if ckpt:
            print(f"[模型] Faster R-CNN 加载训练权重: {ckpt}")
            loaded = torch.load(ckpt, map_location=device, weights_only=False)
            num_classes = loaded.get("num_classes", 0)
            self.class_names = loaded.get("class_names", [])
            self.model = fasterrcnn_resnet50_fpn(weights=None)
            in_features = self.model.roi_heads.box_predictor.cls_score.in_features
            self.model.roi_heads.box_predictor = FastRCNNPredictor(in_features, num_classes)
            self.model.load_state_dict(loaded["model_state_dict"])
            self._from_checkpoint = True
        else:
            # Fallback: COCO 91 类预训练
            from torchvision.models.detection import FasterRCNN_ResNet50_FPN_Weights
            self.model = fasterrcnn_resnet50_fpn(
                weights=FasterRCNN_ResNet50_FPN_Weights.COCO_V1
            )
            self.class_names = [
                "__background__", "person", "bicycle", "car", "motorcycle", "airplane", "bus",
                "train", "truck", "boat", "traffic light", "fire hydrant", "stop sign",
                "parking meter", "bench", "bird", "cat", "dog", "horse", "sheep", "cow",
                "elephant", "bear", "zebra", "giraffe", "backpack", "umbrella", "handbag",
                "tie", "suitcase", "frisbee", "skis", "snowboard", "sports ball", "kite",
                "baseball bat", "baseball glove", "skateboard", "surfboard", "tennis racket",
                "bottle", "wine glass", "cup", "fork", "knife", "spoon", "bowl",
                "banana", "apple", "sandwich", "orange", "broccoli", "carrot", "hot dog",
                "pizza", "donut", "cake", "chair", "couch", "potted plant", "bed",
                "dining table", "toilet", "tv", "laptop", "mouse", "remote", "keyboard",
                "cell phone", "microwave", "oven", "toaster", "sink", "refrigerator",
                "book", "clock", "vase", "scissors", "teddy bear", "hair drier", "toothbrush",
            ]
            self._from_checkpoint = False
            print(f"[模型] Faster R-CNN ResNet-50 FPN  (COCO {len(self.class_names)} 类) [未找到训练权重]")

        self.model.to(device)
        self.model.eval()
        self._load_species_info()

    @classmethod
    def _load_species_info(cls):
        if cls._species_info is not None:
            return
        info_path = Path(__file__).resolve().parent / "wildlife_info.json"
        if info_path.exists():
            with open(info_path, "r", encoding="utf-8") as f:
                cls._species_info = json.load(f)
        else:
            cls._species_info = {}

    @staticmethod
    def get_species_info(class_name: str) -> Optional[Dict]:
        FastRCNNDetector._load_species_info()
        return FastRCNNDetector._species_info.get(class_name)

    def _find_checkpoint(self) -> Optional[str]:
        """查找训练好的 Faster R-CNN 权重文件"""
        if self.checkpoint_path and os.path.exists(self.checkpoint_path):
            return self.checkpoint_path
        base = Path(__file__).resolve().parent
        candidates = [
            base / "output" / "faster_rcnn_wildlife.pt",
            base / "output" / "faster_rcnn_wildlife_best.pt",
            base.parent / "wildlife_model" / "output" / "faster_rcnn_wildlife.pt",
            base.parent / "wildlife_model" / "output" / "faster_rcnn_wildlife_best.pt",
            "wildlife_model/output/faster_rcnn_wildlife.pt",
            "wildlife_model/output/faster_rcnn_wildlife_best.pt",
        ]
        for p in candidates:
            if os.path.exists(str(p)):
                return str(p)
        return None

    def detect(self, image_path: str, conf: float = 0.45, iou: float = 0.5) -> List[Dict]:
        img = cv2.imread(image_path)
        if img is None:
            raise RuntimeError(f"无法读取图片: {image_path}")
        img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        tensor = self._transforms(img_rgb).unsqueeze(0).to(self.device)
        with torch.no_grad():
            preds = self.model(tensor)[0]
        boxes = preds["boxes"].cpu().numpy()
        scores = preds["scores"].cpu().numpy()
        labels = preds["labels"].cpu().numpy()
        keep = self._nms(boxes, scores, iou)
        detections = []
        for i in keep:
            if scores[i] < conf:
                continue
            # Faster R-CNN 输出 1-index 标签（0=background），class_names 是 0-index，
            # 必须减 1 才能正确对应（与 YOLOv8 的 0-index 保持一致）
            cls_id = int(labels[i]) - 1
            name = self.class_names[cls_id] if 0 <= cls_id < len(self.class_names) else f"class_{labels[i]}"
            detections.append({
                "class_id": cls_id,
                "class_name": name,
                "confidence": round(float(scores[i]), 4),
                "bbox": [round(float(x), 1) for x in boxes[i]],
            })
        return detections

    def detect_with_details(self, image_path: str, conf: float = 0.45, iou: float = 0.5) -> Dict:
        t0 = time.time()
        detections = self.detect(image_path, conf, iou)
        elapsed = round((time.time() - t0) * 1000)
        class_counts: Dict[str, int] = {}
        for d in detections:
            name = d["class_name"]
            class_counts[name] = class_counts.get(name, 0) + 1
        species_info = {}
        for cls_name in class_counts:
            info = self.get_species_info(cls_name)
            if info:
                species_info[cls_name] = info
        return {
            "success": True,
            "total_count": len(detections),
            "inference_time_ms": elapsed,
            "class_counts": class_counts,
            "detections": detections,
            "species_info": species_info,
        }

    def render_detections(self, image_path: str, save_path: Optional[str] = None,
                          conf: float = 0.45, iou: float = 0.5) -> Optional[np.ndarray]:
        img = cv2.imread(image_path)
        if img is None:
            return None
        detections = self.detect(image_path, conf, iou)
        colors = self._generate_colors(len(self.class_names))
        for det in detections:
            x1, y1, x2, y2 = [int(v) for v in det["bbox"]]
            cls_id = det["class_id"]
            name = det["class_name"]
            conf_val = det["confidence"]
            rgb = colors[cls_id % len(colors)]
            color_bgr = (rgb[2], rgb[1], rgb[0])
            cv2.rectangle(img, (x1, y1), (x2, y2), color_bgr, 2)
            label = f"{name} {conf_val:.2f}"
            (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
            cv2.rectangle(img, (x1, y1 - th - 8), (x1 + tw + 4, y1), color_bgr, -1)
            cv2.putText(img, label, (x1 + 2, y1 - 4),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
        if save_path:
            os.makedirs(os.path.dirname(save_path) or ".", exist_ok=True)
            cv2.imwrite(save_path, img)
        return img

    def render_to_base64(self, image_path: str, conf: float = 0.45, iou: float = 0.5) -> str:
        img = self.render_detections(image_path, conf=conf, iou=iou)
        if img is None:
            return ""
        try:
            _, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 85])
        except Exception:
            _, buf = cv2.imencode(".jpg", img)
        return base64.b64encode(buf).decode("utf-8")

    def model_info(self) -> Dict:
        params = sum(p.numel() for p in self.model.parameters())
        ckpt = self._find_checkpoint()
        return {
            "model_path": ckpt or "torchvision::fasterrcnn_resnet50_fpn",
            "num_classes": len(self.class_names),
            "class_names": self.class_names,
            "device": self.device,
            "parameters": params,
            "from_checkpoint": self._from_checkpoint,
        }

    @staticmethod
    def _nms(boxes: np.ndarray, scores: np.ndarray, iou_thresh: float) -> List[int]:
        if len(boxes) == 0:
            return []
        x1 = boxes[:, 0]; y1 = boxes[:, 1]; x2 = boxes[:, 2]; y2 = boxes[:, 3]
        areas = (x2 - x1 + 1) * (y2 - y1 + 1)
        order = scores.argsort()[::-1]
        keep = []
        while len(order) > 0:
            i = order[0]
            keep.append(i)
            xx1 = np.maximum(x1[i], x1[order[1:]])
            yy1 = np.maximum(y1[i], y1[order[1:]])
            xx2 = np.minimum(x2[i], x2[order[1:]])
            yy2 = np.minimum(y2[i], y2[order[1:]])
            w = np.maximum(0.0, xx2 - xx1 + 1)
            h = np.maximum(0.0, yy2 - yy1 + 1)
            inter = w * h
            ovr = inter / (areas[i] + areas[order[1:]] - inter)
            inds = np.where(ovr <= iou_thresh)[0]
            order = order[inds + 1]
        return keep

    @staticmethod
    def _generate_colors(n: int) -> List[tuple]:
        colors = []
        for i in range(n):
            hsv = np.array([[[i / n * 179, 200, 255]]], dtype=np.uint8)
            bgr = cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR)[0][0]
            colors.append(tuple(int(c) for c in bgr[::-1]))
        return colors


# ============================================================
# 多模型注册表 — 游客可自由切换检测模型
# ============================================================
# 两种架构，同一数据集（11种野生动物）：
#   YOLOv8       — CNN 单阶段检测器（锚点自由，端到端卷积）
#   Faster R-CNN — CNN 两阶段检测器（RPN 区域提议 + ROI 分类回归）
# ============================================================
MODEL_REGISTRY: Dict[str, dict] = {
    "wildlife_best": {
        "id": "wildlife_best",
        "name": "YOLOv8 专项野生动物",
        "desc": "CNN 单阶段检测。端到端卷积，锚点自由。已用11种野生动物数据集微调训练。",
        "model_path": "",
        "icon": "🧠",
        "arch": "CNN 单阶段",
        "detector": "yolo",
    },
    "faster_rcnn": {
        "id": "faster_rcnn",
        "name": "Faster R-CNN 专项野生动物",
        "desc": "CNN 两阶段检测。RPN 区域提议 + ROI 分类回归，候选框机制。同样用11种野生动物数据集训练。",
        "model_path": "",
        "icon": "🎯",
        "arch": "CNN 两阶段",
        "detector": "faster_rcnn",
    },
}

_detectors: Dict[str, object] = {}


def get_detector(model_id: str = "wildlife_best"):
    """按模型 ID 获取检测器（懒加载 + 缓存）"""
    global _detectors
    if model_id not in _detectors:
        entry = MODEL_REGISTRY.get(model_id)
        if entry is None:
            raise ValueError(f"未知模型: {model_id}")
        d_type = entry.get("detector", "yolo")
        if d_type == "faster_rcnn":
            _detectors[model_id] = FastRCNNDetector(device="cpu")
        else:
            mp = entry["model_path"]
            if mp:
                base = Path(__file__).resolve().parent.parent
                mp = str(base / mp) if not os.path.isabs(mp) else mp
            _detectors[model_id] = WildlifeDetector(model_path=mp or None, device="cpu")
    return _detectors[model_id]


def get_model_list() -> List[Dict]:
    """返回可用模型列表（供前端选择器使用）"""
    result = []
    for mid, entry in MODEL_REGISTRY.items():
        try:
            d = get_detector(mid)
            info = d.model_info()
            result.append({
                "id": mid,
                "name": entry["name"],
                "desc": entry["desc"],
                "icon": entry["icon"],
                "arch": entry.get("arch", ""),
                "num_classes": info["num_classes"],
                "class_names": info["class_names"],
                "model_path": info["model_path"],
                "device": info["device"],
            })
        except Exception as e:
            result.append({
                "id": mid,
                "name": entry["name"],
                "desc": entry["desc"],
                "icon": entry["icon"],
                "arch": entry.get("arch", ""),
                "error": str(e),
            })
    return result


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="野生动物检测推理")
    parser.add_argument("image", help="输入图片路径")
    parser.add_argument("--save", action="store_true", help="保存标注图片")
    parser.add_argument("--json", action="store_true", help="JSON输出")
    parser.add_argument("--conf", type=float, default=0.25)
    parser.add_argument("--device", type=str, default="cpu")
    args = parser.parse_args()

    if not os.path.exists(args.image):
        print(f"[错误] 图片不存在: {args.image}")
        sys.exit(1)

    detector = WildlifeDetector(device=args.device)

    if args.json:
        details = detector.detect_with_details(args.image, conf=args.conf)
        print(json.dumps(details, ensure_ascii=False, indent=2))
    else:
        details = detector.detect_with_details(args.image, conf=args.conf)
        print(f"\n{'=' * 50}")
        print(f"  检测到 {details['total_count']} 个目标  ({details['inference_time_ms']}ms)")
        print(f"{'=' * 50}")
        for name, count in sorted(details.get("class_counts", {}).items(), key=lambda x: -x[1]):
            print(f"  {name}: {count}")
        for i, d in enumerate(details["detections"]):
            print(f"  [{i + 1}] {d['class_name']} conf={d['confidence']:.2%} bbox={d['bbox']}")

    if args.save:
        out = os.path.splitext(args.image)[0] + "_detected.jpg"
        detector.render_detections(args.image, save_path=out)
