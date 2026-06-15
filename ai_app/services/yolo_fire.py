from ultralytics import YOLO
import cv2

# ======================
# 1. 加载模型
# ======================
model = YOLO("fire.pt")   # 你的pt文件

# ======================
# 2. 读图片
# ======================
img_path = "test.jpg"
img = cv2.imread(img_path)

# ======================
# 3. 推理
# ======================
results = model(img)

# ======================
# 4. 结果解析
# ======================
for r in results:
    boxes = r.boxes
    for box in boxes:
        cls = int(box.cls[0])
        conf = float(box.conf[0])

        print("类别ID:", cls, "置信度:", conf)

# ======================
# 5. 可视化
# ======================
annotated = results[0].plot()
cv2.imshow("Fire Detection", annotated)
cv2.waitKey(0)