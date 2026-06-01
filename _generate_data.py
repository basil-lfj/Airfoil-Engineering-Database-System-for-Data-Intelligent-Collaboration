import csv
import math
import os
import random
import re
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
FOILS_DIR = BASE_DIR / "source-data" / "NACAdata" / "foils"
POLAR_DIR = BASE_DIR / "source-data" / "NACAdata" / "polar"
OUTPUT_DIR = BASE_DIR / "project_data" / "output"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
random.seed(42)


def read_foil_csv(filepath):
    with open(filepath, "r") as f:
        lines = f.readlines()
    name = lines[0].strip()
    coords = []
    for line in lines[1:]:
        line = line.strip()
        if not line:
            continue
        parts = line.split(",")
        if len(parts) == 2:
            try:
                x, y = float(parts[0]), float(parts[1])
                if 0 <= x <= 1:
                    coords.append((x, y))
            except ValueError:
                pass
    return name, coords


def make_airfoil_code(filename):
    stem = filename.replace(".csv", "").strip()
    stem = re.sub(r"\s+", "_", stem)
    return stem


def infer_surface(idx, total):
    half = total // 2
    return "upper" if idx < half else "lower"


def generate_version_id(airfoil_code, version_no):
    return f"{airfoil_code}_v{version_no}"


def read_polar_file(filepath):
    records = []
    with open(filepath, "r") as f:
        content = f.read()
    lines = content.strip().split("\n")
    reynolds = 50000
    for line in lines:
        if "Re =" in line:
            parts = line.split()
            for i, p in enumerate(parts):
                if p == "Re" and i + 2 < len(parts):
                    try:
                        re_str = parts[i + 1].replace(",", "")
                        reynolds = int(float(re_str))
                    except ValueError:
                        pass
                    break
    data_start = 0
    for i, line in enumerate(lines):
        if "alpha" in line and ("CL" in line or "CD" in line):
            data_start = i + 1
            break
    for line in lines[data_start:]:
        parts = line.strip().split()
        if len(parts) >= 3:
            try:
                alpha = float(parts[0])
                cl = float(parts[1])
                cd = float(parts[2])
                records.append({"alpha_deg": alpha, "reynolds_number": reynolds, "cl": cl, "cd": cd})
            except ValueError:
                pass
    return records


def find_polar_dir(airfoil_code):
    candidates = [
        POLAR_DIR / f"NACA-{airfoil_code}",
        POLAR_DIR / f"NACA-NACA_{airfoil_code}",
    ]
    no_prefix = re.sub(r"^NACA_?", "", airfoil_code)
    if no_prefix != airfoil_code:
        candidates.append(POLAR_DIR / f"NACA-{no_prefix}")
        candidates.append(POLAR_DIR / f"NACA-NACA_{no_prefix}")
    alt = airfoil_code.replace("_", "-")
    candidates.append(POLAR_DIR / f"NACA-{alt}")
    candidates.append(POLAR_DIR / f"NACA-NACA_{alt}")
    for d in candidates:
        if d.exists():
            return d
    return None


def synthetic_performance(alpha_deg, reynolds_number):
    alpha_rad = math.radians(alpha_deg)
    cl = 2 * math.pi * math.sin(alpha_rad) * (reynolds_number / 1000000) ** 0.05
    if alpha_deg > 12:
        cl *= max(0.6, 1.0 - 0.08 * (alpha_deg - 12))
    elif alpha_deg < -4:
        cl *= 0.6
    cd = 0.008 + 0.01 * cl * cl + 0.00015 * alpha_deg * alpha_deg
    cl *= random.normalvariate(1.0, 0.02)
    cd *= random.normalvariate(1.0, 0.03)
    return max(cl, -3), max(cd, 0.0001)


def maybe_inject_anomaly(cl, cd):
    if random.random() >= 0.008:
        return cl, cd, False
    atype = random.choice(["negative_cd", "extreme_cl", "extreme_ld"])
    if atype == "negative_cd":
        return cl, -abs(cd), True
    elif atype == "extreme_cl":
        return cl * 4.0, cd, True
    else:
        return cl, max(cd * 0.05, 1e-6), True


