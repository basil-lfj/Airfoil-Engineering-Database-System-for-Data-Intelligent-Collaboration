"""验证迁移后的索引和物化视图"""
import os, sys
sys.path.insert(0, r'c:\Users\ASUS\Desktop\Databaselab\Bigwork\AEDS\Webfront')
os.environ['DJANGO_SETTINGS_MODULE'] = 'config.settings'
import django; django.setup()
from django.db import connection

c = connection.cursor()
c.execute("SELECT indexname FROM pg_indexes WHERE tablename IN ('airfoil','airfoil_version','performance_record') AND indexname LIKE 'idx_%' ORDER BY indexname")
rows = c.fetchall()
print('Indexes created:')
for r in rows:
    print(f'  [OK] {r[0]}')

c.execute("SELECT * FROM mv_airfoil_stats")
r = c.fetchone()
print(f'\nMaterialized view mv_airfoil_stats: {r}')
print(f'\nTotal: {len(rows)} indexes + 1 materialized view')
