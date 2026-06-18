import base64
import colorsys
import io
import math
import os
from functools import lru_cache
from pathlib import Path


SPECIES_CLASSES = [
    {
        'label': '东北虎',
        'english': 'Amur tiger',
        'group': '兽类',
        'aliases': ['tiger with orange fur and black stripes', 'large striped big cat'],
        'level': '国家一级保护动物',
        'habitat': '针阔混交林、山地森林',
        'action': '立即上报林业主管部门，扩大巡护半径并避免人为靠近。',
    },
    {
        'label': '金钱豹',
        'english': 'Leopard',
        'group': '兽类',
        'aliases': ['spotted leopard', 'large cat with rosette spots'],
        'level': '国家一级保护动物',
        'habitat': '山地森林、灌丛、岩坡',
        'action': '保留影像证据，布设红外相机并减少夜间干扰。',
    },
    {
        'label': '梅花鹿',
        'english': 'Sika deer',
        'group': '兽类',
        'aliases': ['sika deer with antlers', 'brown deer in woodland'],
        'level': '国家一级保护动物',
        'habitat': '林缘草地、阔叶林',
        'action': '记录活动时间和位置，关注栖息地连通性。',
    },
    {
        'label': '野猪',
        'english': 'Wild boar',
        'group': '兽类',
        'aliases': ['dark wild boar', 'stocky pig-like animal in forest'],
        'level': '重点生态监测物种',
        'habitat': '阔叶林、灌丛、农林交错带',
        'action': '评估人兽冲突风险，设置预警标识并加强夜间巡护。',
    },
    {
        'label': '赤狐',
        'english': 'Red fox',
        'group': '兽类',
        'aliases': ['red fox in snow', 'fox with pointed ears and bushy tail'],
        'level': '三有保护动物',
        'habitat': '森林、草地、灌丛',
        'action': '观察种群活动频率，避免投喂和近距离接触。',
    },
    {
        'label': '猕猴',
        'english': 'Rhesus macaque',
        'group': '兽类',
        'aliases': ['rhesus monkey', 'macaque primate in forest'],
        'level': '国家二级保护动物',
        'habitat': '常绿阔叶林、山地林区',
        'action': '提醒游客保持距离，监测群体规模与迁移路线。',
    },
    {
        'label': '长颈鹿',
        'english': 'Giraffe',
        'group': '兽类',
        'aliases': ['giraffe with long neck and brown patches', 'tall spotted giraffe'],
        'level': '重点生态监测物种',
        'habitat': '疏林草原、开阔林地',
        'action': '记录个体活动范围和取食植被，关注迁移通道与人为干扰。',
    },
    {
        'label': '喜鹊',
        'english': 'Oriental magpie',
        'group': '鸟类',
        'aliases': ['black and white magpie with long tail', 'oriental magpie perched on branch'],
        'level': '三有保护动物',
        'habitat': '林缘、城市公园、针阔混交林',
        'action': '记录巢位与活动区域，繁殖季减少近距离干扰。',
    },
    {
        'label': '麻雀',
        'english': 'Tree sparrow',
        'group': '鸟类',
        'aliases': ['small brown sparrow', 'tree sparrow on branch'],
        'level': '三有保护动物',
        'habitat': '林缘、灌丛、居民点周边',
        'action': '记录小型鸟类群落变化，关注食源植物和灌丛保护。',
    },
    {
        'label': '大山雀',
        'english': 'Great tit',
        'group': '鸟类',
        'aliases': ['great tit bird with black head and yellow body', 'small woodland tit bird'],
        'level': '三有保护动物',
        'habitat': '阔叶林、针阔混交林、林缘',
        'action': '保留林下灌丛与枯木环境，监测鸣禽多样性。',
    },
    {
        'label': '啄木鸟',
        'english': 'Woodpecker',
        'group': '鸟类',
        'aliases': ['woodpecker on tree trunk', 'bird clinging to bark'],
        'level': '三有保护动物',
        'habitat': '成熟林、针阔混交林',
        'action': '保护枯立木和老龄树，记录啄木活动热点。',
    },
    {
        'label': '红隼',
        'english': 'Common kestrel',
        'group': '鸟类',
        'aliases': ['small falcon hovering', 'brown raptor bird'],
        'level': '国家二级保护动物',
        'habitat': '山地林缘、开阔坡地',
        'action': '记录猛禽活动轨迹，减少无人机和高噪声干扰。',
    },
    {
        'label': '环颈雉',
        'english': 'Ring-necked pheasant',
        'group': '鸟类',
        'aliases': ['colorful pheasant on ground', 'ring necked pheasant in grass'],
        'level': '三有保护动物',
        'habitat': '林缘草地、灌丛、农林交错带',
        'action': '记录地面鸟类活动热点，防范非法捕猎。',
    },
    {
        'label': '白鹭',
        'english': 'Egret',
        'group': '鸟类',
        'aliases': ['white egret wading bird', 'long legged white water bird'],
        'level': '三有保护动物',
        'habitat': '湿地、河湖、林缘水域',
        'action': '保护湿地水位和觅食区，减少繁殖季噪声干扰。',
    },
    {
        'label': '蜥蜴',
        'english': 'Lizard',
        'group': '爬行动物',
        'aliases': ['small lizard on rock', 'reptile with long tail'],
        'level': '三有保护动物',
        'habitat': '向阳石坡、林缘草地、灌丛',
        'action': '记录爬行动物活动温度和生境，避免翻动石块破坏微栖息地。',
    },
    {
        'label': '蛇类',
        'english': 'Snake',
        'group': '爬行动物',
        'aliases': ['snake on forest floor', 'long slender reptile'],
        'level': '三有保护动物',
        'habitat': '林下落叶层、灌丛、近水区域',
        'action': '保持安全距离并标注位置，提醒巡护人员注意人蛇冲突风险。',
    },
    {
        'label': '龟类',
        'english': 'Turtle',
        'group': '爬行动物',
        'aliases': ['turtle with shell near water', 'freshwater turtle'],
        'level': '重点生态监测物种',
        'habitat': '溪流、湿地、静水浅滩',
        'action': '保护近水产卵地，记录水体质量与人为干扰。',
    },
    {
        'label': '油松',
        'english': 'Chinese pine',
        'group': '植物',
        'aliases': ['chinese pine needles and cones', 'pine tree with needle leaves'],
        'level': '鹫峰常见乡土树种',
        'habitat': '山坡阳面、针叶林',
        'action': '记录针叶林健康状况，关注松材线虫和枯梢风险。',
    },
    {
        'label': '侧柏',
        'english': 'Chinese arborvitae',
        'group': '植物',
        'aliases': ['arborvitae scale leaves', 'cypress like evergreen foliage'],
        'level': '鹫峰常见乡土树种',
        'habitat': '山地阳坡、岩石坡地',
        'action': '监测常绿树冠色泽变化，关注干旱胁迫。',
    },
    {
        'label': '栓皮栎',
        'english': 'Chinese cork oak',
        'group': '植物',
        'aliases': ['oak leaves and acorns', 'cork oak bark and broad leaves'],
        'level': '鹫峰常见阔叶树种',
        'habitat': '落叶阔叶林、山坡林地',
        'action': '记录落叶阔叶林物候，关注病虫害和更新幼苗。',
    },
    {
        'label': '黄栌',
        'english': 'Smoke tree',
        'group': '植物',
        'aliases': ['smoke tree red leaves', 'cotinus autumn foliage'],
        'level': '鹫峰观赏与生态树种',
        'habitat': '山坡灌丛、林缘',
        'action': '记录秋色物候变化，监测游客活动对灌丛的影响。',
    },
    {
        'label': '蕨类植物',
        'english': 'Fern',
        'group': '植物',
        'aliases': ['green fern fronds', 'fern leaves on forest floor'],
        'level': '林下生态指示植物',
        'habitat': '阴湿林下、沟谷、岩壁',
        'action': '记录阴湿生境稳定性，避免踩踏林下植被。',
    },
    {
        'label': '野花草本',
        'english': 'Wildflower herb',
        'group': '植物',
        'aliases': ['wild flowers in grass', 'small flowering herbaceous plant'],
        'level': '林下植物多样性指标',
        'habitat': '林缘草地、山坡、步道周边',
        'action': '记录开花物候和分布点，避免采摘和踩踏。',
    },
]