def main():
    print("=" * 60)
    print("翼型工程数据库 - 完整数据生成器 (100翼型)")
    print("=" * 60)
    foil_files = sorted([f for f in FOILS_DIR.glob("*.csv")])
    print(f"\n发现翼型文件: {len(foil_files)}")
    airfoil_rows, version_rows, coordinate_rows, performance_rows, anomaly_rows = [], [], [], [], []

    re_list = [50000, 100000, 300000, 500000, 1000000]
    alpha_list = list(range(-4, 16, 2))

    for filepath in foil_files:
        name, coords = read_foil_csv(filepath)
        if not coords:
            continue
        airfoil_code = make_airfoil_code(filepath.name)
        file_stem = filepath.stem

        airfoil_rows.append({
            "airfoil_id": airfoil_code,
            "name": name,
            "geom_source": "UIUC Airfoil Coordinates Database",
            "geom_source_url": "https://m-selig.ae.illinois.edu/ads/coord_database.html",
            "family": "naca",
            "is_generated": 0,
        })

        base_version_id = generate_version_id(airfoil_code, 1)
        version_rows.append({
            "version_id": base_version_id,
            "airfoil_id": airfoil_code,
            "version_no": 1,
            "version_type": "imported_raw",
            "geom_source": "UIUC Airfoil Coordinates Database",
            "geom_source_url": "https://m-selig.ae.illinois.edu/ads/coord_database.html",
        })

        for idx, (x, y) in enumerate(coords):
            coordinate_rows.append({
                "airfoil_id": airfoil_code, "version_id": base_version_id,
                "point_order": idx + 1, "x": f"{x:.6f}", "y": f"{y:.6f}",
                "surface": infer_surface(idx, len(coords)),
                "geom_source": "UIUC Airfoil Coordinates Database",
                "geom_source_url": "https://m-selig.ae.illinois.edu/ads/coord_database.html",
                "is_generated": 0, "raw_file": filepath.name,
            })

        polar_dir = find_polar_dir(file_stem)
        has_real_polar = False
        if polar_dir:
            for txt_file in sorted(polar_dir.glob("*.txt")):
                polar_recs = read_polar_file(txt_file)
                for rec in polar_recs:
                    cl, cd = rec["cl"], rec["cd"]
                    is_anom = False
                    if cd < 0:
                        is_anom = True
                    performance_rows.append({
                        "airfoil_id": airfoil_code,
                        "version_id": base_version_id,
                        "alpha_deg": rec["alpha_deg"], "reynolds_number": rec["reynolds_number"],
                        "cl": f"{cl:.6f}", "cd": f"{cd:.6f}",
                        "perf_source": "real", "perf_rule": "UIUC_experimental",
                        "is_anomaly": 1 if is_anom else 0,
                    })
                    has_real_polar = True

        for k in range(2, 6):
            version_id = generate_version_id(airfoil_code, k)
            version_rows.append({
                "version_id": version_id, "airfoil_id": airfoil_code,
                "version_no": k, "version_type": "generated_variant",
                "geom_source": "generated_from_base", "geom_source_url": "",
            })
            ts = random.normalvariate(1.0, 0.01)
            cs = random.normalvariate(0.0, 0.002)
            for idx, (x, y) in enumerate(coords):
                new_y = y * ts + cs
                coordinate_rows.append({
                    "airfoil_id": airfoil_code, "version_id": version_id,
                    "point_order": idx + 1, "x": f"{x:.6f}", "y": f"{new_y:.6f}",
                    "surface": infer_surface(idx, len(coords)),
                    "geom_source": "generated_from_base", "geom_source_url": "",
                    "is_generated": 1, "raw_file": "",
                })
            for re in re_list:
                for alpha in alpha_list:
                    if has_real_polar and k <= 3:
                        cl, cd = synthetic_performance(alpha, re)
                    else:
                        cl, cd = synthetic_performance(alpha, re)
                    cl, cd, is_anom = maybe_inject_anomaly(cl, cd)
                    performance_rows.append({
                        "airfoil_id": airfoil_code, "version_id": version_id,
                        "alpha_deg": alpha, "reynolds_number": re,
                        "cl": f"{cl:.6f}", "cd": f"{cd:.6f}",
                        "perf_source": "synthetic", "perf_rule": "synthetic_aero_model_v1",
                        "is_anomaly": 1 if is_anom else 0,
                    })

    print(f"\n翼型: {len(airfoil_rows)} | 版本: {len(version_rows)} | 坐标: {len(coordinate_rows)} | 性能: {len(performance_rows)}")

    def write_csv(filename, fieldnames, rows):
        path = OUTPUT_DIR / filename
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=fieldnames)
            w.writeheader()
            w.writerows(rows)
        print(f"  {filename}: {len(rows)} rows")

    write_csv("airfoils.csv",
        ["airfoil_id", "name", "geom_source", "geom_source_url", "family", "is_generated"],
        airfoil_rows)
    write_csv("data_versions.csv",
        ["version_id", "airfoil_id", "version_no", "version_type", "geom_source", "geom_source_url"],
        version_rows)
    write_csv("coordinates.csv",
        ["airfoil_id", "version_id", "point_order", "x", "y", "surface",
         "geom_source", "geom_source_url", "is_generated", "raw_file"],
        coordinate_rows)
    write_csv("performance.csv",
        ["airfoil_id", "version_id", "alpha_deg", "reynolds_number",
         "cl", "cd", "perf_source", "perf_rule", "is_anomaly"],
        performance_rows)

    aid = 0
    anom_out = []
    for pr in performance_rows:
        if pr["is_anomaly"] == 1:
            aid += 1
            anom_out.append({
                "anomaly_id": aid, "airfoil_id": pr["airfoil_id"],
                "version_id": pr["version_id"], "alpha_deg": pr["alpha_deg"],
                "reynolds_number": pr["reynolds_number"], "rule": "auto_detected",
                "cl": pr["cl"], "cd": pr["cd"],
                "ld": f"{float(pr['cl']) / max(float(pr['cd']), 0.0001):.2f}",
            })
    write_csv("anomalies.csv",
        ["anomaly_id", "airfoil_id", "version_id", "alpha_deg", "reynolds_number",
         "rule", "cl", "cd", "ld"],
        anom_out)

    print(f"\n✅ 全部数据已生成到: {OUTPUT_DIR}")


if __name__ == "__main__":
    main()