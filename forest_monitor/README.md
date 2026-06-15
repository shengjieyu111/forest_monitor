# 森林环境监测可视化平台

## 启动

在当前目录执行：

```powershell
.\.venv\Scripts\python.exe manage.py runserver
```

浏览器访问：

```text
http://127.0.0.1:8000/
```

## 数据源

当前看板通过 WebHDFS 直接读取 MapReduce 输出：

```text
/waether/output/part-r-00000
```

配置位于 `forest_monitor/settings.py`：

```python
HDFS_WEB_HOST = 'hd0'
HDFS_WEB_PORT = 50070
HDFS_OUTPUT_PATH = '/waether/output'
```

后端接口：

- `/api/dashboard/`：看板聚合数据
- `/api/records/`：监测明细、分页与风险筛选

点击页面中的“更新看板”会重新读取 HDFS。若 HDFS 临时不可用，页面会使用最近一次成功读取的缓存，并在顶部标注“HDFS 缓存结果”。