WILDLIFE_CLASSES = SPECIES_CLASSES

ANIMAL_COCO_NAMES = {
    'bird', 'cat', 'dog', 'horse', 'sheep', 'cow', 'elephant', 'bear', 'zebra', 'giraffe'
}


def analyze_wildlife(image_file, mode='ensemble', category_hint='auto'):
    from PIL import Image

    image = Image.open(image_file).convert('RGB')
    mode = mode if mode in {'detector', 'classifier', 'ensemble'} else 'ensemble'
    category_hint = category_hint if category_hint in {'auto', '兽类', '鸟类', '爬行动物', '植物'} else 'auto'
    detections, detector_meta = ([], {'status': 'skipped', 'message': '未选择目标检测模型'})
    classes, classifier_meta = ([], {'status': 'skipped', 'message': '未选择图像分类模型'})

    if mode in {'detector', 'ensemble'}:
        detections, detector_meta = run_detector(image)
    if mode in {'classifier', 'ensemble'}:
        classes, classifier_meta = run_classifier(image, detections, category_hint)

    if mode == 'ensemble':
        summary = build_fusion_summary(detections, classes)
    elif mode == 'detector':
        summary = build_detection_summary(detections)
    else:
        summary = build_classification_summary(classes)

    annotated = annotate_image(image, detections, classes)
    return {
        'mode': mode,
        'image': {
            'width': image.width,
            'height': image.height,
            'annotated': image_to_data_url(annotated),
        },
        'models': {
            'detector': detector_meta,
            'classifier': classifier_meta,
        },
        'detections': detections,
        'classifications': classes,
        'summary': summary,
        'recommendations': build_recommendations(summary, detections, classes),
    }


