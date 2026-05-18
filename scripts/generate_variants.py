"""
基于现有翼型生成厚度缩放变体 (版本数据)
每个原始翼型生成 4 个变体（±3%, ±6% 厚度缩放）
"""

import os
import math
import csv

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FOILS_DIR = os.path.join(BASE_DIR, "AEDS", "source-data", "NACAdata", "foils")
VARIANT_DIR = os.path.join(BASE_DIR, "AEDS", "source-data", "NACAdata", "variants")


def parse_airfoil_coords(filepath):
    """解析翼型坐标文件"""
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


def thickness_scaling(coords, scale_factor):
    """
    对翼型坐标做厚度缩放
    scale_factor = 1.0 表示不变
    scale_factor > 1.0 表示增厚
    scale_factor < 1.0 表示减薄
    
    方法：保持 x 不变，将 y 值相对于弦线（y=0）缩放
    """
    new_coords = []
    for x, y in coords:
        new_y = y * scale_factor
        new_coords.append((x, new_y))
    return new_coords


def save_airfoil_coords(coords, name, filepath):
    """将坐标保存为 CSV 格式"""
    with open(filepath, "w") as f:
        f.write(f"{name}\n")
        for x, y in coords:
            f.write(f"{x:.6f},{y:.6f}\n")


def get_naca_thickness(naca_name):
    """从 NACA 4位数编码中提取厚度百分数"""
    parts = naca_name.split()
    for part in parts:
        if part.isdigit() and len(part) == 4:
            return int(part[2:])  # 最后两位是厚度
    return None


def main():
    print("=" * 60)
    print("翼型变体生成器（厚度缩放）")
    print("=" * 60)
    
    # 获取原始翼型文件
    original_csvs = sorted([
        f for f in os.listdir(FOILS_DIR)
        if f.endswith(".csv") and f.startswith("NACA")
    ])
    
    if not original_csvs:
        print("[错误] 未在 {} 中找到 NACA CSV 文件".format(FOILS_DIR))
        return
    
    print("\n原始翼型: {} 个".format(len(original_csvs)))
    
    os.makedirs(VARIANT_DIR, exist_ok=True)
    
    # 厚度缩放因子
    scale_factors = {
        "thick_plus_3": 1.03,
        "thick_plus_6": 1.06,
        "thick_minus_3": 0.97,
        "thick_minus_6": 0.94,
    }
    
    total_variants = 0
    variant_info = []
    
    for csv_file in original_csvs:
        filepath = os.path.join(FOILS_DIR, csv_file)
        name, coords = parse_airfoil_coords(filepath)
        
        basename = csv_file.replace(".csv", "")
        
        for variant_name, scale in sorted(scale_factors.items()):
            # 生成变体坐标
            new_coords = thickness_scaling(coords, scale)
            
            # 生成变体文件名和名称
            scaled_pct = int(round((scale - 1) * 100))
            sign = "+" if scaled_pct >= 0 else ""
            variant_label = "{} ({}{}% thickness)".format(basename, sign, scaled_pct)
            
            variant_csv = "{}_thick{}.csv".format(basename, variant_name.replace("thick_", "").replace("plus", "p").replace("minus", "m"))
            variant_path = os.path.join(VARIANT_DIR, variant_csv)
            
            save_airfoil_coords(new_coords, variant_label, variant_path)
            total_variants += 1
            
            variant_info.append({
                "original": basename,
                "variant_file": variant_csv,
                "variant_label": variant_label,
                "scale": scale,
                "points": len(new_coords),
                "version_type": "generated_variant"
            })
            
            print("  + {} -> {} (缩放到 {:.0%} 厚度)".format(basename, variant_label, scale))
    
    print("\n[完成] 生成 {} 个变体文件".format(total_variants))
    print("[路径] 保存在: {}".format(VARIANT_DIR))
    
    # 生成变体索引文件
    idx_path = os.path.join(VARIANT_DIR, "_variant_index.csv")
    with open(idx_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["original", "variant_file", "variant_label", "scale", "points", "version_type"])
        writer.writeheader()
        writer.writerows(variant_info)
    
    print("[索引] 变体索引: {}".format(idx_path))
    print("\n=== 版本数据总览 ===")
    print("  原始翼型: {} 个".format(len(original_csvs)))
    print("  变体翼型: {} 个".format(total_variants))
    print("  版本类型: imported_raw (原始) + generated_variant (变体)")
    print("  合计: {} 个翼型".format(len(original_csvs) + total_variants))


if __name__ == "__main__":
    main()