from django.core.management.base import BaseCommand, CommandError

from mapreduce_app.hdfs_sync import RESULT_PATHS, sync_all_results, sync_result


class Command(BaseCommand):
    help = '从 HDFS 读取 MapReduce 结果并写入数据库'

    def add_arguments(self, parser):
        parser.add_argument(
            '--job',
            choices=[*RESULT_PATHS, 'all'],
            default='all',
            help='选择要同步的作业结果',
        )

    def handle(self, *args, **options):
        job = options['job']
        try:
            results = sync_all_results() if job == 'all' else {job: sync_result(job)}
        except Exception as error:
            raise CommandError(f'同步失败：{error}') from error

        for job_type, count in results.items():
            self.stdout.write(self.style.SUCCESS(
                f'{job_type}: 已同步 {count} 条结果'
            ))
