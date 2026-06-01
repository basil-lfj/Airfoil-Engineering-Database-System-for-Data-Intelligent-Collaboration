from __future__ import annotations
import csv
import math
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple

RAW_DIR = Path("project_data/raw_uiuc")
OUT_DIR = Path("project_data/output")

OUT_DIR.mkdir(parents=True, exist_ok=True)

GEOM_SOURCE = "UIUC Airfoil Coordinates Database"
GEOM_SOURCE_URL = "https://m-selig.ae.illinois.edu/ads/coord_seligFmt/"
PERF_SOURCE = "synthetic"
PERF_RULE = "synthetic_aero_model_v1"
TARGET_AIRFOILS = 80
ANOMALY_PROB = 0.01

@dataclass
class AirfoilMeta:
    airfoil_id: str
    name: str
    geom_source: str
    geom_source_url: str
    family: str
    is_generated: bool

@dataclass
class CoordinatePoint:
    airfoil_id: str
    version_id: str
    point_order: int
    x: float
    y: float
    surface: str
    geom_source: str
    geom_source_url: str
    is_generated: bool
    raw_file: str

@dataclass
class PerformanceRecord:
    airfoil_id: str
    version_id: str
    alpha_deg: float
    reynolds_number: int
    cl: float
    cd: float
    perf_source: str
    perf_rule: str
    is_anomaly: bool

@dataclass
class AnomalyRecord:
    anomaly_id: int
    airfoil_id: str
    version_id: str
    alpha_deg: float
    reynolds_number: int
    rule: str
    cl: float
    cd: float
    ld: float

def read_uiuc_dat(file_path: Path) -> List[Tuple[float, float]]:
    coords: List[Tuple[float, float]] = []
    with file_path.open("r", encoding="utf-8", errors="ignore") as f:
        lines = f.readlines()

    for line in lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue

        parts = line.split()
        if len(parts) != 2:
            continue

        try:
            x = float(parts[0])
            y = float(parts[1])
            coords.append((x, y))
        except ValueError:
            continue

    if len(coords) < 80:
        raise ValueError(f"{file_path.name} 坐标点数量 ({len(coords)}) 少于80，不符合要求。")

    return coords

def infer_surface(point_index: int, total_points: int) -> str:
    halfway = total_points // 2
    return "upper" if point_index < halfway else "lower"

def make_version_id(airfoil_id: str, version_no: int) -> str:
    return f"{airfoil_id}_v{version_no}"

def perturb_coordinates(
    base_coords: List[Tuple[float, float]],
    thickness_scale: float,
    camber_shift: float,
) -> List[Tuple[float, float]]:
    result: List[Tuple[float, float]] = []
    for x, y in base_coords:
        new_y = y * thickness_scale + camber_shift
        result.append((x, new_y))
    return result

def synthetic_aero_model(alpha_deg: float, reynolds_number: int) -> Tuple[float, float]:
    alpha_rad = math.radians(alpha_deg)

    cl = 2 * math.pi * alpha_rad

    re_factor = (reynolds_number / 1_000_000) ** 0.05
    cl *= re_factor

    if alpha_deg > 12:
        cl *= max(0.6, 1.0 - 0.08 * (alpha_deg - 12))

    cd = 0.008 + 0.01 * (cl ** 2) + 0.00015 * (alpha_deg ** 2)

    cl *= random.normalvariate(1.0, 0.02)
    cd *= random.normalvariate(1.0, 0.03)

    return cl, max(cd, 0.0001)

def maybe_inject_anomaly(cl: float, cd: float, prob: float) -> Tuple[float, float, bool, str]:
    if random.random() >= prob:
        return cl, cd, False, ""

    anomaly_type = random.choice(["negative_cd", "extreme_cl", "extreme_ld"])

    if anomaly_type == "negative_cd":
        return cl, -abs(cd), True, anomaly_type
    if anomaly_type == "extreme_cl":
        return cl * random.uniform(3.0, 5.0), cd, True, anomaly_type
    return cl, max(cd * random.uniform(0.01, 0.1), 1e-6), True, anomaly_type


