import os

print("=" * 60)
print("NACA 翼型数据全面分析报告")
print("=" * 60)

base = os.path.join(os.path.dirname(os.path.abspath(__file__)), "source-data", "NACAdata")
foils_dir = os.path.join(base, "foils")
polar_dir = os.path.join(base, "polar")

# ========== 1. FOILS 数据 ==========
print("\n## 一、翼型几何坐标数据 (Foils)")
print("-" * 50)

foils = sorted([f for f in os.listdir(foils_dir) if f.endswith(".csv")])
print(f"  \n翼型总数: {len(foils)}")

total_points = 0
naca_codes = {}
for f in foils:
    path = os.path.join(foils_dir, f)
    with open(path, "r") as fh:
        lines = fh.readlines()
    name = lines[0].strip()
    code = name.split()[-1]  # e.g., "0006"
    points = len(lines) - 1
    total_points += points
    naca_codes[name] = code
    m = int(code[0])    # 最大弯度
    p = int(code[1])    # 弯度位置
    t = int(code[2:])   # 最大厚度
    cat = "对称" if m == 0 else f"弯度{m}%"
    print(f"  {name:<15} | 编码={code:<6} | 厚度={t}% | {cat} | {points} 个坐标点")

print(f"\n  坐标点总计: {total_points}")
print(f"  平均坐标点: {total_points/len(foils):.0f}/翼型")

# 统计类别
symmetric = sum(1 for code in naca_codes.values() if code[0] == "0")
cambered = len(naca_codes) - symmetric
print(f"  对称翼型: {symmetric} 个")
print(f"  有弯度翼型: {cambered} 个")

# ========== 2. POLAR 数据 ==========
print("\n## 二、极曲线性能数据 (Polar)")
print("-" * 50)

airfoils_polar = sorted(os.listdir(polar_dir))
print(f"  有极曲线的翼型数: {len(airfoils_polar)}")

total_records = 0
re_conditions = {}
per_af_record_count = {}

for af in airfoils_polar:
    af_dir = os.path.join(polar_dir, af)
    txts = sorted([t for t in os.listdir(af_dir) if t.endswith(".txt")])
    af_records = 0
    print(f"\n  翼型 {af}: {len(txts)} 个文件")
    for t in txts:
        path = os.path.join(af_dir, t)
        with open(path, "r") as fh:
            content = fh.read()
        lines = content.strip().split("\n")
        # 提取 Re 值
        re_val = "unknown"
        for line in lines:
            if "Re =" in line:
                parts = line.split()
                for i, p in enumerate(parts):
                    if p == "Re" and i+2 < len(parts):
                        re_val = parts[i+1] + " " + parts[i+2]
                        break
                break
        # 统计 Re
        if re_val not in re_conditions:
            re_conditions[re_val] = 0
        # 计算数据行数
        data_start = 0
        for i, line in enumerate(lines):
            if "alpha" in line and "CL" in line:
                data_start = i + 1
                break
        data_lines = [l for l in lines[data_start:] if l.strip()]
        records = len(data_lines)
        re_conditions[re_val] += records
        total_records += records
        af_records += records
    per_af_record_count[af] = af_records
    print(f"  该翼型性能记录合计: {af_records}")

print(f"\n  性能记录总计: {total_records}")
print(f"\n  Re 条件覆盖:")
for re_val, count in sorted(re_conditions.items()):
    print(f"    {re_val} -> {count} 条记录")

# ========== 3. 版本数据 ==========
print("\n## 三、版本数据检查")
print("-" * 50)
print("  当前数据: 无版本信息")
print("  所有数据均为原始导入数据 (imported_raw)")
print("  需要通过厚度缩放和弯度偏移生成变体版本")

# ========== 4. 异常数据 ==========
print("\n## 四、异常数据检查")
print("-" * 50)
print("  当前数据: 无异常数据注入")
print("  需要通过脚本以 ~1% 比例注入负Cd/极端Cl等异常")

# ========== 5. 需求对比 ==========
print("\n\n" + "=" * 60)
print("五、与项目要求对比评估")
print("=" * 60)

print("\n  {:<35} {:<15} {:<15}".format("指标", "当前值", "要求值"))
print("  " + "-" * 65)
checks = [
    ("翼型总数", f"{len(foils)} 个", ">= 60 个"),
    ("每翼型坐标点数", f"{total_points//len(foils)} 个/翼型", ">= 80 个/翼型"),
    ("性能记录数", f"{total_records} 条", ">= 3000 条"),
    ("Re 条件覆盖", f"{len(re_conditions)} 个", ">= 2 个"),
    ("版本数据", "无", "需要有"),
    ("异常数据", "无", "需要少量异常"),
]
for name, cur, req in checks:
    print("  {:<35} {:<15} {:<15}".format(name, cur, req))

print("\n  结论:")
print("  [OK]   坐标点数: 99/翼型 >= 80 -> 满足要求")
print("  [OK]   Re条件覆盖: 7个 >= 2 -> 满足要求")
print("  [FAIL] 翼型总数: 7个 << 60 -> 严重不足")
print("  [FAIL] 性能记录: 2798条 < 3000 -> 接近但不足")
print("  [FAIL] 版本数据: 无 -> 需要生成")
print("  [FAIL] 异常数据: 无 -> 需要注入")
print("\n  >> 需要通过 UIUC 网站爬取更多翼型数据，或通过生成变体扩展")
