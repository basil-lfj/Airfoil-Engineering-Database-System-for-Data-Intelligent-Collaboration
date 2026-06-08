"""
翼型工程数据可视化分析
生成多种图表用于项目报告：
1. 翼型轮廓叠加对比图
2. Cl-α 关系曲线（单翼型/多翼型/多Re）
3. Cd-α 关系曲线
4. Cl/Cd-α 升阻比曲线
5. 多翼型同Re性能对比
6. 异常数据可视化
7. 数据规模总览图
"""

import os
import math
import random
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

plt.rcParams["font.family"] = "Microsoft YaHei"
plt.rcParams["font.size"] = 11
plt.rcParams["axes.unicode_minus"] = False

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FOILS_DIR = os.path.join(BASE_DIR, "source-data", "NACAdata", "foils")
POLAR_DIR = os.path.join(BASE_DIR, "source-data", "NACAdata", "polar")
OUTPUT_DIR = os.path.join(BASE_DIR, "Webfront", "static", "visualization")

os.makedirs(OUTPUT_DIR, exist_ok=True)

# ── 选取代表性翼型用于分析 ──
REPRESENTATIVE_FOILS = [
    "NACA 0006",
    "NACA 2412",
    "NACA 4421",
    "NACA 0015",
    "NACA 4415",
]

def parse_foil_csv(filepath):
    """解析翼型 CSV 坐标文件"""
    with open(filepath, "r") as f:
        content = f.read()
    lines = content.strip().split("\n")
    name = lines[0].strip()
    coords = []
    for line in lines[1:]:
        parts = line.strip().split(",")
        if len(parts) == 2:
            try:
                x, y = float(parts[0]), float(parts[1])
                coords.append((x, y))
            except ValueError:
                pass
    return name, coords


def parse_polar_file(filepath):
    """解析 Polar 文件，返回 [(alpha, cl, cd), ...]
    兼容两种格式：新格式(3列)和旧格式(8+列)"""
    with open(filepath, "r") as f:
        lines = f.readlines()
    records = []
    data_start = 0
    for i, line in enumerate(lines):
        if "alpha" in line and ("CL" in line or "CD" in line):
            data_start = i + 1
            break
    for line in lines[data_start:]:
        stripped = line.strip()
        if not stripped:
            continue
        parts = stripped.split()
        if len(parts) >= 3:
            try:
                alpha = float(parts[0])
                cl = float(parts[1])
                # cd 可能在第三列或更多
                if len(parts) >= 8:
                    cd = float(parts[2])
                else:
                    cd = float(parts[2])
                records.append((alpha, cl, cd))
            except ValueError:
                pass
    return records


def find_polar_file(af_name, re_val=0.050):
    """查找特定翼型和 Re 的 Polar 文件（兼容两种目录命名格式）"""
    safe_name = af_name.replace(" ", "_").replace("/", "_").replace(",", "_").replace("(", "").replace(")", "").replace("=", "_")
    
    # 尝试两种格式：NACA-NACA_xxxx 和 NACA-xxxx
    candidates = [f"NACA-{safe_name}"]
    # 如果名称包含"NACA"，也尝试去掉前缀的NACA
    if safe_name.upper().startswith("NACA_"):
        candidates.append(f"NACA-{safe_name[5:]}")
    
    for dir_name in candidates:
        af_dir = os.path.join(POLAR_DIR, dir_name)
        if os.path.isdir(af_dir):
            for fname in os.listdir(af_dir):
                if fname.endswith(".txt") and f"Re{re_val:.3f}" in fname and not fname.startswith("._"):
                    return os.path.join(af_dir, fname)
    return None


def get_polar_by_af(af_name, re=0.050):
    path = find_polar_file(af_name, re)
    if path:
        return parse_polar_file(path)
    return []


def find_foil_csv(name):
    """查找翼型 CSV 文件"""
    # 尝试精确文件名
    fpath = os.path.join(FOILS_DIR, f"{name}.csv")
    if os.path.exists(fpath):
        return fpath
    # 尝试带空格的
    for f in os.listdir(FOILS_DIR):
        if f.endswith(".csv") and f.startswith(name):
            return os.path.join(FOILS_DIR, f)
    return None


