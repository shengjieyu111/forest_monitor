package main.java;

import org.apache.hadoop.conf.Configuration;
import org.apache.hadoop.fs.Path;
import org.apache.hadoop.io.*;
import org.apache.hadoop.mapreduce.*;
import org.apache.hadoop.mapreduce.lib.input.FileInputFormat;
import org.apache.hadoop.mapreduce.lib.output.FileOutputFormat;

import java.io.IOException;

public class DeviceHealthAnalysis {

    // ================= Mapper =================
    public static class HealthMapper extends Mapper<LongWritable, Text, Text, Text> {
        private final Text deviceKey = new Text();
        private final Text valueOut = new Text();

        @Override
        protected void map(LongWritable key, Text value, Context context)
                throws IOException, InterruptedException {
            String line = value.toString().trim();
            if (line.isEmpty()) return;

            String[] f = line.split(",", -1);
            if (f.length < 7) {
                context.getCounter("PARSE_ERRORS", "BAD_LINES").increment(1);
                return;
            }

            try {
                String deviceId = f[0].trim();
                if (deviceId.isEmpty()) return;

                double cpu = Double.parseDouble(f[1]);
                double mem = Double.parseDouble(f[2]);
                double temp = Double.parseDouble(f[3]);
                double net = Double.parseDouble(f[5]);
                double uptime = Double.parseDouble(f[6]);

                deviceKey.set(deviceId);
                // 输出原始值
                valueOut.set(cpu + "|" + mem + "|" + temp + "|" + net + "|" + uptime);
                context.write(deviceKey, valueOut);

            } catch (Exception e) {
                context.getCounter("PARSE_ERRORS", "PARSE_EXCEPTIONS").increment(1);
            }
        }
    }

    // ================= Combiner =================
    public static class HealthCombiner extends Reducer<Text, Text, Text, Text> {
        private final Text valueOut = new Text();

        @Override
        protected void reduce(Text key, Iterable<Text> values, Context context)
                throws IOException, InterruptedException {
            double cpuSum = 0, memSum = 0, tempSum = 0, netSum = 0, uptimeSum = 0;
            long count = 0;

            for (Text v : values) {
                String[] p = v.toString().split("\\|");
                if (p.length != 5) continue;
                try {
                    cpuSum += Double.parseDouble(p[0]);
                    memSum += Double.parseDouble(p[1]);
                    tempSum += Double.parseDouble(p[2]);
                    netSum += Double.parseDouble(p[3]);
                    uptimeSum += Double.parseDouble(p[4]);
                    count++;
                } catch (NumberFormatException ignored) {}
            }

            if (count > 0) {
                // 输出局部的 sum 和 count
                valueOut.set(cpuSum + "|" + memSum + "|" + tempSum + "|" + netSum + "|" + uptimeSum + "|" + count);
                context.write(key, valueOut);
            }
        }
    }

    // ================= Reducer (全局聚合 + 计算健康度，输出类型: <Text, DoubleWritable>) =================
    public static class HealthReducer extends Reducer<Text, Text, Text, DoubleWritable> {
        @Override
        protected void reduce(Text key, Iterable<Text> values, Context context)
                throws IOException, InterruptedException {
            
            double cpuSum = 0, memSum = 0, tempSum = 0, netSum = 0, uptimeSum = 0;
            long totalCount = 0;

            for (Text v : values) {
                String[] p = v.toString().split("\\|");
                // 兼容 Combiner 输出的6段格式，或者没有 Combiner 时的5段原始格式
                if (p.length == 6) { 
                    cpuSum += Double.parseDouble(p[0]);
                    memSum += Double.parseDouble(p[1]);
                    tempSum += Double.parseDouble(p[2]);
                    netSum += Double.parseDouble(p[3]);
                    uptimeSum += Double.parseDouble(p[4]);
                    totalCount += Long.parseLong(p[5]);
                } else if (p.length == 5) {
                    cpuSum += Double.parseDouble(p[0]);
                    memSum += Double.parseDouble(p[1]);
                    tempSum += Double.parseDouble(p[2]);
                    netSum += Double.parseDouble(p[3]);
                    uptimeSum += Double.parseDouble(p[4]);
                    totalCount++;
                }
            }

            if (totalCount == 0) return;

            // 计算平均值
            double cpu = cpuSum / totalCount;
            double mem = memSum / totalCount;
            double temp = tempSum / totalCount;
            double net = netSum / totalCount;
            double uptime = uptimeSum / totalCount;

            // 计算超出基准线的部分
            double cpuExcess = Math.max(0, cpu - 40.0);
            double memExcess = Math.max(0, mem - 50.0);
            double tempExcess = Math.max(0, temp - 40.0);
            double netExcess = Math.max(0, net - 15.0);
            double uptimeDeficit = Math.max(0, 95.0 - uptime);

            double healthScore = 100.0
                    - 0.35 * cpuExcess
                    - 0.30 * memExcess
                    - 0.20 * tempExcess
                    - 0.15 * netExcess
                    - 0.70 * uptimeDeficit;

            // 边界保护
            healthScore = Math.max(0, Math.min(100, healthScore));
            
            double finalScore = Double.parseDouble(String.format("%.2f", healthScore));
            context.write(key, new DoubleWritable(finalScore));
        }
    }

    // ================= Driver =================
    public static void main(String[] args) throws Exception {
        Configuration conf = new Configuration();
        conf.set("fs.defaultFS", "hdfs://hd0:9000");
        conf.set("mapreduce.framework.name", "yarn");
        conf.set("yarn.resourcemanager.hostname", "hd1");
        conf.set("yarn.resourcemanager.address", "hd1:8032");
        conf.set("yarn.resourcemanager.scheduler.address", "hd1:8030");
        conf.set("yarn.resourcemanager.resource-tracker.address", "hd1:8031");
        conf.set("yarn.resourcemanager.admin.address", "hd1:8033");
        conf.set("mapreduce.app-submission.cross-platform", "true");

        Job job = Job.getInstance(conf, "MR2 DeviceHealthAnalysis");
        job.setJarByClass(DeviceHealthAnalysis.class);

        job.setMapperClass(HealthMapper.class);
        job.setCombinerClass(HealthCombiner.class); // 使用独立的 Combiner
        job.setReducerClass(HealthReducer.class);

        // Map 阶段输出类型
        job.setMapOutputKeyClass(Text.class);
        job.setMapOutputValueClass(Text.class);

        // Reduce 最终输出类型
        job.setOutputKeyClass(Text.class);
        job.setOutputValueClass(DoubleWritable.class);

        FileInputFormat.addInputPath(job, new Path(args[0]));
        FileOutputFormat.setOutputPath(job, new Path(args[1]));

        System.exit(job.waitForCompletion(true) ? 0 : 1);
    }
}