def detect_anomalies(perf: List[PerformanceRecord]) -> Tuple[List[AnomalyRecord], Dict[int, List[str]]]:
    rules_by_index: Dict[int, List[str]] = {}
    anomalies: List[AnomalyRecord] = []

    def add(i: int, rule: str):
        rules_by_index.setdefault(i, []).append(rule)

    for i, r in enumerate(perf):
        if r.cd < 0:
            add(i, "rule:negative_cd")
        if abs(r.cl) > 3.0:
            add(i, "rule:extreme_cl")
        ld = r.cl / r.cd if r.cd != 0 else float("inf")
        if r.cd > 0 and abs(ld) > 200:
            add(i, "rule:extreme_ld")

    groups: Dict[Tuple[str, str, int], List[Tuple[float, int]]] = {}
    for i, r in enumerate(perf):
        groups.setdefault((r.airfoil_id, r.version_id, r.reynolds_number), []).append((r.alpha_deg, i))

    for _, items in groups.items():
        items.sort(key=lambda x: x[0])
        prev_i: int | None = None
        prev_alpha: float | None = None
        for alpha, idx in items:
            if prev_i is not None and prev_alpha is not None:
                da = alpha - prev_alpha
                if da != 0:
                    dcl = perf[idx].cl - perf[prev_i].cl
                    if abs(dcl / da) > 0.8:
                        add(idx, "rule:jump_cl")
                        add(prev_i, "rule:jump_cl")
            prev_i = idx
            prev_alpha = alpha

    anomaly_id = 1
    for i, rules in rules_by_index.items():
        r = perf[i]
        ld = r.cl / r.cd if r.cd != 0 else float("inf")
        for rule in rules:
            anomalies.append(
                AnomalyRecord(
                    anomaly_id=anomaly_id,
                    airfoil_id=r.airfoil_id,
                    version_id=r.version_id,
                    alpha_deg=r.alpha_deg,
                    reynolds_number=r.reynolds_number,
                    rule=rule,
                    cl=r.cl,
                    cd=r.cd,
                    ld=ld,
                )
            )
            anomaly_id += 1

    return anomalies, rules_by_index

def build_dataset():
    airfoil_rows: List[AirfoilMeta] = []
    coordinate_rows: List[CoordinatePoint] = []
    performance_rows: List[PerformanceRecord] = []
    version_rows: List[Tuple[str, str, int, str, str, str]] = []
    anomaly_rows: List[AnomalyRecord] = []
    injected_counts: Dict[str, int] = {"negative_cd": 0, "extreme_cl": 0, "extreme_ld": 0}

    dat_files = sorted(RAW_DIR.glob("*.dat"))
    if not dat_files:
        raise FileNotFoundError(f"在 {RAW_DIR} 目录下未找到 .dat 文件。请确保已放置UIUC翼型数据。")

    valid_files: List[Path] = []
    invalid_files: List[Tuple[str, str]] = []
    for f in dat_files:
        try:
            read_uiuc_dat(f)
            valid_files.append(f)
        except Exception as e:
            invalid_files.append((f.name, str(e)))

    if len(valid_files) < 60:
        raise RuntimeError(f"有效翼型数量不足：{len(valid_files)}（要求至少 60）。")

    if len(valid_files) < TARGET_AIRFOILS:
        print(f"警告：有效翼型数量为 {len(valid_files)}，小于目标 {TARGET_AIRFOILS}，将使用全部有效翼型。")
        selected_files = valid_files
    else:
        selected_files = random.sample(valid_files, TARGET_AIRFOILS)

    alpha_list = list(range(-4, 18, 2))
    re_list = [100000, 300000, 500000, 1000000]

    for file_path in selected_files:
        base_id = file_path.stem.lower().replace(" ", "_").replace(".", "")
        base_name = file_path.stem

        try:
            base_coords = read_uiuc_dat(file_path)
        except ValueError as e:
            print(f"跳过文件 {file_path.name}，原因: {e}")
            continue

        base_version_no = 1
        base_version_id = make_version_id(base_id, base_version_no)

        airfoil_rows.append(
            AirfoilMeta(
                airfoil_id=base_id,
                name=base_name,
                geom_source=GEOM_SOURCE,
                geom_source_url=GEOM_SOURCE_URL,
                family="unknown",
                is_generated=False,
            )
        )
        version_rows.append((base_version_id, base_id, base_version_no, "imported_raw", GEOM_SOURCE, GEOM_SOURCE_URL))

        for idx, (x, y) in enumerate(base_coords):
            coordinate_rows.append(
                CoordinatePoint(
                    airfoil_id=base_id,
                    version_id=base_version_id,
                    point_order=idx + 1,
                    x=x,
                    y=y,
                    surface=infer_surface(idx, len(base_coords)),
                    geom_source=GEOM_SOURCE,
                    geom_source_url=GEOM_SOURCE_URL,
                    is_generated=False,
                    raw_file=file_path.name,
                )
            )

        for re in re_list:
            for alpha in alpha_list:
                cl, cd = synthetic_aero_model(alpha, re)
                cl, cd, is_injected, injected_type = maybe_inject_anomaly(cl, cd, prob=ANOMALY_PROB)
                if is_injected and injected_type:
                    injected_counts[injected_type] = injected_counts.get(injected_type, 0) + 1
                performance_rows.append(
                    PerformanceRecord(
                        airfoil_id=base_id,
                        version_id=base_version_id,
                        alpha_deg=alpha,
                        reynolds_number=re,
                        cl=cl,
                        cd=cd,
                        perf_source=PERF_SOURCE,
                        perf_rule=PERF_RULE,
                        is_anomaly=is_injected,
                    )
                )

        for k in range(2, 6):
            version_id = make_version_id(base_id, k)

            thickness_scale = random.normalvariate(1.0, 0.01)
            camber_shift = random.normalvariate(0.0, 0.002)

            new_coords = perturb_coordinates(base_coords, thickness_scale, camber_shift)
            version_rows.append((version_id, base_id, k, "generated_variant", GEOM_SOURCE, GEOM_SOURCE_URL))

            for idx, (x, y) in enumerate(new_coords):
                coordinate_rows.append(
                    CoordinatePoint(
                        airfoil_id=base_id,
                        version_id=version_id,
                        point_order=idx + 1,
                        x=x,
                        y=y,
                        surface=infer_surface(idx, len(new_coords)),
                        geom_source=GEOM_SOURCE,
                        geom_source_url=GEOM_SOURCE_URL,
                        is_generated=True,
                        raw_file=file_path.name,
                    )
                )

            for re in re_list:
                for alpha in alpha_list:
                    cl, cd = synthetic_aero_model(alpha, re)
                    cl *= random.normalvariate(1.0, 0.015)
                    cd *= random.normalvariate(1.0, 0.02)
                    cl, cd, is_injected, injected_type = maybe_inject_anomaly(cl, cd, prob=ANOMALY_PROB)
                    if is_injected and injected_type:
                        injected_counts[injected_type] = injected_counts.get(injected_type, 0) + 1
                    performance_rows.append(
                        PerformanceRecord(
                            airfoil_id=base_id,
                            version_id=version_id,
                            alpha_deg=alpha,
                            reynolds_number=re,
                            cl=cl,
                            cd=cd,
                            perf_source=PERF_SOURCE,
                            perf_rule=PERF_RULE,
                            is_anomaly=is_injected,
                        )
                    )

    detected_anomalies, rules_by_index = detect_anomalies(performance_rows)
    anomaly_rows.extend(detected_anomalies)
    for idx in rules_by_index.keys():
        performance_rows[idx].is_anomaly = True

    write_airfoils_csv(airfoil_rows)
    write_coordinates_csv(coordinate_rows)
    write_performance_csv(performance_rows)
    write_versions_csv(version_rows)
    write_anomalies_csv(anomaly_rows)

    if invalid_files:
        print(f"预处理跳过 {len(invalid_files)} 个无效几何文件（坐标点不足或格式异常）。")

    print(f"异常注入计数: negative_cd={injected_counts.get('negative_cd',0)} extreme_cl={injected_counts.get('extreme_cl',0)} extreme_ld={injected_counts.get('extreme_ld',0)}")
    print(f"规则检测异常明细行数: {len(anomaly_rows)}")

    print(f"数据生成完成。共生成 {len(airfoil_rows)} 个翼型，"
          f"{len(coordinate_rows)} 条坐标记录，"
          f"{len(performance_rows)} 条性能记录，"
          f"{len(version_rows)} 条版本记录。")

