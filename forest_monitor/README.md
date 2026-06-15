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

系统包含四类计算结果，其中新增三种 MapReduce：

```text
/waether/output/part-r-00000          每日综合统计
/waether/hourly_output/part-r-00000   24 小时环境画像
/waether/risk_output/part-r-00000     每日风险事件统计
/waether/comfort_output/part-r-00000  每日舒适度统计
/waether/topn_output/part-r-00000     高风险日期 Top 10
```

## 一键运行四种 MapReduce 并写入数据库

```powershell
.\sensor\weather\run_analytics.ps1
```

脚本会自动：

1. 编译 Java MapReduce。
2. 覆盖并运行四种分析任务。
3. 从 HDFS 读取五类结果。
4. 写入 SQLite 数据库。

也可以只同步数据库：

```powershell
.\.venv\Scripts\python.exe manage.py sync_mapreduce_results
```

看板 API 查询数据库：

- `/api/dashboard/`：数据库聚合数据
- `/api/records/`：每日计算结果明细

## SQLite 配置

项目默认使用根目录下的 `db.sqlite3`，不需要安装或启动数据库服务。

```powershell
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py sync_mapreduce_results
.\.venv\Scripts\python.exe manage.py runserver
```

前端包含四种 MapReduce 专属展示：24 小时环境画像、每日风险事件与风险率趋势、每日舒适度样本与舒适率趋势、高风险日期 Top 10 排名。

## HDFS 作业控制台

看板顶部可以直接完成以下操作：

- 浏览 `/waether` 下的 HDFS 文件与目录。
- 查看文本或 CSV 文件前 64 KB 内容。
- 上传文件到 `/waether/input`，支持覆盖同名文件。
- 删除 HDFS 文件或目录。
- 上传后自动运行全部 MapReduce，或手动点击运行。
- 计算完成后自动同步 SQLite 并刷新图表。
- 手动点击“同步数据库并刷新”重新加载 HDFS 计算结果。

后台同一时间只运行一个 MapReduce 套件。任务状态保存在 SQLite 的 `hdfs_app_mapreducerun` 表中。
