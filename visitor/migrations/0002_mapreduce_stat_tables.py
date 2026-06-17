from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("visitor", "0001_initial"),
    ]

    operations = [
        migrations.RemoveIndex(
            model_name="visitorrecord",
            name="visitor_vis_visit_t_891bfb_idx",
        ),
        migrations.RemoveIndex(
            model_name="visitorrecord",
            name="visitor_vis_entranc_dbf278_idx",
        ),
        migrations.RenameField(
            model_name="visitorrecord",
            old_name="entrance",
            new_name="gate",
        ),
        migrations.RemoveField(
            model_name="visitorrecord",
            name="source",
        ),
        migrations.RemoveField(
            model_name="visitorrecord",
            name="note",
        ),
        migrations.AddField(
            model_name="visitorrecord",
            name="ticket_type",
            field=models.CharField(
                choices=[
                    ("成人票", "成人票"),
                    ("学生票", "学生票"),
                    ("团体票", "团体票"),
                    ("老人票", "老人票"),
                ],
                default="成人票",
                max_length=20,
                verbose_name="票种",
            ),
            preserve_default=False,
        ),
        migrations.AlterField(
            model_name="visitorrecord",
            name="gate",
            field=models.CharField(
                choices=[
                    ("东门", "东门"),
                    ("西门", "西门"),
                    ("南门", "南门"),
                    ("北门", "北门"),
                ],
                max_length=20,
                verbose_name="入口",
            ),
        ),
        migrations.AlterField(
            model_name="visitorrecord",
            name="visitor_count",
            field=models.IntegerField(verbose_name="游客数量"),
        ),
        migrations.AlterModelOptions(
            name="visitorrecord",
            options={
                "ordering": ["-visit_time", "-id"],
                "verbose_name": "游客原始记录",
                "verbose_name_plural": "游客原始记录",
            },
        ),
        migrations.AlterModelTable(
            name="visitorrecord",
            table="visitor_record",
        ),
        migrations.AddIndex(
            model_name="visitorrecord",
            index=models.Index(fields=["visit_time"], name="visitor_rec_visit_t_033860_idx"),
        ),
        migrations.AddIndex(
            model_name="visitorrecord",
            index=models.Index(
                fields=["gate", "visit_time"], name="visitor_rec_gate_73efc5_idx"
            ),
        ),
        migrations.CreateModel(
            name="VisitorDailyStat",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("stat_date", models.DateField(verbose_name="统计日期")),
                ("total_count", models.IntegerField(verbose_name="当日游客总量")),
                (
                    "created_at",
                    models.DateTimeField(auto_now_add=True, verbose_name="创建时间"),
                ),
            ],
            options={
                "verbose_name": "每日游客统计",
                "verbose_name_plural": "每日游客统计",
                "db_table": "visitor_daily_stat",
                "ordering": ["stat_date"],
                "indexes": [
                    models.Index(
                        fields=["stat_date"],
                        name="visitor_dai_stat_da_5c39c2_idx",
                    ),
                ],
            },
        ),
        migrations.CreateModel(
            name="VisitorHourlyStat",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("hour", models.IntegerField(verbose_name="小时")),
                (
                    "total_count",
                    models.IntegerField(verbose_name="该小时累计游客数量"),
                ),
                (
                    "created_at",
                    models.DateTimeField(auto_now_add=True, verbose_name="创建时间"),
                ),
            ],
            options={
                "verbose_name": "小时游客统计",
                "verbose_name_plural": "小时游客统计",
                "db_table": "visitor_hourly_stat",
                "ordering": ["hour"],
                "indexes": [
                    models.Index(fields=["hour"], name="visitor_hou_hour_c9e4d7_idx"),
                ],
            },
        ),
        migrations.CreateModel(
            name="VisitorGateStat",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("gate", models.CharField(max_length=20, verbose_name="入口名称")),
                (
                    "total_count",
                    models.IntegerField(verbose_name="该入口累计游客数量"),
                ),
                (
                    "created_at",
                    models.DateTimeField(auto_now_add=True, verbose_name="创建时间"),
                ),
            ],
            options={
                "verbose_name": "入口游客统计",
                "verbose_name_plural": "入口游客统计",
                "db_table": "visitor_gate_stat",
                "ordering": ["-total_count"],
                "indexes": [
                    models.Index(fields=["gate"], name="visitor_gat_gate_53a612_idx"),
                ],
            },
        ),
    ]
