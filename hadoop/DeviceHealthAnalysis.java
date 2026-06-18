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
            if (line.isEmpty() || line.startsWith("||")) return;

            String[] f = line.split(",");
            
            if (f.length < 9) {
                context.getCounter("PARSE_ERRORS", "BAD_LINES").increment(1);
                return;
            }

            try {
                String deviceId = f[1].trim();
                if (deviceId.isEmpty()) return;

                double cpu = Double.parseDouble(f[2].trim());
                double mem = Double.parseDouble(f[3].trim());
                double temp = Double.parseDouble(f[4].trim());
                double net = Double.parseDouble(f[6].trim());
                double uptime = Double.parseDouble(f[7].trim());

                deviceKey.set(deviceId);
                valueOut.set(cpu + "|" + mem + "|" + temp + "|" + net + "|" + uptime);
                context.write(deviceKey, valueOut);

            } catch (NumberFormatException e) {
                // 数据格式异常计数
                context.getCounter("PARSE_ERRORS", "PARSE_EXCEPTIONS").increment(1);
            }
        }
    }

    // ================= Combiner (局部聚合) =================
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
                valueOut.set(cpuSum + "|" + memSum + "|" + tempSum + "|" + netSum + "|" + uptimeSum + "|" + count);
                context.write(key, valueOut);
            }
        }
    }

    // ================= Reducer (全局聚合 + 计算健康度) =================
    public static class HealthReducer extends Reducer<Text, Text, Text, DoubleWritable> {
        @Override
        protected void reduce(Text key, Iterable<Text> values, Context context)
                throws IOException, InterruptedException {
            
            double cpuSum = 0, memSum = 0, tempSum = 0, netSum = 0, uptimeSum = 0;
            long totalCount = 0;

            for (Text v : values) {
                String[] p = v.toString().split("\\|");
                // 兼容 Combiner 输出的 6 段格式 (sum|sum|sum|sum|sum|count)
                if (p.length == 6) { 
                    cpuSum += Double.parseDouble(p[0]);
                    memSum += Double.parseDouble(p[1]);
                    tempSum += Double.parseDouble(p[2]);
                    netSum += Double.parseDouble(p[3]);
                    uptimeSum += Double.parseDouble(p[4]);
                    totalCount += Long.parseLong(p[5]);
                } 
                else if (p.length == 5) {
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

            // 大部分设备落在 60-80 分区间
            double cpuPenalty = Math.max(0, cpu - 50.0) * 0.30;
            double memPenalty = Math.max(0, mem - 60.0) * 0.25;
            double tempPenalty = Math.max(0, temp - 45.0) * 0.40;
            double netPenalty = Math.max(0, net - 20.0) * 0.20;
            double uptimePenalty = Math.max(0, 80.0 - uptime) * 0.15;

            double healthScore = 100.0 - (cpuPenalty + memPenalty + tempPenalty + netPenalty + uptimePenalty);

            // 边界保护
            healthScore = Math.max(0, Math.min(100, healthScore));
            
            double finalScore = Double.parseDouble(String.format("%.2f", healthScore));
            context.write(key, new DoubleWritable(finalScore));
        }
    }

    // ================= Driver =================
    public static void main(String[] args) throws Exception {
        Configuration conf = new Configuration();
        conf.set("fs.defaultFS", "hdfs://node11:8020");
        conf.set("mapreduce.framework.name", "yarn");
        conf.set("yarn.resourcemanager.address", "node12:8032");

        Job job = Job.getInstance(conf, "MR2 DeviceHealthAnalysis");
        job.setJarByClass(DeviceHealthAnalysis.class);

        job.setMapperClass(HealthMapper.class);
        job.setCombinerClass(HealthCombiner.class);
        job.setReducerClass(HealthReducer.class);

        job.setMapOutputKeyClass(Text.class);
        job.setMapOutputValueClass(Text.class);

        job.setOutputKeyClass(Text.class);
        job.setOutputValueClass(DoubleWritable.class);

        FileInputFormat.addInputPath(job, new Path(args[0]));
        FileOutputFormat.setOutputPath(job, new Path(args[1]));

        System.exit(job.waitForCompletion(true) ? 0 : 1);
    }
}