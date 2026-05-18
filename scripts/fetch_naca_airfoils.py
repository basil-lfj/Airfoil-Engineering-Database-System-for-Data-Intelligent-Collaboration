"""
从 UIUC Airfoil Database 爬取 NACA 系列翼型坐标数据
策略：
1. 从 coord_seligFmt.zip 下载完整压缩包 (~5MB)
2. 解压并筛选出文件名包含 'naca' 的文件
3. 将其转换为 CSV 格式
"""

import os
import re
import shutil
import urllib.request
import zipfile
import io

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NACA_DIR = os.path.join(BASE_DIR, "AEDS", "source-data", "NACAdata", "foils")

DAT_URL = "https://m-selig.ae.illinois.edu/ads/archives/coord_seligFmt.zip"
DOWNLOAD_DIR = os.path.join(BASE_DIR, "scripts", "_download")


def download_zip(url, save_dir):
    """下载 UIUC 数据库 zip 包"""
    os.makedirs(save_dir, exist_ok=True)
    zip_path = os.path.join(save_dir, "coord_seligFmt.zip")
    
    if os.path.exists(zip_path):
        print(f"[跳过] zip 文件已存在: {zip_path}")
        return zip_path
    
    print(f"[下载] {url} -> {zip_path}")
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) "
                          "Chrome/120.0.0.0 Safari/537.36"
        }
    )
    with urllib.request.urlopen(req) as response:
        with open(zip_path, "wb") as f:
            shutil.copyfileobj(response, f)
    print(f"[完成] 下载完成: {os.path.getsize(zip_path) / 1024:.1f} KB")
    return zip_path


def extract_naca_files(zip_path, output_dir):
    """解压并筛选 NACA 系列翼型文件"""
    os.makedirs(output_dir, exist_ok=True)
    
    # NACA 文件命名模式
    naca_pattern = re.compile(r"naca\d{4,5}", re.IGNORECASE)
    
    found_files = []
    
    with zipfile.ZipFile(zip_path, "r") as zf:
        all_files = [f for f in zf.namelist() if f.endswith(".dat")]
        print(f"\n[扫描] zip 包中共 {len(all_files)} 个 .dat 文件")
        
        for filename in sorted(all_files):
            basename = os.path.basename(filename)
            # 检查文件名是否包含 'naca'
            if "naca" in basename.lower():
                found_files.append(filename)
                # 提取内容
                content = zf.read(filename).decode("utf-8", errors="replace")
                # 写入到输出目录
                out_path = os.path.join(output_dir, basename)
                with open(out_path, "w", encoding="utf-8") as f:
                    f.write(content)
    
    print(f"[筛选] 找到 {len(found_files)} 个 NACA 系列文件")
    return found_files


def analyze_naca_files(directory):
    """分析每个 NACA 文件的基础信息"""
    results = []
    
    for fname in sorted(os.listdir(directory)):
        if not fname.endswith(".dat"):
            continue
        
        fpath = os.path.join(directory, fname)
        with open(fpath, "r") as f:
            lines = f.readlines()
        
        # 第一行是翼型名称
        name_line = lines[0].strip()
        
        # 过滤注释行和空行
        coord_lines = []
        for line in lines:
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            parts = stripped.split()
            if len(parts) >= 2:
                try:
                    float(parts[0])
                    float(parts[1])
                    coord_lines.append((float(parts[0]), float(parts[1])))
                except ValueError:
                    pass
        
        # 分析坐标分布
        if coord_lines:
            xs = [p[0] for p in coord_lines]
            upper = len([p for p in coord_lines if p[1] >= 0])
            lower = len([p for p in coord_lines if p[1] < 0])
            
            results.append({
                "filename": fname,
                "name": name_line,
                "coords": len(coord_lines),
                "x_min": min(xs),
                "x_max": max(xs),
                "upper_count": upper,
                "lower_count": lower,
            })
    
    return results


def convert_dat_to_csv(dat_path, csv_path):
    """将 .dat 文件转换为标准 CSV 格式"""
    with open(dat_path, "r") as f:
        lines = f.readlines()
    
    name_line = lines[0].strip()
    
    # 提取坐标
    coords = []
    for line in lines[1:]:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        parts = stripped.split()
        if len(parts) >= 2:
            try:
                x, y = float(parts[0]), float(parts[1])
                coords.append((x, y))
            except ValueError:
                pass
    
    with open(csv_path, "w") as f:
        f.write(f"{name_line}\n")
        for x, y in coords:
            f.write(f"{x:.6f},{y:.6f}\n")
    
    return len(coords)


def main():
    print("=" * 60)
    print("NACA 翼型数据爬取与转换")
    print("=" * 60)
    
    # Step 1: 下载 zip
    print("\n[Step 1] 下载 UIUC 数据库压缩包...")
    zip_path = download_zip(DAT_URL, DOWNLOAD_DIR)
    
    # Step 2: 解压 NACA 文件
    print("\n[Step 2] 提取 NACA 系列文件...")
    naca_temp = os.path.join(DOWNLOAD_DIR, "naca_raw")
    naca_files = extract_naca_files(zip_path, naca_temp)
    
    if not naca_files:
        print("[错误] 未找到 NACA 系列文件！")
        return
    
    # Step 3: 分析文件
    print("\n[Step 3] 分析 NACA 文件...")
    analysis = analyze_naca_files(naca_temp)
    
    print(f"\n{'文件名':<25} {'翼型名称':<30} {'坐标点数':<10} {'上表面':<8} {'下表面':<8}")
    print("-" * 81)
    for r in sorted(analysis, key=lambda x: x["filename"]):
        print(f"{r['filename']:<25} {r['name']:<30} {r['coords']:<10} {r['upper_count']:<8} {r['lower_count']:<8}")
    
    # Step 4: 转换为 CSV
    print("\n[Step 4] 转换为 CSV 格式...")
    os.makedirs(NACA_DIR, exist_ok=True)
    
    existing_csvs = [f for f in os.listdir(NACA_DIR) if f.endswith(".csv") and f.startswith("NACA")]
    existing_names = set()
    for csv_f in existing_csvs:
        # Extract name without extension
        existing_names.add(csv_f.replace(".csv", ""))
    
    converted_count = 0
    skipped_count = 0
    for r in sorted(analysis, key=lambda x: x["filename"]):
        dat_path = os.path.join(naca_temp, r["filename"])
        csv_name = r["name"].replace(" ", "_").replace("/", "_").replace(":", "_")
        csv_path = os.path.join(NACA_DIR, f"{csv_name}.csv")
        
        # 检查是否已存在
        if csv_name in existing_names:
            skipped_count += 1
            continue
        
        pts = convert_dat_to_csv(dat_path, csv_path)
        if pts > 0:
            converted_count += 1
            print(f"  + {csv_name}.csv ({pts} 个坐标点)")
    
    print(f"\n[完成] 转换 {converted_count} 个新文件，跳过了 {skipped_count} 个已存在的文件")
    print(f"[路径] CSV 文件保存在: {NACA_DIR}")
    
    # Step 5: 统计
    all_csvs = [f for f in os.listdir(NACA_DIR) if f.endswith(".csv")]
    total_points = 0
    for f in all_csvs:
        with open(os.path.join(NACA_DIR, f)) as fh:
            total_points += len(fh.readlines()) - 1
    print(f"\n[统计] NACA 系列 CSV 总数: {len(all_csvs)}")
    print(f"[统计] 总坐标点数: {total_points}")


if __name__ == "__main__":
    main()