def write_airfoils_csv(rows: List[AirfoilMeta]):
    with (OUT_DIR / "airfoils.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["airfoil_id", "name", "geom_source", "geom_source_url", "family", "is_generated"])
        for r in rows:
            writer.writerow([r.airfoil_id, r.name, r.geom_source, r.geom_source_url, r.family, int(r.is_generated)])

def write_coordinates_csv(rows: List[CoordinatePoint]):
    with (OUT_DIR / "coordinates.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["airfoil_id", "version_id", "point_order", "x", "y", "surface", "geom_source", "geom_source_url", "is_generated", "raw_file"])
        for r in rows:
            writer.writerow([r.airfoil_id, r.version_id, r.point_order, r.x, r.y, r.surface, r.geom_source, r.geom_source_url, int(r.is_generated), r.raw_file])

def write_performance_csv(rows: List[PerformanceRecord]):
    with (OUT_DIR / "performance.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "airfoil_id", "version_id", "alpha_deg", "reynolds_number",
            "cl", "cd", "perf_source", "perf_rule", "is_anomaly"
        ])
        for r in rows:
            writer.writerow([
                r.airfoil_id, r.version_id, r.alpha_deg, r.reynolds_number,
                r.cl, r.cd, r.perf_source, r.perf_rule, int(r.is_anomaly)
            ])

def write_versions_csv(rows: List[Tuple[str, str, int, str, str, str]]):
    with (OUT_DIR / "data_versions.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["version_id", "airfoil_id", "version_no", "version_type", "geom_source", "geom_source_url"])
        for row in rows:
            writer.writerow(row)

def write_anomalies_csv(rows: List[AnomalyRecord]):
    with (OUT_DIR / "anomalies.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["anomaly_id", "airfoil_id", "version_id", "alpha_deg", "reynolds_number", "rule", "cl", "cd", "ld"])
        for r in rows:
            writer.writerow([r.anomaly_id, r.airfoil_id, r.version_id, r.alpha_deg, r.reynolds_number, r.rule, r.cl, r.cd, r.ld])

if __name__ == "__main__":
    random.seed(2026)
    build_dataset()