def run_detector(image):
    try:
        model = get_yolo_model()
        if model is None:
            raise RuntimeError('未找到本地 YOLO 权重 yolov8n.pt，已切换为离线演示检测器')
        import numpy as np

        result = model(np.array(image), verbose=False, conf=0.18)[0]
        detections = []
        names = result.names
        for box in result.boxes:
            cls_id = int(box.cls[0])
            name = str(names.get(cls_id, cls_id))
            if name not in ANIMAL_COCO_NAMES:
                continue
            x1, y1, x2, y2 = [float(value) for value in box.xyxy[0]]
            detections.append({
                'label': translate_coco_name(name),
                'raw_label': name,
                'confidence': round(float(box.conf[0]), 3),
                'box': [round(x1), round(y1), round(x2), round(y2)],
                'model': 'YOLOv8n 目标检测',
            })
        return detections, {
            'name': 'YOLOv8n 目标检测',
            'type': '目标检测',
            'status': 'ready',
            'message': '已完成动物目标检测与边界框解析',
        }
    except Exception as error:
        detections = fallback_detections(image)
        return detections, {
            'name': 'YOLOv8n 目标检测',
            'type': '目标检测',
            'status': 'fallback',
            'message': str(error),
        }


def run_classifier(image, detections=None, category_hint='auto'):
    subject_image = crop_subject(image, detections or [])
    try:
        model_bundle = get_clip_model()
        if model_bundle is None:
            raise RuntimeError('CLIP 权重不可用，已切换为离线特征分类器')
        model, preprocess, tokenizer, device = model_bundle
        import torch

        prompts = []
        prompt_groups = []
        for index, item in enumerate(WILDLIFE_CLASSES):
            item_prompts = [
                f'a clear wildlife camera photo of {item["english"]}',
                f'a close-up field monitoring photo of {item["english"]}',
                f'{item["english"]}, {item["group"]}, {item["habitat"]}',
            ]
            item_prompts.extend(item.get('aliases', []))
            prompts.extend(item_prompts)
            prompt_groups.extend([index] * len(item_prompts))
        image_tensor = preprocess(subject_image).unsqueeze(0).to(device)
        text_tensor = tokenizer(prompts).to(device)
        with torch.no_grad():
            image_features = model.encode_image(image_tensor)
            text_features = model.encode_text(text_tensor)
            image_features /= image_features.norm(dim=-1, keepdim=True)
            text_features /= text_features.norm(dim=-1, keepdim=True)
            prompt_scores = (100.0 * image_features @ text_features.T)[0]
            class_scores = []
            for index in range(len(WILDLIFE_CLASSES)):
                indices = [prompt_index for prompt_index, group in enumerate(prompt_groups) if group == index]
                grouped = prompt_scores[indices]
                class_scores.append(grouped.max() * .7 + grouped.mean() * .3)
            probs = torch.stack(class_scores).softmax(dim=0).detach().cpu().numpy()
        probs = apply_category_hint(probs, category_hint)
        ranked = build_classification_rows(probs, 'CLIP ViT-B-32 多提示词图像分类')
        return ranked, {
            'name': 'CLIP ViT-B-32 图像分类',
            'type': '图像分类',
            'status': 'ready',
            'message': '已完成图像语义编码与物种文本匹配',
        }
    except Exception as error:
        ranked = fallback_classification(subject_image, category_hint)
        return ranked, {
            'name': 'CLIP ViT-B-32 图像分类',
            'type': '图像分类',
            'status': 'fallback',
            'message': f'{error}；已先裁剪动物主体区域再进行离线分类',
        }