# ============================================================
# 图表 1: 翼型轮廓叠加对比 (5个代表性翼型)
# ============================================================
def plot_foil_profiles():
    print("  [1/6] 绘制翼型轮廓叠加对比图...")
    fig, ax = plt.subplots(figsize=(10, 6))
    
    colors = ["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd"]
    linestyles = ["-", "--", "-.", ":", (0, (3, 1, 1, 1))]
    
    for i, fname in enumerate(REPRESENTATIVE_FOILS):
        fpath = find_foil_csv(fname)
        if not fpath:
            continue
        name, coords = parse_foil_csv(fpath)
        xs = [p[0] for p in coords]
        ys = [p[1] for p in coords]
        ax.plot(xs, ys, label=f"{name}", color=colors[i % len(colors)],
                linewidth=1.8, linestyle=linestyles[i % len(linestyles)])
        
        # 标注关键参数
        max_y = max(abs(y) for _, y in coords)
        thick_pct = round(max_y * 2 * 100, 1)
        ax.annotate(f"t={thick_pct}%", xy=(0.5, max(coords, key=lambda p: abs(p[1]))[1]),
                    fontsize=8, color=colors[i], ha="center")
    
    ax.set_xlabel("x/c (弦长位置)", fontsize=12)
    ax.set_ylabel("y/c (厚度)", fontsize=12)
    ax.set_title("代表性 NACA 翼型轮廓对比", fontsize=14, fontweight="bold")
    ax.set_xlim(-0.05, 1.05)
    ax.set_aspect("equal")
    ax.grid(True, alpha=0.3)
    ax.legend(fontsize=10, loc="best")
    
    plt.tight_layout()
    fig.savefig(os.path.join(OUTPUT_DIR, "01_foil_profiles.png"), dpi=150)
    plt.close(fig)


# ============================================================
# 图表 2: NACA 2412 在不同 Re 下的 Cl-α 曲线
# ============================================================
def plot_cl_alpha_multi_re():
    print("  [2/6] 绘制 Cl-α 曲线 (多Re条件)...")
    fig, axes = plt.subplots(1, 3, figsize=(15, 5))
    
    re_values = [0.050, 0.070, 0.100]
    re_labels = ["Re = 0.050M", "Re = 0.070M", "Re = 0.100M"]
    colors = ["#1f77b4", "#ff7f0e", "#2ca02c"]
    
    # 对比三种代表性翼型
    foil_to_show = ["NACA 2412", "NACA 0006", "NACA 4421"]
    styles = ["-", "--", ":"]
    
    for idx, (ax, re_val, re_label) in enumerate(zip(axes, re_values, re_labels)):
        for fi, fname in enumerate(foil_to_show):
            records = get_polar_by_af(fname, re_val)
            if not records:
                continue
            alphas = [r[0] for r in records]
            cls = [r[1] for r in records]
            # 过滤异常 Cl
            filtered = [(a, c) for a, c in zip(alphas, cls) if abs(c) < 5]
            if filtered:
                fa, fc = zip(*filtered)
                ax.plot(fa, fc, label=fname, color=colors[fi], linewidth=1.8, linestyle=styles[fi])
        
        ax.set_xlabel("攻角 α (°)", fontsize=11)
        ax.set_ylabel("升力系数 $C_l$", fontsize=11)
        ax.set_title(re_label, fontsize=12, fontweight="bold")
        ax.grid(True, alpha=0.3)
        ax.legend(fontsize=9)
        ax.axhline(y=0, color="gray", linewidth=0.5)
        ax.axvline(x=0, color="gray", linewidth=0.5)
    
    fig.suptitle("不同 Re 条件下翼型 $C_l$ - α 关系曲线", fontsize=14, fontweight="bold", y=1.02)
    plt.tight_layout()
    fig.savefig(os.path.join(OUTPUT_DIR, "02_cl_alpha_multi_re.png"), dpi=150, bbox_inches="tight")
    plt.close(fig)


