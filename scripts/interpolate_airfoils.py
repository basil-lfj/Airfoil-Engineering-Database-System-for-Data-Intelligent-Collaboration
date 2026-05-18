"""
对坐标点不足 80 的翼型进行样条插值加密
保留原有 99+ 点的翼型不变
使用线性插值方法保证翼型轮廓平滑
"""

import os
import numpy as np
from scipy import interpolate

FOILS_DIR = r"c:\Users\ASUS\Desktop\Databaselab\Bigwork\AEDS\source-data\NACAdata\foils"
TARGET_POINTS = 100  # 统一加密到 100 点


def parse_csv(filepath):
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
                if 0 <= x <= 1.0:
                    coords.append((x, y))
            except ValueError:
                pass
    return name, coords


def interpolate_airfoil(coords, n_points=TARGET_POINTS):
    """
    对翼型坐标进行插值加密
    策略：按上表面和下表面分别插值，保持翼型形状"
    """
    if len(coords) < 3:
        return coords
    
    # 找到前缘点（x 最小值）
    le_idx = min(range(len(coords)), key=lambda i: coords[i][0])
    
    # 分割为上表面和下表面
    upper = coords[:le_idx + 1]
    lower = coords[le_idx:]
    
    # 上下表面应该分别插值
    def interpolate_curve(points, num):
        if len(points) < 2:
            return points * num if points else []
        if len(points) == 2:
            return [points[0]] + points * (num - 2) + [points[-1]]
        
        pts = np.array(points)
        dist = np.cumsum(np.sqrt(np.sum(np.diff(pts, axis=0)**2, axis=1)))
        dist = np.insert(dist, 0, 0)
        dist = dist / dist[-1] if dist[-1] > 0 else dist
        
        # 使用样条插值
        tck_u, _ = interpolate.splprep([pts[:, 0], pts[:, 1]], u=dist, s=0, k=min(3, len(points) - 1))
        u_new = np.linspace(0, 1, num)
        new_pts = interpolate.splev(u_new, tck_u)
        return list(zip(new_pts[0], new_pts[1]))
    
    # 计算上下表面各需要多少点
    total = len(upper) + len(lower) - 1  # 减去重复的前缘
    upper_ratio = len(upper) / total
    n_upper = max(2, int(n_points * upper_ratio))
    n_lower = n_points - n_upper + 1  # +1 因为前缘点重复
    
    # 插值
    new_upper = interpolate_curve(upper, n_upper)
    new_lower = interpolate_curve(lower, n_lower)
    
    # 合并（去除前缘重复点）
    result = new_upper[:-1] + new_lower
    return result


def main():
    print("=" * 60)
    print("翼型坐标点插值加密")
    print("=" * 60)
    
    if TARGET_POINTS < 80:
        print(f"[WARN] 目标点数 {TARGET_POINTS} < 80，可能不满足要求")
    
    csv_files = sorted([f for f in os.listdir(FOILS_DIR) if f.endswith(".csv")])
    print(f"\nCSV 文件总数: {len(csv_files)}")
    
    try:
        from scipy import interpolate
        has_scipy = True
    except ImportError:
        has_scipy = False
        print("[WARN] scipy 未安装，使用线性插值")
    
    interpolated_count = 0
    kept_count = 0
    
    for csv_file in csv_files:
        filepath = os.path.join(FOILS_DIR, csv_file)
        name, coords = parse_csv(filepath)
        current_pts = len(coords)
        
        if current_pts >= TARGET_POINTS:
            print(f"  [保留] {csv_file:<50} {current_pts} 点 (>= {TARGET_POINTS})")
            kept_count += 1
            continue
        
        # 需要插值
        new_coords = interpolate_airfoil(coords, TARGET_POINTS)
        
        if len(new_coords) < 80:
            print(f"  [WARN] {csv_file}: 插值后只有 {len(new_coords)} 点")
        
        # 写回文件
        with open(filepath, "w") as f:
            f.write(f"{name}\n")
            for x, y in new_coords:
                f.write(f"{x:.6f},{y:.6f}\n")
        
        print(f"  [插值] {csv_file:<50} {current_pts} -> {len(new_coords)} 点")
        interpolated_count += 1
    
    print(f"\n{'='*60}")
    print(f"插值前 < {TARGET_POINTS} 点的: {interpolated_count} 个")
    print(f"已满足 >= {TARGET_POINTS} 点的: {kept_count} 个")
    print(f"当前翼型总数: {len(csv_files)}")
    
    # 最终统计
    print(f"\n{'='*60}")
    print("最终坐标统计")
    print(f"{'='*60}")
    total_pts = 0
    for csv_file in sorted(os.listdir(FOILS_DIR)):
        if not csv_file.endswith(".csv"):
            continue
        with open(os.path.join(FOILS_DIR, csv_file)) as f:
            pts = len(f.readlines()) - 1
        total_pts += pts
    print(f"翼型总数: {len(csv_files)}")
    print(f"总坐标点数: {total_pts}")
    print(f"平均每翼型: {total_pts // len(csv_files)} 点")


if __name__ == "__main__":
    main()