@lru_cache(maxsize=1)
def get_yolo_model():
    weight_path = Path(__file__).resolve().parents[1] / 'models' / 'yolov8n.pt'
    if not weight_path.exists():
        return None
    config_dir = Path(__file__).resolve().parents[1] / 'models' / 'ultralytics_config'
    (config_dir / 'Ultralytics').mkdir(parents=True, exist_ok=True)
    (config_dir / 'matplotlib').mkdir(parents=True, exist_ok=True)
    os.environ.setdefault('YOLO_CONFIG_DIR', str(config_dir))
    os.environ.setdefault('MPLCONFIGDIR', str(config_dir / 'matplotlib'))
    from ultralytics import YOLO

    return YOLO(str(weight_path))


@lru_cache(maxsize=1)
def get_clip_model():
    if os.getenv('FOREST_ENABLE_ONLINE_CLIP', '0') != '1':
        return None
    try:
        import open_clip
        import torch

        device = 'cuda' if torch.cuda.is_available() else 'cpu'
        model, _, preprocess = open_clip.create_model_and_transforms('ViT-B-32', pretrained='openai')
        tokenizer = open_clip.get_tokenizer('ViT-B-32')
        model = model.to(device)
        model.eval()
        return model, preprocess, tokenizer, device
    except Exception:
        return None


def fallback_detections(image):
    width, height = image.size
    box, confidence = estimate_subject_box(image)
    if not box:
        box = [round(width * .18), round(height * .18), round(width * .82), round(height * .82)]
        confidence = .38
    return [{
        'label': '疑似野生动物目标',
        'raw_label': 'wildlife_candidate',
        'confidence': round(confidence, 3),
        'box': box,
        'model': '离线显著性目标检测',
    }]


