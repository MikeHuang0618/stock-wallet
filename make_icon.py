"""產生 app 圖示 icon.ico — 金色圓幣 + 上升走勢線。"""
from PIL import Image, ImageDraw

S = 256
img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
d = ImageDraw.Draw(img)

# 外圈金色漸層 (用多層同心圓模擬 radial gradient)
cx = cy = S / 2
R = S * 0.47
inner = (245, 217, 139)   # 亮金
outer = (176, 132, 55)    # 暗金
steps = 120
for i in range(steps, 0, -1):
    t = i / steps
    r = R * t
    col = tuple(int(outer[j] + (inner[j] - outer[j]) * (1 - t)) for j in range(3))
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=col + (255,))

# 內圈深色底,凸顯走勢線
ir = R * 0.74
d.ellipse([cx - ir, cy - ir, cx + ir, cy + ir], fill=(28, 22, 10, 255))
# 內圈金邊
d.ellipse([cx - ir, cy - ir, cx + ir, cy + ir], outline=(245, 217, 139, 255), width=4)

# 上升走勢折線
pts = [(0.30, 0.66), (0.42, 0.56), (0.52, 0.62), (0.66, 0.42), (0.74, 0.36)]
px = [(cx - R + 2 * R * x, cy - R + 2 * R * y) for x, y in pts]
d.line(px, fill=(245, 217, 139, 255), width=11, joint="curve")
for p in px:
    d.ellipse([p[0] - 6, p[1] - 6, p[0] + 6, p[1] + 6], fill=(255, 240, 200, 255))
# 箭頭
ex, ey = px[-1]
d.polygon([(ex + 20, ey - 20), (ex - 6, ey - 26), (ex + 26, ey + 4)], fill=(56, 211, 159, 255))

img.save("icon.ico", sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
img.save("icon.png")
print("icon.ico saved")
