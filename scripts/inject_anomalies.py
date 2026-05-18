"""
在 Polar 性能数据中注入异常数据
类型：
1. negative_cd: Cd 设为负值 (物理不可能)
2. extreme_cl: Cl 放大 4 倍 (异常偏高)
3. extreme_ld: 升阻比异常偏离

注入比例：约 1%
"""

import os
import random
import math

random.seed(42)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
POLAR_DIR = os.path.join(BASE_DIR, "AEDS", "source-data", "NACAdata", "polar")

ANOMALY_TYPES = ["negative_cd", "extreme_cl", "extreme_ld"]

def parse_polar_file(filepath):
    """解析 Polar 文件"""
    with open(filepath, "r") as f:
        lines = f.readlines()
    
    header_lines = []
    data_start = 0
    for i, line in enumerate(lines):
        header_lines.append(line)
        if "alpha" in line and ("CL" in line or "CD" in line):
            data_start = i + 1
            break
    
    data_lines = lines[data_start:]
    records = []
    for line in data_lines:
        stripped = line.strip()
        if not stripped:
            continue
        parts = stripped.split()
        if len(parts) >= 3:
            try:
                rec = {
                    "alpha": float(parts[0]),
                    "cl": float(parts[1]),
                    "cd": float(parts[2]),
                }
                records.append(rec)
            except ValueError:
                pass
    
    return header_lines, records


def inject_anomaly(records, anomaly_type):
    """在一个记录中注入特定类型的异常"""
    if not records:
        return False
    
    idx = random.randint(0, len(records) - 1)
    rec = records[idx]
    
    if anomaly_type == "negative_cd":
        # Cd 设为负值 (正常值 ~0.01-0.1)
        rec["cd"] = -abs(rec["cd"]) * random.uniform(0.5, 2.0)
        rec["anomaly_type"] = "negative_cd"
        rec["anomaly_desc"] = f"Cd为负值 ({rec['cd']:.6f})"
        
    elif anomaly_type == "extreme_cl":
        # Cl 放大 4 倍
        rec["cl"] = rec["cl"] * random.uniform(3.5, 5.0)
        rec["anomaly_type"] = "extreme_cl"
        rec["anomaly_desc"] = f"Cl异常偏高 ({rec['cl']:.6f})"
        
    elif anomaly_type == "extreme_ld":
        # 升阻比异常（使 Cd 极小）
        rec["cd"] = rec["cd"] * random.uniform(0.01, 0.05)
        rec["anomaly_type"] = "extreme_ld"
        rec["anomaly_desc"] = f"Cd异常偏低导致升阻比偏离 ({rec['cd']:.6f})"
    
    return True


def count_total_records(polar_dir):
    """统计所有 Polar 文件的总记录数"""
    total = 0
    for af_dir_name in sorted(os.listdir(polar_dir)):
        af_dir = os.path.join(polar_dir, af_dir_name)
        if not os.path.isdir(af_dir):
            continue
        for txt_file in os.listdir(af_dir):
            if not txt_file.endswith(".txt"):
                continue
            _, records = parse_polar_file(os.path.join(af_dir, txt_file))
            total += len(records)
    return total


def save_polar_file(filepath, header_lines, records):
    """保存 Polar 文件"""
    with open(filepath, "w") as f:
        for line in header_lines:
            f.write(line.rstrip() + "\n")
        for rec in records:
            cl = rec["cl"]
            cd = rec["cd"]
            f.write(f"{rec['alpha']:+7.2f}  {cl:+10.6f}  {cd:+10.6f}  {0.0:>10.6f}  {0.0:>10.6f}  {0.0:>9.6f}  {0.0:>9.6f}\n")


def main():
    print("=" * 60)
    print("异常数据注入器")
    print("=" * 60)
    
    total_records = count_total_records(POLAR_DIR)
    inject_count = max(1, int(total_records * 0.01))  # 约 1%
    
    print(f"\nPolar 记录总数: {total_records}")
    print(f"计划注入异常: {inject_count} 条 ({inject_count/total_records*100:.1f}%)")
    
    anomaly_log = []
    injected = 0
    
    # 收集所有文件及其记录数，按比例分配异常
    file_info = []
    for af_dir_name in sorted(os.listdir(POLAR_DIR)):
        af_dir = os.path.join(POLAR_DIR, af_dir_name)
        if not os.path.isdir(af_dir):
            continue
        for txt_file in sorted(os.listdir(af_dir)):
            if not txt_file.endswith(".txt"):
                continue
            filepath = os.path.join(af_dir, txt_file)
            header_lines, records = parse_polar_file(filepath)
            file_info.append({
                "filepath": filepath,
                "header": header_lines,
                "records": records,
                "af_name": af_dir_name,
                "txt_name": txt_file,
            })
    
    # 随机分配异常
    all_files = file_info.copy()
    random.shuffle(all_files)
    
    remaining_injects = inject_count
    for finfo in all_files:
        if remaining_injects <= 0:
            break
        
        records = finfo["records"]
        if not records:
            continue
        
        # 每个文件最多注入 2 个异常
        max_for_file = min(remaining_injects, max(1, len(records) // 50), 2)
        
        for _ in range(max_for_file):
            anomaly_type = random.choice(ANOMALY_TYPES)
            success = inject_anomaly(records, anomaly_type)
            if success:
                injected += 1
                remaining_injects -= 1
                anomaly_log.append({
                    "file": f"{finfo['af_name']}/{finfo['txt_name']}",
                    "alpha": records[-1]["alpha"] if "alpha" in records[-1] else None,
                    "type": anomaly_type,
                })
    
    # 写回文件
    for finfo in all_files:
        save_polar_file(finfo["filepath"], finfo["header"], finfo["records"])
    
    print(f"\n实际注入: {injected} 条异常")
    print(f"\n异常类型分布:")
    type_count = {}
    for log in anomaly_log:
        t = log["type"]
        type_count[t] = type_count.get(t, 0) + 1
    for t, c in sorted(type_count.items()):
        print(f"  {t}: {c} 条")
    
    print(f"\n异常记录样例:")
    for log in anomaly_log[:5]:
        print(f"  [{log['type']}] {log['file']}")
    
    print(f"\n{'='*60}")
    print("异常注入完成")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()