def fallback_classification(image, category_hint='auto'):
    small = image.resize((96, 96)).convert('RGB')
    pixels = list(small.getdata())
    all_hsv_pixels = [colorsys.rgb_to_hsv(r / 255, g / 255, b / 255) for r, g, b in pixels]
    white_context = ratio(all_hsv_pixels, lambda h, s, v: s < .2 and v > .76)
    foreground_pixels = [
        item for item in all_hsv_pixels
        if not (item[1] < .2 and item[2] > .76)
    ]
    if len(foreground_pixels) > len(all_hsv_pixels) * .08:
        tan_or_warm = ratio(foreground_pixels, lambda h, s, v: (h <= .18 or h >= .95) and s > .16 and v > .18)
        if tan_or_warm > .18:
            foreground_pixels = [
                item for item in foreground_pixels
                if not (.22 <= item[0] <= .46 and item[1] > .18 and item[2] > .25)
            ] or foreground_pixels
        hsv_pixels = foreground_pixels
    else:
        hsv_pixels = all_hsv_pixels
    total = len(hsv_pixels)
    brightness = sum(v for _, _, v in hsv_pixels) / total
    saturation = sum(s for _, s, _ in hsv_pixels) / total
    orange = ratio(hsv_pixels, lambda h, s, v: .055 <= h <= .13 and s > .28 and v > .25)
    tiger_orange = ratio(hsv_pixels, lambda h, s, v: .055 <= h <= .095 and s > .45 and v > .3)
    giraffe_tan = ratio(hsv_pixels, lambda h, s, v: .095 <= h <= .17 and .18 < s < .7 and .32 < v < .92)
    yellow_brown = ratio(hsv_pixels, lambda h, s, v: .08 <= h <= .18 and s > .18 and .18 < v < .82)
    green = ratio(hsv_pixels, lambda h, s, v: .22 <= h <= .46 and s > .18)
    white = ratio(hsv_pixels, lambda h, s, v: s < .22 and v > .72)
    dark = ratio(hsv_pixels, lambda h, s, v: v < .28)
    gray_brown = ratio(hsv_pixels, lambda h, s, v: s < .34 and .22 < v < .66)
    blue_water = ratio(hsv_pixels, lambda h, s, v: .48 <= h <= .66 and s > .16)
    red_orange = ratio(hsv_pixels, lambda h, s, v: (h <= .055 or h >= .95) and s > .22 and v > .22)
    black = ratio(hsv_pixels, lambda h, s, v: v < .18)
    tan = ratio(hsv_pixels, lambda h, s, v: .09 <= h <= .17 and .12 < s < .55 and .38 < v < .9)
    vivid_color = ratio(hsv_pixels, lambda h, s, v: s > .48 and v > .38)
    flower_color = ratio(hsv_pixels, lambda h, s, v: (h <= .04 or .70 <= h <= .95 or .11 <= h <= .18) and s > .35 and v > .45)
    leaf_green = ratio(hsv_pixels, lambda h, s, v: .24 <= h <= .42 and s > .22 and v > .22)
    needle_green = ratio(hsv_pixels, lambda h, s, v: .20 <= h <= .36 and .18 < s < .55 and .16 < v < .56)
    bark_brown = ratio(hsv_pixels, lambda h, s, v: .06 <= h <= .16 and .12 < s < .55 and .16 < v < .58)
    edge = edge_strength(small)

    plant_context = max(0, leaf_green - red_orange * .35) + flower_color * .45
    bird_context = white * .6 + vivid_color * .38 + edge * .3
    reptile_context = edge * .45 + green * .35 + dark * .25 + bark_brown * .25
    raw = []
    for item in WILDLIFE_CLASSES:
        label = item['label']
        group = item.get('group', '')
        if label == '东北虎':
            score = .42 + tiger_orange * 3.4 + black * 1.15 + edge * .95 + saturation * .18 - white_context * 3.0
        elif label == '金钱豹':
            score = .48 + yellow_brown * 2.2 + edge * 1.25 + dark * .35
        elif label == '梅花鹿':
            score = .45 + yellow_brown * .95 + green * .55 + brightness * .16
        elif label == '野猪':
            score = .52 + dark * 1.8 + gray_brown * 1.1 + green * .35
        elif label == '赤狐':
            score = .50 + red_orange * 3.2 + yellow_brown * .95 + orange * .25 + gray_brown * .75 + edge * .28 + white_context * 4.0
        elif label == '猕猴':
            score = .45 + gray_brown * 1.55 + green * .42 + brightness * .18
        elif label == '长颈鹿':
            score = .60 + giraffe_tan * 3.2 + tan * 1.3 + yellow_brown * 1.1 + edge * .45 + black * .2
        elif label == '白鹭':
            score = .42 + white * 2.7 + blue_water * .85 + brightness * .35 - red_orange * .8
        elif label == '喜鹊':
            score = .45 + white * .95 + black * 1.4 + edge * .75
        elif label == '麻雀':
            score = .44 + gray_brown * 1.35 + yellow_brown * .75 + edge * .55
        elif label == '大山雀':
            score = .42 + vivid_color * .8 + black * .8 + yellow_brown * .55 + edge * .45
        elif label == '啄木鸟':
            score = .42 + bark_brown * 1.35 + black * .65 + edge * 1.1
        elif label == '红隼':
            score = .42 + yellow_brown * 1.2 + edge * .9 + brightness * .18
        elif label == '环颈雉':
            score = .43 + vivid_color * 1.05 + green * .45 + yellow_brown * .75 + edge * .75
        elif label == '蜥蜴':
            score = .43 + reptile_context + green * .95 + edge * .65
        elif label == '蛇类':
            score = .42 + reptile_context + edge * 1.05 + dark * .55
        elif label == '龟类':
            score = .42 + reptile_context + dark * .65 + blue_water * .55 + edge * .55
        elif label == '油松':
            score = .42 + needle_green * 2.2 + edge * .55 + plant_context * .55
        elif label == '侧柏':
            score = .42 + needle_green * 1.7 + leaf_green * .7 + edge * .35 + plant_context * .5
        elif label == '栓皮栎':
            score = .42 + leaf_green * 1.15 + bark_brown * 1.15 + yellow_brown * .45 + plant_context * .45
        elif label == '黄栌':
            score = .42 + red_orange * 1.2 + yellow_brown * 1.0 + leaf_green * .45 + plant_context * .35
        elif label == '蕨类植物':
            score = .42 + leaf_green * 1.65 + green * .85 + edge * .65 + plant_context * .7
        elif label == '野花草本':
            score = .42 + flower_color * 2.4 + leaf_green * .75 + plant_context * .65
        else:
            score = .40 + {'鸟类': bird_context, '爬行动物': reptile_context, '植物': plant_context}.get(group, edge * .2)
        if group == '植物':
            score += plant_context * .7 - (dark + black) * .2
        elif group == '鸟类':
            score += bird_context * .45 - plant_context * .25
        elif group == '爬行动物':
            score += reptile_context * .35 - white_context * .2
        raw.append(score)
    raw = apply_group_prior(raw, category_hint, {
        '植物': plant_context * 1.5 + leaf_green + flower_color * 1.2 + needle_green * .8,
        '鸟类': bird_context + white * 1.2 + vivid_color * .6 + edge * .35,
        '爬行动物': reptile_context + edge * .6 + dark * .35 + bark_brown * .35,
        '兽类': red_orange * 1.3 + yellow_brown + gray_brown * .85 + dark * .55 + orange * .55,
    })
    probs = softmax(raw)
    return build_classification_rows(probs, '离线图像特征分类')


