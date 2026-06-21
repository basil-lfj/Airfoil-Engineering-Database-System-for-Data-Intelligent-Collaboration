"""
Service 层 Facade：向后兼容，委托到 DAO 包
"""
from .dao import (
    get_statistics, get_top_performers,
    get_recent_airfoils, get_all_airfoils, get_airfoil_detail,
    search_airfoils_by_name, search_airfoils_by_condition,
    compare_airfoils, get_suggested_airfoils,
    get_anomaly_stats, get_anomalies, get_anomaly_count,
    # 异常检测引擎
    scan_all_performance, check_single_record,
    get_anomaly_detail_stats, get_anomaly_annotations,
    create_airfoil, update_airfoil, delete_airfoil, get_all_data_sources,
    # 版本管理
    create_version, update_version_status, delete_version,
    # 坐标点管理
    create_coordinate_points, update_coordinate_point, delete_coordinate_points,
    # 性能数据管理
    create_performance_record, update_performance_record, delete_performance_record,
    get_performance_records,
)

__all__ = [
    'get_statistics', 'get_top_performers',
    'get_recent_airfoils', 'get_all_airfoils', 'get_airfoil_detail',
    'search_airfoils_by_name', 'search_airfoils_by_condition',
    'compare_airfoils', 'get_suggested_airfoils',
    'get_anomaly_stats', 'get_anomalies', 'get_anomaly_count',
    # 异常检测引擎
    'scan_all_performance', 'check_single_record',
    'get_anomaly_detail_stats', 'get_anomaly_annotations',
    'create_airfoil', 'update_airfoil', 'delete_airfoil', 'get_all_data_sources',
    # 版本
    'create_version', 'update_version_status', 'delete_version',
    # 坐标
    'create_coordinate_points', 'update_coordinate_point', 'delete_coordinate_points',
    # 性能
    'create_performance_record', 'update_performance_record', 'delete_performance_record',
    'get_performance_records',
]