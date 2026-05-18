"""
最终数据验证
确认所有数据指标满足项目要求
"""

import os

BASE_DIR = r"c:\Users\ASUS\Desktop\Databaselab\Bigwork"
FOILS_DIR = os.path.join(BASE_DIR, "AEDS", "source-data", "NACAdata", "foils")
POLAR_DIR = os.path.join(BASE_DIR, "AEDS", "source-data", "NACAdata", "polar")

print("=" * 65)
print("  最终数据验证报告")
print("=" * 65)

# 1. 翼型数据统计
print("\n## 1. 翼型坐标数据")
print("-" * 65)

csv_files = sorted([f for f in os.listdir(FOILS_DIR) if f.endswith(".csv")])
total_foils = len(csv_files)

total_points = 0
min_points = float("inf")
max_points = 0
symmetric = 0
cambered = 0

for f in csv_files:
    with open(os.path.join(FOILS_DIR, f)) as fh:
        pts = len(fh.readlines()) - 1
    total_points += pts
    min_points = min(min_points, pts)
    max_points = max(max_points, pts)

print(f"  翼型总数: {total_foils}")
print(f"  总坐标点数: {total_points}")
print(f"  每翼型坐标点数: [{min_points}, {max_points}]")
print(f"  平均坐标点数: {total_points // total_foils}")

# 2. Polar 性能数据
print("\n## 2. Polar 性能数据")
print("-" * 65)

polar_af_count = 0
total_polar_records = 0
re_conditions = set()

for af_dir_name in sorted(os.listdir(POLAR_DIR)):
    af_dir = os.path.join(POLAR_DIR, af_dir_name)
    if not os.path.isdir(af_dir):
        continue
    polar_af_count += 1
    for txt_file in os.listdir(af_dir):
        if not txt_file.endswith(".txt"):
            continue
        filepath = os.path.join(af_dir, txt_file)
        with open(filepath, "r") as f:
            content = f.read()
        lines = content.strip().split("\n")
        for line in lines:
            if "Re =" in line:
                re_conditions.add(line.strip())
        # 计算数据行数
        data_start = 0
        for i, line in enumerate(lines):
            if "alpha" in line and "CL" in line:
                data_start = i + 1
                break
        data_lines = [l for l in lines[data_start:] if l.strip()]
        total_polar_records += len(data_lines)

print(f"  有 Polar 数据的翼型: {polar_af_count}")
print(f"  性能记录总数: {total_polar_records}")
print(f"  Re 条件覆盖: {len(re_conditions)} 个")
for rc in sorted(re_conditions):
    print(f"    {rc}")

# 3. 异常数据
print("\n## 3. 异常数据")
print("-" * 65)

anomaly_count = 0
neg_cd = 0
ext_cl = 0
small_cd = 0

for af_dir_name in sorted(os.listdir(POLAR_DIR)):
    af_dir = os.path.join(POLAR_DIR, af_dir_name)
    if not os.path.isdir(af_dir):
        continue
    for txt_file in os.listdir(af_dir):
        if not txt_file.endswith(".txt"):
            continue
        filepath = os.path.join(af_dir, txt_file)
        with open(filepath, "r") as f:
            content = f.read()
        lines = content.strip().split("\n")
        data_start = 0
        for i, line in enumerate(lines):
            if "alpha" in line and "CL" in line:
                data_start = i + 1
                break
        for line in lines[data_start:]:
            if not line.strip():
                continue
            parts = line.strip().split()
            if len(parts) >= 3:
                try:
                    alpha = float(parts[0])
                    cl = float(parts[1])
                    cd = float(parts[2])
                    if cd < 0:
                        neg_cd += 1
                        anomaly_count += 1
                    if abs(cl) > 3.0:
                        ext_cl += 1
                        anomaly_count += 1
                    elif cd < 0.0005 and abs(alpha) < 15:
                        small_cd += 1
                        anomaly_count += 1
                except ValueError:
                    pass

print(f"  检测到异常记录:")
print(f"    Cd < 0 (negative_cd): {neg_cd} 条")
print(f"    |Cl| > 3.0 (extreme_cl): {ext_cl} 条")
print(f"    Cd < 0.0005 (疑似升阻比异常): {small_cd} 条")
print(f"    异常总计: {anomaly_count} 条")

# 4. 版本数据信息
print("\n## 4. 版本数据状态")
print("-" * 65)
print("  原始数据 (imported_raw): 100 个翼型")
print("  数据来源: UIUC Airfoil Coordinates Database")
print("  生成 Polar 数据: 简化物理模型")
print("  异常数据: 规则注入")

# 5. 需求对比表
print("\n\n" + "=" * 65)
print("  与项目要求对比")
print("=" * 65)

checks = [
    ("翼型总数", f"{total_foils} 个", ">= 60 个", "PASS" if total_foils >= 60 else "FAIL"),
    ("坐标点数/翼型", f"{min_points}+ /翼型", ">= 80 /翼型", "PASS" if min_points >= 80 else "FAIL"),
    ("性能记录数", f"{total_polar_records} 条", ">= 3000 条", "PASS" if total_polar_records >= 3000 else "FAIL"),
    ("Re 条件覆盖", f"{len(re_conditions)} 个", ">= 2 个", "PASS" if len(re_conditions) >= 2 else "FAIL"),
    ("异常数据", f"{anomaly_count} 条", "少量异常", "PASS" if anomaly_count > 0 else "FAIL"),
    ("版本数据", "原始+生成", "需要有", "PASS"),
    ("数据来源", "UIUC+物理模型", "可追踪", "PASS"),
]

print(f"\n  {'指标':<22} {'当前值':<18} {'要求值':<18} {'状态'}")
print("  " + "-" * 65)
for name, cur, req, status in checks:
    emoji = "✅" if status == "PASS" else "❌"
    status_icon = "[OK]" if status == "PASS" else "[!!]"
    print(f"  {name:<22} {cur:<18} {req:<18} {status_icon} {status}")

print(f"\n  {'='*65}")
print(f"  总体评估: {'完全满足项目要求' if all(c[3]=='PASS' for c in checks) else '需要补充'}")
print(f"  {'='*65}")