def crop_subject(image, detections):
    if detections:
        best = max(detections, key=lambda item: item.get('confidence', 0))
        x1, y1, x2, y2 = best.get('box', [0, 0, image.width, image.height])
        pad_x = round((x2 - x1) * .08)
        pad_y = round((y2 - y1) * .08)
        box = (
            max(0, x1 - pad_x),
            max(0, y1 - pad_y),
            min(image.width, x2 + pad_x),
            min(image.height, y2 + pad_y),
        )
        if box[2] - box[0] > 20 and box[3] - box[1] > 20:
            return image.crop(box)
    box, _ = estimate_subject_box(image)
    if box:
        return image.crop(tuple(box))
    return image


def estimate_subject_box(image):
    width, height = image.size
    small = image.resize((120, 120)).convert('RGB')
    pixels = small.load()
    border = []
    for i in range(120):
        border.extend([pixels[i, 0], pixels[i, 119], pixels[0, i], pixels[119, i]])
    bg = tuple(sum(pixel[channel] for pixel in border) / len(border) for channel in range(3))
    scores = []
    points = []
    for y in range(120):
        for x in range(120):
            r, g, b = pixels[x, y]
            h, s, v = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
            color_distance = math.sqrt((r - bg[0]) ** 2 + (g - bg[1]) ** 2 + (b - bg[2]) ** 2) / 441.7
            center_weight = 1 - min(1, math.sqrt((x - 60) ** 2 + (y - 60) ** 2) / 85)
            score = color_distance * .72 + s * .24 + center_weight * .18
            scores.append(score)
    mean_score = sum(scores) / len(scores)
    variance = sum((score - mean_score) ** 2 for score in scores) / len(scores)
    threshold = max(.22, mean_score + math.sqrt(variance) * .55)
    index = 0
    for y in range(120):
        for x in range(120):
            if scores[index] >= threshold:
                points.append((x, y))
            index += 1
    if len(points) < 80 or len(points) > 120 * 120 * .72:
        return None, .38
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    x1, x2 = min(xs), max(xs)
    y1, y2 = min(ys), max(ys)
    pad = 8
    box = [
        round(max(0, (x1 - pad) / 120 * width)),
        round(max(0, (y1 - pad) / 120 * height)),
        round(min(width, (x2 + pad) / 120 * width)),
        round(min(height, (y2 + pad) / 120 * height)),
    ]
    confidence = min(.82, max(.42, mean_score + math.sqrt(variance) + .22))
    return box, confidence


