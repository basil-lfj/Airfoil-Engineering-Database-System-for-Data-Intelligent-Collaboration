"""
使用简化物理模型生成 Polar 性能数据
为所有翼型生成多 Re 条件下的性能记录 (Cl, Cd, 升阻比)

模型：
- Cl = 2π * sin(α) * f(Re) [带失速修正]
- Cd = 0.008 + 0.01*Cl^2 + 0.00015*α^2
- 攻角范围: -5° 到 20°, 步长 0.5°
- Re 条件: 0.050, 0.070, 0.100 (百万)
"""

import os
import math
import random

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FOILS_DIR = os.path.join(BASE_DIR, "AEDS", "source-data", "NACAdata", "foils")
POLAR_DIR = os.path.join(BASE_DIR, "AEDS", "source-data", "NACAdata", "polar")


def compute_cl(alpha_deg, reynolds_number, thickness_ratio=0.12, camber=0):
    """计算升力系数 Cl"""
    alpha_rad = math.radians(alpha_deg)
    
    # 基础升力线斜率 2π
    cl_slope = 2 * math.pi
    
    # 厚度修正
    thickness_factor = 1 + 0.3 * thickness_ratio
    
    # Re 修正
    re_factor = 1 - 0.02 / (reynolds_number + 0.01)
    
    # 零升力迎角 (有弯度时)
    alpha_zero_lift = -camber * 0.08  # 弯度造成的零升力迎角偏移
    
    # 有效攻角
    effective_alpha = alpha_deg - alpha_zero_lift
    
    # 线性段
    cl_linear = cl_slope * math.sin(alpha_rad) * thickness_factor * re_factor
    
    # 失速修正 (15° 左右开始失速)
    stall_angle = 14 + thickness_ratio * 5
    if effective_alpha > stall_angle:
        stall_factor = math.exp(-0.3 * (effective_alpha - stall_angle))
        cl = cl_linear * (0.8 + 0.2 * stall_factor)
    elif effective_alpha < -5:
        cl = cl_linear * 0.6
    else:
        cl = cl_linear
    
    # 确保 Cl 不会无限大
    cl = max(-3.0, min(3.0, cl))
    
    return cl


def compute_cd(alpha_deg, cl, reynolds_number):
    """计算阻力系数 Cd"""
    # 零升阻力 (Re 相关)
    cd0 = 0.008 + 0.002 / (reynolds_number + 0.001)
    
    # 诱导阻力
    cd_induced = 0.01 * cl * cl
    
    # 角度相关阻力
    alpha_rad = math.radians(alpha_deg)
    cd_alpha = 0.00015 * alpha_deg * alpha_deg
    
    # 失速阻力增量
    if alpha_deg > 14:
        stall_drag = 0.001 * (alpha_deg - 14) ** 2
    elif alpha_deg < -3:
        stall_drag = 0.0005 * (alpha_deg + 3) ** 2
    else:
        stall_drag = 0
    
    cd = cd0 + cd_induced + cd_alpha + stall_drag
    
    return cd


def get_airfoil_thickness(name):
    """从翼型名称估算厚度比"""
    import re
    numbers = re.findall(r"\d+", name)
    for num in numbers:
        if len(num) >= 2:
            t = int(num[-2:])
            if 1 <= t <= 99:
                return t / 100.0
    return 0.12


def get_airfoil_camber(name):
    """从 NACA 编码估算弯度"""
    import re
    numbers = re.findall(r"\d{4}", name)
    for num in numbers:
        m = int(num[0])
        if 0 <= m <= 9:
            return m / 100.0
    return 0.0


def generate_polar_data(airfoil_name):
    """为一个翼型生成 Polar 性能数据"""
    thickness = get_airfoil_thickness(airfoil_name)
    camber = get_airfoil_camber(airfoil_name)
    
    # Re 条件列表
    re_conditions = [0.050, 0.070, 0.100]
    
    # 攻角范围 -5° 到 20°，步长 0.5°
    alpha_values = [i * 0.5 for i in range(-10, 41)]
    
    all_records = []
    
    for re_condition in re_conditions:
        records = []
        for alpha in alpha_values:
            cl = compute_cl(alpha, re_condition, thickness, camber)
            cd = compute_cd(alpha, cl, re_condition)
            
            # 升阻比
            ld_ratio = cl / cd if cd > 0 else 0
            
            records.append({
                "alpha": round(alpha, 1),
                "cl": round(cl, 6),
                "cd": round(cd, 6),
                "cl_cd": round(ld_ratio, 2),
            })
        
        all_records.append({
            "reynolds": re_condition,
            "records": records,
            "mach": 0.0,
            "ncrit": 5.0,
        })
    
    return all_records


def save_polar(polar_data, airfoil_name, output_dir):
    """保存 Polar 数据到文件"""
    safe_name = airfoil_name.replace(" ", "_").replace("/", "_").replace(",", "_").replace("(", "").replace(")", "").replace("=", "_")
    af_dir = os.path.join(output_dir, f"NACA-{safe_name}")
    os.makedirs(af_dir, exist_ok=True)
    
    saved_files = []
    for condition in polar_data:
        re_val = condition["reynolds"]
        filename = f"T1_Re{re_val:.3f}_M{condition['mach']:.2f}_N{condition['ncrit']:.1f}.txt"
        filepath = os.path.join(af_dir, filename)
        
        with open(filepath, "w") as f:
            f.write(f"# {airfoil_name}\n")
            f.write(f"# Generated polar data using simplified physics model\n")
            f.write(f"# Re = {re_val:.3f} million, Mach = {condition['mach']:.2f}, Ncrit = {condition['ncrit']:.1f}\n")
            f.write(f"# alpha    CL          CD          CDp         CM       Top_Xtr   Bot_Xtr\n")
            for rec in condition["records"]:
                f.write(f"{rec['alpha']:+7.2f}  {rec['cl']:+10.6f}  {rec['cd']:+10.6f}  {0.0:>10.6f}  {0.0:>10.6f}  {0.0:>9.6f}  {0.0:>9.6f}\n")
        
        saved_files.append(filepath)
    
    return saved_files


def main():
    print("=" * 60)
    print("Polar 性能数据生成器")
    print("=" * 60)
    
    csv_files = sorted([f for f in os.listdir(FOILS_DIR) if f.endswith(".csv")])
    print(f"\n翼型总数: {len(csv_files)}")
    
    os.makedirs(POLAR_DIR, exist_ok=True)
    
    total_records = 0
    total_files = 0
    
    for csv_file in csv_files:
        af_name = csv_file.replace(".csv", "")
        af_display = af_name[:50]
        
        # 生成极曲线数据
        polar_data = generate_polar_data(af_name)
        
        # 保存
        saved = save_polar(polar_data, af_name, POLAR_DIR)
        
        records_count = sum(len(c["records"]) for c in polar_data)
        total_records += records_count
        total_files += len(saved)
        
        print(f"  [{saved[0].split(os.sep)[-2]}] {records_count} 条记录 / {len(saved)} 个文件")
    
    print(f"\n{'='*60}")
    print(f"生成总计:")
    print(f"  Polar 文件: {total_files} 个")
    print(f"  性能记录: {total_records} 条")
    print(f"  覆盖翼型: {len(csv_files)} 个")
    print(f"  Re 条件/翼型: 3 个 (0.050, 0.070, 0.100)")
    print(f"  攻角范围: -5° ~ 20°, 步长 0.5°")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()