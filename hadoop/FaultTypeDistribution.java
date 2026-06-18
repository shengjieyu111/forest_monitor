package main.java;

import org.apache.hadoop.conf.Configuration;
import org.apache.hadoop.fs.Path;
import org.apache.hadoop.io.*;
import org.apache.hadoop.mapreduce.*;
import org.apache.hadoop.mapreduce.lib.input.FileInputFormat;
import org.apache.hadoop.mapreduce.lib.input.MultipleInputs;
import org.apache.hadoop.mapreduce.lib.input.TextInputFormat;
import org.apache.hadoop.mapreduce.lib.output.FileOutputFormat;
import org.apache.hadoop.mapreduce.lib.output.TextOutputFormat;

import java.io.IOException;

public class FaultTypeDistribution {

    // ================= 第一阶段：Join Mapper & Reducer =================
    
    // Mapper 1: 处理设备信息
    public static class InfoMapper extends Mapper<LongWritable, Text, Text, Text> {
        private final Text outKey = new Text();
        private final Text outValue = new Text();

        @Override
        protected void map(LongWritable key, Text value, Context context)
                throws IOException, InterruptedException {
            String line = value.toString().trim();
            if (line.isEmpty()) return;
            String[] f = line.split(",");
            if (f.length < 3) return;

            String deviceId = f[0].trim();
            String deviceType = f[2].trim();

            outKey.set(deviceId);
            outValue.set("INFO|" + deviceType);
            context.write(outKey, outValue);
        }
    }

    // Mapper 2: 处理故障日志
    public static class FaultMapper extends Mapper<LongWritable, Text, Text, Text> {
        private final Text outKey = new Text();
        private final Text outValue = new Text();

        @Override
        protected void map(LongWritable key, Text value, Context context)
                throws IOException, InterruptedException {
            String line = value.toString().trim();
            if (line.isEmpty()) return;
            String[] f = line.split(",");
            if (f.length < 3) return;

            String deviceId = f[1].trim();
            String faultType = f[2].trim();

            outKey.set(deviceId);
            outValue.set("FAULT|" + faultType);
            context.write(outKey, outValue);
        }
    }

    // Reducer 1: 关联设备和故障，输出扁平化的 "故障_设备"
    public static class JoinReducer extends Reducer<Text, Text, Text, IntWritable> {
        private final IntWritable one = new IntWritable(1);

        @Override
        protected void reduce(Text key, Iterable<Text> values, Context context)
                throws IOException, InterruptedException {
            
            String deviceType = "UNKNOWN";
            // 收集该设备的所有故障类型
            java.util.List<String> faults = new java.util.ArrayList<>();

            for (Text val : values) {
                String strVal = val.toString();
                if (strVal.startsWith("INFO|")) {
                    deviceType = strVal.split("\\|", 2)[1];
                } else if (strVal.startsWith("FAULT|")) {
                    faults.add(strVal.split("\\|", 2)[1]);
                }
            }

            // 如果关联成功，输出扁平数据：Key="故障_设备", Value=1
            if (!deviceType.equals("UNKNOWN")) {
                for (String fault : faults) {
                    String finalKey = fault + "_" + deviceType;
                    context.write(new Text(finalKey), one);
                }
            }
        }
    }

    // ================= 第二阶段：全局聚合 Mapper & Reducer =================

    // Mapper 3: 直接透传第一阶段的结果
    public static class AggMapper extends Mapper<LongWritable, Text, Text, IntWritable> {
        private final Text outKey = new Text();
        private final IntWritable outVal = new IntWritable();

        @Override
        protected void map(LongWritable key, Text value, Context context)
                throws IOException, InterruptedException {
            String line = value.toString().trim();
            if (line.isEmpty()) return;
            
            String[] parts = line.split("\t");
            if (parts.length == 2) {
                outKey.set(parts[0]); // 故障_设备
                outVal.set(Integer.parseInt(parts[1])); // 1
                context.write(outKey, outVal);
            }
        }
    }

    // Reducer 2: 全局累加相同的 "故障_设备"
    public static class AggReducer extends Reducer<Text, IntWritable, Text, IntWritable> {
        private final IntWritable result = new IntWritable();

        @Override
        protected void reduce(Text key, Iterable<IntWritable> values, Context context)
                throws IOException, InterruptedException {
            int sum = 0;
            for (IntWritable val : values) {
                sum += val.get();
            }
            result.set(sum);
            context.write(key, result);
        }
    }

    // ================= Driver =================
    public static void main(String[] args) throws Exception {
        Configuration conf = new Configuration();
        conf.set("fs.defaultFS", "hdfs://node11:8020");
        conf.set("mapreduce.framework.name", "yarn");
        conf.set("yarn.resourcemanager.address", "node12:8032");

        Path tempJoinOutput = new Path(args[2] + "_temp_join");
        Path finalOutput = new Path(args[2]);

        // --- 第一阶段 Job：Join ---
        Job joinJob = Job.getInstance(conf, "MR1_Step1_Join");
        joinJob.setJarByClass(FaultTypeDistribution.class);
        
        MultipleInputs.addInputPath(joinJob, new Path(args[0]), TextInputFormat.class, FaultMapper.class);
        MultipleInputs.addInputPath(joinJob, new Path(args[1]), TextInputFormat.class, InfoMapper.class);

        
        joinJob.setReducerClass(JoinReducer.class);
        joinJob.setMapOutputKeyClass(Text.class);
        joinJob.setMapOutputValueClass(Text.class);
        joinJob.setOutputKeyClass(Text.class);
        joinJob.setOutputValueClass(IntWritable.class);
        joinJob.setOutputFormatClass(TextOutputFormat.class);
        FileOutputFormat.setOutputPath(joinJob, tempJoinOutput);

        // --- 第二阶段 Job：Aggregation ---
        Job aggJob = Job.getInstance(conf, "MR1_Step2_Aggregation");
        aggJob.setJarByClass(FaultTypeDistribution.class);
        
        aggJob.setMapperClass(AggMapper.class);
        aggJob.setReducerClass(AggReducer.class);
        
        aggJob.setMapOutputKeyClass(Text.class);
        aggJob.setMapOutputValueClass(IntWritable.class);
        aggJob.setOutputKeyClass(Text.class);
        aggJob.setOutputValueClass(IntWritable.class);
        
        // 输入是第一阶段 Join 的输出
        FileInputFormat.addInputPath(aggJob, tempJoinOutput);
        FileOutputFormat.setOutputPath(aggJob, finalOutput);

        // 串行执行两个 Job
        if (joinJob.waitForCompletion(true)) {
            System.exit(aggJob.waitForCompletion(true) ? 0 : 1);
        } else {
            System.exit(1);
        }
    }
}