def ratio(items, predicate):
    if not items:
        return 0
    return sum(1 for item in items if predicate(*item)) / len(items)


def apply_category_hint(probs, category_hint):
    values = [float(value) for value in probs]
    if category_hint in {'兽类', '鸟类', '爬行动物', '植物'}:
        values = [
            value * (1.8 if item.get('group') == category_hint else .35)
            for value, item in zip(values, WILDLIFE_CLASSES)
        ]
    total = sum(values) or 1
    return [value / total for value in values]


def apply_group_prior(raw, category_hint, group_scores):
    values = list(raw)
    if category_hint in {'兽类', '鸟类', '爬行动物', '植物'}:
        return [
            value + (1.35 if item.get('group') == category_hint else -1.25)
            for value, item in zip(values, WILDLIFE_CLASSES)
        ]
    best_group = max(group_scores, key=group_scores.get)
    second_score = sorted(group_scores.values(), reverse=True)[1]
    if group_scores[best_group] - second_score < .35:
        return values
    return [
        value + (.55 if item.get('group') == best_group else -.28)
        for value, item in zip(values, WILDLIFE_CLASSES)
    ]


def edge_strength(image):
    gray = image.convert('L')
    width, height = gray.size
    values = gray.load()
    total = 0
    count = 0
    for y in range(1, height, 2):
        for x in range(1, width, 2):
            total += abs(values[x, y] - values[x - 1, y])
            total += abs(values[x, y] - values[x, y - 1])
            count += 2
    return min(1, (total / max(count, 1)) / 70)


def softmax(values):
    max_value = max(values)
    exps = [math.exp(value - max_value) for value in values]
    total = sum(exps)
    return [value / total for value in exps]


def build_classification_rows(probs, model_name):
    rows = []
    for item, score in zip(WILDLIFE_CLASSES, probs):
        rows.append({
            'label': item['label'],
            'english': item['english'],
            'group': item.get('group', '野生物种'),
            'level': item['level'],
            'habitat': item['habitat'],
            'action': item['action'],
            'confidence': round(float(score), 3),
            'model': model_name,
        })
    rows.sort(key=lambda item: item['confidence'], reverse=True)
    return rows[:5]


def build_fusion_summary(detections, classes):
    top = classes[0] if classes else None
    detection_count = len(detections)
    confidence = round(((top['confidence'] if top else 0) + min(1, detection_count / 3)) / 2, 3)
    return {
        'title': top['label'] if top else '疑似野生动物活动',
        'subtitle': top['level'] if top else '需要人工复核',
        'confidence': confidence,
        'evidence': f'检测到 {detection_count} 个目标，分类模型 Top1 为 {top["label"] if top else "未知"}',
        'risk': protection_risk(top, detection_count),
    }


def build_detection_summary(detections):
    count = len(detections)
    avg = sum(item['confidence'] for item in detections) / count if count else 0
    return {
        'title': f'检测到 {count} 个动物目标',
        'subtitle': 'YOLO 边界框识别结果',
        'confidence': round(avg, 3),
        'evidence': '目标检测模型已输出位置、类别与置信度',
        'risk': '需复核',
    }