# ============================================================
# 图表 3: Cd-α 曲线 + Cl/Cd-α 升阻比曲线
# ============================================================
def plot_cd_and_ld():
    print("  [3/6] 绘制 Cd-α 和 升阻比曲线...")
    fig, axes = plt.subplots(2, 2, figsize=(12, 10))
    
    re_val = 0.070
    foil_to_show = ["NACA 2412", "NACA 0006", "NACA 4421", "NACA 0015"]
    colors = ["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728"]
    
    # Cd-α
    ax = axes[0, 0]
    for fi, fname in enumerate(foil_to_show):
        records = get_polar_by_af(fname, re_val)
        if not records:
            continue
        alphas = [r[0] for r in records]
        cds = [r[2] for r in records]
        ax.plot(alphas, cds, label=fname, color=colors[fi], linewidth=1.8)
    ax.set_xlabel("攻角 α (°)", fontsize=11)
    ax.set_ylabel("阻力系数 $C_d$", fontsize=11)
    ax.set_title(f"$C_d$ - α (Re = {re_val:.3f}M)", fontsize=12, fontweight="bold")
    ax.grid(True, alpha=0.3)
    ax.legend(fontsize=9)
    
    # Cl/Cd - α
    ax = axes[0, 1]
    for fi, fname in enumerate(foil_to_show):
        records = get_polar_by_af(fname, re_val)
        if not records:
            continue
        alphas = [r[0] for r in records]
        ld = [r[1] / r[2] if r[2] > 0 else 0 for r in records]
        ax.plot(alphas, ld, label=fname, color=colors[fi], linewidth=1.8)
    ax.set_xlabel("攻角 α (°)", fontsize=11)
    ax.set_ylabel("升阻比 $C_l/C_d$", fontsize=11)
    ax.set_title(f"升阻比 - α (Re = {re_val:.3f}M)", fontsize=12, fontweight="bold")
    ax.grid(True, alpha=0.3)
    ax.legend(fontsize=9)
    ax.axhline(y=0, color="gray", linewidth=0.5)
    
    # NACA 2412 不同 Re 的 Cd-α（线性坐标）
    ax = axes[1, 0]
    re_values = [0.050, 0.070, 0.100]
    for re_val in re_values:
        records = get_polar_by_af("NACA 2412", re_val)
        if not records:
            continue
        alphas = [r[0] for r in records]
        cds = [r[2] for r in records]
        ax.plot(alphas, cds, label=f"Re={re_val:.3f}M", linewidth=1.8)
    ax.set_xlabel("攻角 α (°)", fontsize=11)
    ax.set_ylabel("阻力系数 $C_d$", fontsize=11)
    ax.set_title("NACA 2412 $C_d$ - α (不同 Re)", fontsize=12, fontweight="bold")
    ax.grid(True, alpha=0.3)
    ax.legend(fontsize=9)
    
    # NACA 2412 不同 Re 的 Cl 对比
    ax = axes[1, 1]
    for re_val in re_values:
        records = get_polar_by_af("NACA 2412", re_val)
        if not records:
            continue
        alphas = [r[0] for r in records]
        cls = [r[1] for r in records]
        ax.plot(alphas, cls, label=f"Re={re_val:.3f}M", linewidth=1.8)
    ax.set_xlabel("攻角 α (°)", fontsize=11)
    ax.set_ylabel("升力系数 $C_l$", fontsize=11)
    ax.set_title("NACA 2412 $C_l$ - α (不同 Re)", fontsize=12, fontweight="bold")
    ax.grid(True, alpha=0.3)
    ax.legend(fontsize=9)
    ax.axhline(y=0, color="gray", linewidth=0.5)
    
    plt.tight_layout()
    fig.savefig(os.path.join(OUTPUT_DIR, "03_cd_and_ld.png"), dpi=150)
    plt.close(fig)


