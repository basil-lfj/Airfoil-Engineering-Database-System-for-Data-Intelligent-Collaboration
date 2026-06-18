"""
执行 v1.0_indexes.sql 数据库迁移脚本
用法: cd Webfront && python ../scripts/migration/run_migration.py
"""
import os
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent / 'Webfront'
sys.path.insert(0, str(BASE_DIR))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

import django
django.setup()

from django.db import connection
import psycopg2


def run_migration():
    sql_path = Path(__file__).resolve().parent / 'v1.0_indexes.sql'
    raw = sql_path.read_text(encoding='utf-8')

    # 去掉注释行，按分号拆分语句
    clean = '\n'.join(
        line for line in raw.split('\n')
        if not line.strip().startswith('--') and line.strip()
    )
    statements = [s.strip() for s in clean.split(';') if s.strip()]

    # --- 第1组：普通 DDL（在事务中执行）---
    ddl = [s for s in statements if 'CONCURRENTLY' not in s.upper()]
    if ddl:
        with connection.cursor() as cursor:
            for stmt in ddl:
                try:
                    cursor.execute(stmt)
                    print(f"  [OK] {stmt[:60].replace(chr(10),' ')}...")
                except Exception as e:
                    print(f"  [SKIP] {stmt[:60].replace(chr(10),' ')}... {e}")

    # --- 第2组：CONCURRENTLY 索引（需 autocommit 模式）---
    concurrently = [s for s in statements if 'CONCURRENTLY' in s.upper()]
    if concurrently:
        conn2 = psycopg2.connect(
            host='localhost', port=5432,
            user='postgres', password='postgres',
            dbname='airfoil_db'
        )
        conn2.autocommit = True
        try:
            with conn2.cursor() as c:
                for stmt in concurrently:
                    try:
                        c.execute(stmt)
                        print(f"  [OK] {stmt[:60].replace(chr(10),' ')}...")
                    except Exception as e:
                        print(f"  [SKIP] {stmt[:60].replace(chr(10),' ')}... {e}")
        finally:
            conn2.close()

    print("\nDone. Migration completed.")


if __name__ == '__main__':
    run_migration()
