"""
清理翼型数据文件夹：删除重复的 UIUC 数据文件
保留原有 99 点版本，删除重复的 35 点版本
"""

import os

FOILS_DIR = r"c:\Users\ASUS\Desktop\Databaselab\Bigwork\AEDS\source-data\NACAdata\foils"

# 原有文件的精确文件名（99点版本）——带空格
originals_with_space = [
    "NACA 0006.csv",
    "NACA 0009.csv",
    "NACA 0015.csv",
    "NACA 1410.csv",
    "NACA 2412.csv",
    "NACA 2421.csv",
    "NACA 4421.csv",
]

# 对应的 UIUC 重复文件（35点版本）——带下划线
duplicates_from_uiuc = [
    "NACA_0006.csv",
    "NACA_0009.csv",
    "NACA_0015.csv",
    "NACA_1410.csv",
    "NACA_2412.csv",
    "NACA_2421.csv",
    "NACA_4421.csv",
]

also_dedup = [
    "NACA_0010.csv",         # 没有原版，但检查 NACA 0010 在原有?
    "NACA_1408.csv",
    "NACA_2410.csv",
    "NACA_4412.csv",
    "NACA_4415.csv",
    "NACA_0018.csv",
    "NACA_0021.csv",
    "NACA_0024.csv",
    "NACA_2408.csv",
    "NACA_2415.csv",
    "NACA_2418.csv",
    "NACA_2424.csv",
    "NACA_4418.csv",
    "NACA_4424.csv",
    "NACA_23015.csv",
    "NACA_23018.csv",
    "NACA_23021.csv",
    "NACA_23024.csv",
]

all_files = [f for f in os.listdir(FOILS_DIR) if f.endswith(".csv")]
print(f"当前文件总数: {len(all_files)}")

# 统计删除
deleted = 0
kept = 0

# 删除重复的 UIUC 文件
for dup in duplicates_from_uiuc:
    path = os.path.join(FOILS_DIR, dup)
    if os.path.exists(path):
        os.remove(path)
        print(f"[删除] {dup} (被原版 99 点版本替代)")
        deleted += 1
    else:
        kept += 1

# 删除其他非 NACA 四位数标准的 UIUC 文件（只保留 4 位和 5 位 NACA 编码）
# 保留：naca4位(naca0024, naca2412等) 和 naca5位(naca23012等)
# 删除：特殊命名(naca-1_cowl, nacacyh, nacam12等)
special_cases = [
    "NACA-1_COWL.csv",
    "NACA_CYH.csv",
    "NACA_M12.csv",
    "NACA_M18.csv",
    "NACA_M2.csv",
    "NACA_M3.csv",
    "NACA_M6.csv",
]
for sc in special_cases:
    path = os.path.join(FOILS_DIR, sc)
    if os.path.exists(path):
        os.remove(path)
        print(f"[删除] {sc} (非标准 NACA 翼型)")
        deleted += 1

remaining = [f for f in os.listdir(FOILS_DIR) if f.endswith(".csv")]
print(f"\n删除: {deleted} 个文件, 剩余: {len(remaining)} 个文件")

# 统计坐标点数统计
print(f"\n{'='*60}")
print("翼型坐标点数分布统计")
print(f"{'='*60}")
total_pts = 0
count_by_pts = {}
for f in sorted(remaining):
    with open(os.path.join(FOILS_DIR, f)) as fh:
        pts = len(fh.readlines()) - 1
    total_pts += pts
    count_by_pts[pts] = count_by_pts.get(pts, 0) + 1

for pts, count in sorted(count_by_pts.items()):
    print(f"  {pts} 点: {count} 个翼型")
print(f"总计: {len(remaining)} 个翼型, {total_pts} 个坐标点")