# ============================================================
# 图表 4: 多翼型同 Re 性能对比 (Cl-α, Cd-α, Cl/Cd)
# ============================================================
def plot_multi_foil_comparison():
    print("  [4/6] 绘制多翼型性能对比图...")
    fig, axes = plt.subplots(1, 3, figsize=(16, 5))
    
    re_val = 0.070
    foils = ["NACA 0006", "NACA 2412", "NACA 4421", "NACA 0015", "NACA 4415"]
    colors = ["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd"]
    
    # Cl-α
    ax = axes[0]
    for fi, fname in enumerate(foils):
        records = get_polar_by_af(fname, re_val)
        if not records:
            continue
        alphas = [r[0] for r in records]
        cls = [r[1] for r in records]
        # 过滤
        filtered = [(a, c) for a, c in zip(alphas, cls) if abs(c) < 5]
        if filtered:
            fa, fc = zip(*filtered)
            ax.plot(fa, fc, label=fname, color=colors[fi], linewidth=1.6)
    ax.set_xlabel("攻角 α (°)", fontsize=11)
    ax.set_ylabel("$C_l$", fontsize=11)
    ax.set_title(f"$C_l$ - α (Re={re_val:.3f}M)", fontsize=12, fontweight="bold")
    ax.grid(True, alpha=0.3)
    ax.legend(fontsize=8, loc="upper left")
    ax.axhline(y=0, color="gray", linewidth=0.5)
    
    # Cd-α
    ax = axes[1]
    for fi, fname in enumerate(foils):
        records = get_polar_by_af(fname, re_val)
        if not records:
            continue
        alphas = [r[0] for r in records]
        cds = [r[2] for r in records]
        ax.plot(alphas, cds, label=fname, color=colors[fi], linewidth=1.6)
    ax.set_xlabel("攻角 α (°)", fontsize=11)
    ax.set_ylabel("$C_d$", fontsize=11)
    ax.set_title(f"$C_d$ - α (Re={re_val:.3f}M)", fontsize=12, fontweight="bold")
    ax.grid(True, alpha=0.3)
    ax.legend(fontsize=8)
    
    # Cl/Cd
    ax = axes[2]
    for fi, fname in enumerate(foils):
        records = get_polar_by_af(fname, re_val)
        if not records:
            continue
        alphas = [r[0] for r in records]
        ld = [r[1] / r[2] if r[2] > 0 else 0 for r in records]
        ax.plot(alphas, ld, label=fname, color=colors[fi], linewidth=1.6)
    ax.set_xlabel("攻角 α (°)", fontsize=11)
    ax.set_ylabel("$C_l/C_d$", fontsize=11)
    ax.set_title(f"升阻比 - α (Re={re_val:.3f}M)", fontsize=12, fontweight="bold")
    ax.grid(True, alpha=0.3)
    ax.legend(fontsize=8)
    
    fig.suptitle(f"多翼型性能对比 (Re={re_val:.3f}M)", fontsize=14, fontweight="bold", y=1.02)
    plt.tight_layout()
    fig.savefig(os.path.join(OUTPUT_DIR, "04_multi_foil_comparison.png"), dpi=150, bbox_inches="tight")
    plt.close(fig)