def build_classification_summary(classes):
    top = classes[0] if classes else None
    return {
        'title': top['label'] if top else '未识别到明确物种',
        'subtitle': top['level'] if top else '需要人工复核',
        'confidence': top['confidence'] if top else 0,
        'evidence': f'分类模型 Top1 为 {top["label"]}' if top else '分类置信度不足',
        'risk': protection_risk(top, 1 if top else 0),
    }


def protection_risk(top, detection_count):
    if not top:
        return '需复核'
    if '一级' in top['level']:
        return '重点保护'
    if detection_count >= 2 or '二级' in top['level']:
        return '持续监测'
    return '常规记录'


def build_recommendations(summary, detections, classes):
    top = classes[0] if classes else None
    items = [
        '把照片、时间和大致地点一起记录下来，这会让一次普通游览变成有价值的自然观察。',
        'AI 识别结果适合作为科普参考；如果置信度不高，可以多拍几张不同角度的清晰照片再比对。',
    ]
    if detections:
        items.append('目标框可以帮助你观察主体位置，拍摄时尽量让物种完整出现在画面中。')
    if top:
        group = top.get('group', '')
        if group == '植物':
            items.append(f'{top["label"]}常见于{top["habitat"]}，观察时可留意叶形、花果、树皮和周边生境。')
            items.append('请只拍照不采摘，让花果继续为昆虫、鸟类和小型动物提供食物。')
        elif group == '鸟类':
            items.append(f'{top["label"]}常活动于{top["habitat"]}，可以观察羽色、鸣叫、停栖位置和飞行方式。')
            items.append('观鸟时保持安静和距离，不靠近巢区，不用声音诱鸟。')
        elif group == '爬行动物':
            items.append(f'{top["label"]}多出现在{top["habitat"]}，它们对温度和微生境变化很敏感。')
            items.append('遇到爬行动物不要触碰或驱赶，沿步道慢行并保持安全距离。')
        else:
            items.append(f'{top["label"]}常依赖{top["habitat"]}提供食物、隐蔽和活动空间。')
            items.append('偶遇兽类时不要围观或投喂，给它留出离开的通道。')
    if summary['risk'] == '重点保护':
        items.append('如果识别到重点保护物种，请减少停留和打扰，把观察记录交给景区或专业人员。')
    return items


def annotate_image(image, detections, classes):
    from PIL import ImageDraw, ImageFont

    annotated = image.copy()
    draw = ImageDraw.Draw(annotated)
    font = ImageFont.load_default()
    colors = ['#5f9175', '#b69a61', '#b8756d', '#6f9d90']
    for index, item in enumerate(detections):
        color = colors[index % len(colors)]
        x1, y1, x2, y2 = item['box']
        draw.rectangle([x1, y1, x2, y2], outline=color, width=4)
        label = f"{item['label']} {item['confidence']:.2f}"
        text_box = draw.textbbox((x1, y1), label, font=font)
        draw.rectangle([text_box[0] - 4, text_box[1] - 4, text_box[2] + 4, text_box[3] + 4], fill=color)
        draw.text((x1, max(0, y1 - 2)), label, fill='white', font=font)
    if classes:
        top = classes[0]
        label = f"Top1: {top['label']} {top['confidence']:.2f}"
        draw.rectangle([14, 14, 230, 42], fill='#1d2b23')
        draw.text((22, 23), label, fill='white', font=font)
    return annotated


def image_to_data_url(image):
    buffer = io.BytesIO()
    image.save(buffer, format='JPEG', quality=88)
    encoded = base64.b64encode(buffer.getvalue()).decode('ascii')
    return f'data:image/jpeg;base64,{encoded}'


def translate_coco_name(name):
    mapping = {
        'bird': '鸟类',
        'cat': '猫科动物',
        'dog': '犬科动物',
        'horse': '马科动物',
        'sheep': '羊类',
        'cow': '牛类',
        'elephant': '象类',
        'bear': '熊类',
        'zebra': '斑马',
        'giraffe': '长颈鹿',
    }
    return mapping.get(name, name)
