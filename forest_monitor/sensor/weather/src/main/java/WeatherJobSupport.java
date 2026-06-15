import exp02.EJob;
import org.apache.hadoop.conf.Configuration;
import org.apache.hadoop.fs.FileSystem;
import org.apache.hadoop.fs.Path;
import org.apache.hadoop.mapreduce.Job;

import java.io.File;

public final class WeatherJobSupport {
    private WeatherJobSupport() {
    }

    public static Configuration configureCluster(Configuration conf) {
        conf.set("fs.defaultFS", "hdfs://hd0:9000");
        conf.set("mapreduce.framework.name", "yarn");
        conf.set("yarn.resourcemanager.hostname", "hd1");
        conf.set("yarn.resourcemanager.address", "hd1:8032");
        conf.set("yarn.resourcemanager.scheduler.address", "hd1:8030");
        conf.set("yarn.resourcemanager.resource-tracker.address", "hd1:8031");
        conf.set("yarn.resourcemanager.admin.address", "hd1:8033");
        conf.set("mapreduce.app-submission.cross-platform", "true");
        conf.set(
                "mapreduce.application.classpath",
                "/usr/local/hadoop/etc/hadoop,"
                        + "/usr/local/hadoop/share/hadoop/mapreduce/*,"
                        + "/usr/local/hadoop/share/hadoop/mapreduce/lib/*,"
                        + "/usr/local/hadoop/share/hadoop/common/*,"
                        + "/usr/local/hadoop/share/hadoop/common/lib/*,"
                        + "/usr/local/hadoop/share/hadoop/hdfs/*,"
                        + "/usr/local/hadoop/share/hadoop/hdfs/lib/*,"
                        + "/usr/local/hadoop/share/hadoop/yarn/*,"
                        + "/usr/local/hadoop/share/hadoop/yarn/lib/*"
        );
        return conf;
    }

    public static void attachJobJar(Job job, Class<?> entryClass) throws Exception {
        File classesDir = new File(
                entryClass.getProtectionDomain().getCodeSource().getLocation().toURI()
        );
        System.out.println("编译目录：" + classesDir.getAbsolutePath());

        File jarFile = EJob.createTempJar(classesDir.getAbsolutePath());
        if (jarFile == null || !jarFile.exists()) {
            throw new IllegalStateException(
                    "EJob 自动打包失败，编译目录：" + classesDir.getAbsolutePath()
            );
        }

        System.out.println("临时 Jar：" + jarFile.getAbsolutePath());
        job.setJar(jarFile.getAbsolutePath());

        ClassLoader classLoader = EJob.getClassLoader();
        if (classLoader != null) {
            Thread.currentThread().setContextClassLoader(classLoader);
        }
    }

    public static int waitForCompletion(Job job) throws Exception {
        if (job.waitForCompletion(true)) {
            return 0;
        }

        String failureInfo = job.getStatus().getFailureInfo();
        System.err.println("MapReduce 作业执行失败。");
        if (failureInfo != null && !failureInfo.trim().isEmpty()) {
            System.err.println("失败原因：" + failureInfo);
        }
        return 1;
    }

    public static void prepareOutput(Configuration conf, String output, boolean overwrite)
            throws Exception {
        Path outputPath = new Path(output);
        FileSystem fileSystem = outputPath.getFileSystem(conf);
        if (overwrite && fileSystem.exists(outputPath)) {
            System.out.println("删除已有输出目录：" + output);
            if (!fileSystem.delete(outputPath, true)) {
                throw new IllegalStateException("无法删除已有输出目录：" + output);
            }
        }
    }
}