# ============================================================
# 图表 5: 异常数据可视化
# ============================================================
def plot_anomaly_detection():
    print("  [5/6] 绘制异常数据检测图...")
    fig, axes = plt.subplots(2, 2, figsize=(12, 10))
    
    # 扫描所有 Polar 文件找异常
    all_records = []
    anomalies = []
    
    for af_dir_name in sorted(os.listdir(POLAR_DIR)):
        af_dir = os.path.join(POLAR_DIR, af_dir_name)
        if not os.path.isdir(af_dir):
            continue
        for txt_file in os.listdir(af_dir):
            if not txt_file.endswith(".txt") or txt_file.startswith("._"):
                continue
            fpath = os.path.join(af_dir, txt_file)
            records = parse_polar_file(fpath)
            for alpha, cl, cd in records:
                all_records.append((cl, cd, alpha, af_dir_name))
                is_anomaly = False
                atype = ""
                if cd < 0:
                    is_anomaly = True
                    atype = "negative_cd"
                elif abs(cl) > 3.0:
                    is_anomaly = True
                    atype = "extreme_cl"
                elif cd < 0.001 and abs(alpha) < 15:
                    is_anomaly = True
                    atype = "extreme_ld"
                if is_anomaly:
                    anomalies.append((cl, cd, alpha, af_dir_name, atype))
    
    # 散点图: Cl vs Cd (正常 vs 异常)
    ax = axes[0, 0]
    # 采样
    sample = random.sample(all_records, min(2000, len(all_records)))
    if sample:
        cls = [r[0] for r in sample]
        cds = [r[1] for r in sample]
        ax.scatter(cds, cls, s=2, alpha=0.3, c="#1f77b4", label="正常数据")
    
    if anomalies:
        a_colors = {"negative_cd": "#d62728", "extreme_cl": "#ff7f0e", "extreme_ld": "#2ca02c"}
        plotted_types = set()
        for cl, cd, alpha, af_name, atype in anomalies:
            label_text = atype if atype not in plotted_types else ""
            plotted_types.add(atype)
            ax.scatter(cd, cl, s=30, c=a_colors.get(atype, "black"), marker="x", label=label_text)
    ax.set_xlabel("$C_d$", fontsize=11)
    ax.set_ylabel("$C_l$", fontsize=11)
    ax.set_title("异常数据分布 ($C_l$ - $C_d$ 散点图)", fontsize=12, fontweight="bold")
    ax.grid(True, alpha=0.3)
    ax.axhline(y=0, color="gray", linewidth=0.5)
    ax.axvline(x=0, color="gray", linewidth=0.5)
    if anomalies:
        ax.legend(fontsize=8, markerscale=0.8)
    
    # 异常计数柱状图
    ax = axes[0, 1]
    type_counts = {}
    for _, _, _, _, atype in anomalies:
        type_counts[atype] = type_counts.get(atype, 0) + 1
    types = list(type_counts.keys())
    counts = list(type_counts.values())
    bar_colors = [a_colors.get(t, "gray") for t in types]
    bars = ax.bar(types, counts, color=bar_colors, edgecolor="white", linewidth=0.5)
    for bar, count in zip(bars, counts):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 1,
                str(count), ha="center", fontsize=10, fontweight="bold")
    ax.set_ylabel("异常记录数", fontsize=11)
    ax.set_title("异常类型分布", fontsize=12, fontweight="bold")
    ax.set_xticks(range(len(types)))
    ax.set_xticklabels(types, rotation=15)
    ax.grid(True, alpha=0.3, axis="y")
    
    # Cl-α 异常标注
    ax = axes[1, 0]
    for af_name in ["NACA 0006"]:
        records = get_polar_by_af("NACA 0006", 0.050)
        if records:
            alphas = [r[0] for r in records]
            cls = [r[1] for r in records]
            ax.plot(alphas, cls, "b-", linewidth=1.5, alpha=0.7, label="NACA 0006 (正常)")
            # 标注异常点
            for a, c, d in records:
                if d < 0:
                    ax.scatter(a, c, s=80, c="red", marker="o", zorder=5,
                               label=f"异常: Cd={d:.3f}")
                    ax.annotate(f"Cd={d:.3f}<0", xy=(a, c), xytext=(a+2, c+0.3),
                                arrowprops=dict(arrowstyle="->", color="red"),
                                fontsize=9, color="red")
                if abs(c) > 3:
                    ax.scatter(a, c, s=80, c="orange", marker="o", zorder=5,
                               label=f"异常: Cl={c:.1f}")
    ax.set_xlabel("攻角 α (°)", fontsize=11)
    ax.set_ylabel("$C_l$", fontsize=11)
    ax.set_title("NACA 0006 异常检测 (Re=0.050M)", fontsize=12, fontweight="bold")
    ax.grid(True, alpha=0.3)
    ax.legend(fontsize=9)
    
    # α-Cd 异常标注
    ax = axes[1, 1]
    records = get_polar_by_af("NACA 0006", 0.050)
    if records:
        alphas = [r[0] for r in records]
        cds = [r[2] for r in records]
        ax.plot(alphas, cds, "g-", linewidth=1.5, alpha=0.7, label="NACA 0006")
        for a, c, d in records:
            if d < 0:
                ax.scatter(a, d, s=80, c="red", marker="o", zorder=5)
                ax.annotate(f"Cd={d:.3f}", xy=(a, d), xytext=(a+1, d-0.02),
                            arrowprops=dict(arrowstyle="->", color="red"),
                            fontsize=9, color="red")
            if d < 0.0005 and abs(a) < 15:
                ax.scatter(a, d, s=60, c="orange", marker="o", zorder=5,
                           label="Cd 异常偏低" if "偏低" not in str(ax.get_legend_handles_labels()) else "")
    ax.set_xlabel("攻角 α (°)", fontsize=11)
    ax.set_ylabel("$C_d$", fontsize=11)
    ax.set_title("NACA 0006 阻力系数异常 (Re=0.050M)", fontsize=12, fontweight="bold")
    ax.grid(True, alpha=0.3)
    ax.legend(fontsize=9)
    
    plt.tight_layout()
    fig.savefig(os.path.join(OUTPUT_DIR, "05_anomaly_detection.png"), dpi=150)
    plt.close(fig)


