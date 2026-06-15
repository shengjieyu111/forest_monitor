import torch
import open_clip
from PIL import Image
import os

# =========================
# 1. 设备
# =========================
device = "cuda" if torch.cuda.is_available() else "cpu"

# =========================
# 2. 加载 CLIP 模型（自动下载 .pt）
# =========================
model, preprocess, tokenizer = open_clip.create_model_and_transforms(
    'ViT-B-32',
    pretrained='openai'
)

model = model.to(device)
model.eval()

# =========================
# 3. 北京常见鸟类（你系统的“类别库”）
# =========================
bird_classes = [
    "麻雀 House Sparrow",
    "喜鹊 Magpie",
    "乌鸦 Crow",
    "白鹭 Egret",
    "鸽子 Pigeon",
    "燕子 Swallow",
    "啄木鸟 Woodpecker",
    "八哥 Myna",
    "苍鹭 Heron",
    "鸥 Gull"
]

# =========================
# 4. 图像识别函数
# =========================
def predict(image_path):
    image = preprocess(Image.open(image_path).convert("RGB")).unsqueeze(0).to(device)

    text = tokenizer(bird_classes).to(device)

    with torch.no_grad():
        image_features = model.encode_image(image)
        text_features = model.encode_text(text)

        # 归一化
        image_features /= image_features.norm(dim=-1, keepdim=True)
        text_features /= text_features.norm(dim=-1, keepdim=True)

        # 相似度
        similarity = (100.0 * image_features @ text_features.T)
        probs = similarity.softmax(dim=-1)

    # 输出结果
    result = []
    for i, bird in enumerate(bird_classes):
        result.append((bird, float(probs[0][i])))

    # 排序
    result.sort(key=lambda x: x[1], reverse=True)

    return result


# =========================
# 5. 单张图片测试
# =========================
if __name__ == "__main__":

    image_path = "test.jpg"   # ← 改成你的图片

    if not os.path.exists(image_path):
        print("请放入图片 test.jpg")
        exit()

    results = predict(image_path)

    print("\n=== 北京鸟类识别结果（CLIP）===")
    for bird, score in results:
        print(f"{bird}: {score:.3f}")

    print("\n最可能结果：", results[0][0])