# ============================================================
# 图表 6: 数据规模总览图
# ============================================================
def plot_data_overview():
    print("  [6/6] 绘制数据规模总览图...")
    fig, axes = plt.subplots(2, 3, figsize=(15, 8))
    
    # 1. 翼型分类
    ax = axes[0, 0]
    foil_types = {"对称翼型 (4位)": 0, "有弯度翼型 (4位)": 0, "5位系列": 0, "6系/7系": 0}
    for f in os.listdir(FOILS_DIR):
        if not f.endswith(".csv"):
            continue
        name = f.replace(".csv", "")
        parts = name.split("_")
        code = parts[-1] if len(parts) > 1 else name
        if "63" in code or "64" in code or "65" in code or "66" in code or "67" in code or "74" in code:
            foil_types["6系/7系"] += 1
        elif len(code) == 4 and code.isdigit():
            if code[0] == "0":
                foil_types["对称翼型 (4位)"] += 1
            else:
                foil_types["有弯度翼型 (4位)"] += 1
        else:
            foil_types["5位系列"] += 1
    
    colors_pie = ["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728"]
    wedges, texts, autotexts = ax.pie(
        foil_types.values(), labels=foil_types.keys(), autopct="%1.1f%%",
        colors=colors_pie, startangle=90, textprops={"fontsize": 9}
    )
    ax.set_title("翼型类别分布", fontsize=12, fontweight="bold")
    
    # 2. 每翼型坐标点数分布
    ax = axes[0, 1]
    point_counts = []
    for f in os.listdir(FOILS_DIR):
        if not f.endswith(".csv"):
            continue
        with open(os.path.join(FOILS_DIR, f)) as fh:
            pts = len(fh.readlines()) - 1
        point_counts.append(pts)
    
    ax.hist(point_counts, bins=20, color="#1f77b4", edgecolor="white", alpha=0.8)
    ax.axvline(x=80, color="red", linestyle="--", linewidth=2, label="要求最低 80 点")
    ax.set_xlabel("坐标点数", fontsize=11)
    ax.set_ylabel("翼型数量", fontsize=11)
    ax.set_title("翼型坐标点数分布", fontsize=12, fontweight="bold")
    ax.legend(fontsize=9)
    ax.grid(True, alpha=0.3)
    
    # 3. 性能记录数分布
    ax = axes[0, 2]
    record_counts = []
    for af_dir_name in sorted(os.listdir(POLAR_DIR)):
        af_dir = os.path.join(POLAR_DIR, af_dir_name)
        if not os.path.isdir(af_dir):
            continue
        af_total = 0
        for txt_file in os.listdir(af_dir):
            if not txt_file.endswith(".txt") or txt_file.startswith("._"):
                continue
            records = parse_polar_file(os.path.join(af_dir, txt_file))
            af_total += len(records)
        record_counts.append(af_total)
    
    ax.hist(record_counts, bins=20, color="#2ca02c", edgecolor="white", alpha=0.8)
    ax.axvline(x=150, color="red", linestyle="--", linewidth=2, label="每翼型约 153 条")
    ax.set_xlabel("性能记录数/翼型", fontsize=11)
    ax.set_ylabel("翼型数量", fontsize=11)
    ax.set_title("性能记录数分布", fontsize=12, fontweight="bold")
    ax.legend(fontsize=9)
    ax.grid(True, alpha=0.3)
    
    # 4. 攻角-升力系数热力图 (NACA 2412)
    ax = axes[1, 0]
    re_values = [0.050, 0.070, 0.100]
    cl_data = {}
    for re_val in re_values:
        records = get_polar_by_af("NACA 2412", re_val)
        if records:
            cl_data[f"Re={re_val:.3f}M"] = [r[1] for r in records[:15]]
    
    if cl_data:
        im = ax.imshow(list(cl_data.values()), cmap="RdYlBu_r", aspect="auto", interpolation="nearest")
        ax.set_yticks(range(len(cl_data)))
        ax.set_yticklabels(cl_data.keys(), fontsize=9)
        ax.set_xticks(range(0, 15, 3))
        ax.set_xticklabels([f"{r[0]:.0f}°" for r in records[:15:3]], fontsize=8)
        ax.set_xlabel("攻角 α", fontsize=11)
        ax.set_title("NACA 2412 $C_l$ 热力图 (不同Re)", fontsize=12, fontweight="bold")
        fig.colorbar(im, ax=ax, shrink=0.8)
    
    # 5. 数据规模条形图
    ax = axes[1, 1]
    metrics = ["翼型数", "坐标点数\n(万)", "性能记录\n(万)"]
    values = [100, round(10011 / 1000, 1), round(18060 / 1000, 1)]
    bars = ax.bar(metrics, values, color=["#1f77b4", "#2ca02c", "#ff7f0e"], edgecolor="white", linewidth=0.5)
    for bar, val in zip(bars, values):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.5,
                str(val) if val > 1 else str(int(val * 1000)),
                ha="center", fontsize=11, fontweight="bold")
    ax.set_ylabel("数量", fontsize=11)
    ax.set_title("数据规模总览", fontsize=12, fontweight="bold")
    ax.grid(True, alpha=0.3, axis="y")
    
    # 6. 异常检测结果
    ax = axes[1, 2]
    # 统计所有异常
    total = 0
    anomaly_details = {"negative_cd": 0, "extreme_cl": 0, "extreme_ld": 0}
    for af_dir_name in sorted(os.listdir(POLAR_DIR)):
        af_dir = os.path.join(POLAR_DIR, af_dir_name)
        if not os.path.isdir(af_dir):
            continue
        for txt_file in os.listdir(af_dir):
            if not txt_file.endswith(".txt") or txt_file.startswith("._"):
                continue
            records = parse_polar_file(os.path.join(af_dir, txt_file))
            for alpha, cl, cd in records:
                if cd < 0:
                    anomaly_details["negative_cd"] += 1
                    total += 1
                elif abs(cl) > 3.0:
                    anomaly_details["extreme_cl"] += 1
                    total += 1
                elif cd < 0.001 and abs(alpha) < 15:
                    anomaly_details["extreme_ld"] += 1
                    total += 1
    
    labels = list(anomaly_details.keys())
    vals = list(anomaly_details.values())
    a_colors = ["#d62728", "#ff7f0e", "#2ca02c"]
    bars = ax.barh(labels, vals, color=a_colors, edgecolor="white")
    for bar, val in zip(bars, vals):
        ax.text(bar.get_width() + 1, bar.get_y() + bar.get_height() / 2,
                str(val), va="center", fontsize=10, fontweight="bold")
    ax.set_xlabel("异常记录数", fontsize=11)
    ax.set_title(f"总异常 {total} 条", fontsize=12, fontweight="bold")
    ax.grid(True, alpha=0.3, axis="x")
    
    plt.tight_layout()
    fig.savefig(os.path.join(OUTPUT_DIR, "06_data_overview.png"), dpi=150)
    plt.close(fig)


# ============================================================
# 主流程
# ============================================================
def main():
    print("=" * 60)
    print("翼型数据可视化分析")
    print("=" * 60)
    
    # 设置中文字体
    try:
        plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "DejaVu Sans"]
    except:
        pass
    
    plot_foil_profiles()
    plot_cl_alpha_multi_re()
    plot_cd_and_ld()
    plot_multi_foil_comparison()
    plot_anomaly_detection()
    plot_data_overview()
    
    print(f"\n{'='*60}")
    print("所有图表生成完毕！")
    print(f"输出目录: {OUTPUT_DIR}")
    print(f"{'='*60}")
    
    # 列出生成的文件
    for f in sorted(os.listdir(OUTPUT_DIR)):
        fpath = os.path.join(OUTPUT_DIR, f)
        size = os.path.getsize(fpath) / 1024
        print(f"  {f:<45} {size:.1f} KB")


if __name__ == "__main__":
    main()
