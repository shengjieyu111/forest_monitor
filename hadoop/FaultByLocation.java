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
import java.util.ArrayList;
import java.util.List;

public class FaultByLocation {

    // ================= 第一阶段：Join Mapper & Reducer =================

    public static class FaultMapper extends Mapper<LongWritable, Text, Text, Text> {
        private final Text outKey = new Text();
        private final Text outValue = new Text();

        @Override
        protected void map(LongWritable key, Text value, Context context)
                throws IOException, InterruptedException {
            String line = value.toString().trim();
            if (line.isEmpty() || line.startsWith("||")) return;
            String[] f = line.split(",");
            if (f.length < 6) return;

            try {
                String deviceId = f[1].trim();     
                String faultType = f[2].trim();     
                String timestampStr = f[5].trim(); 
                String month = timestampStr.length() >= 7 ? timestampStr.substring(0, 7) : "UNKNOWN";

                outKey.set(deviceId);
                outValue.set("FAULT|" + month + "|" + faultType);
                context.write(outKey, outValue);
            } catch (Exception e) {
                // 忽略解析错误
            }
        }
    }

    public static class DeviceMapper extends Mapper<LongWritable, Text, Text, Text> {
        private final Text outKey = new Text();
        private final Text outValue = new Text();

        @Override
        protected void map(LongWritable key, Text value, Context context)
                throws IOException, InterruptedException {
            String line = value.toString().trim();
            if (line.isEmpty() || line.startsWith("||")) return;
            String[] f = line.split(",");
            if (f.length < 7) return;

            try {
                String deviceId = f[0].trim();     
                String region = f[6].trim();      

                outKey.set(deviceId);
                outValue.set("DEVICE|" + region);
                context.write(outKey, outValue);
            } catch (Exception e) {
                // 忽略解析错误
            }
        }
    }

    // Reducer 1: 关联设备和故障，输出扁平化的 "区域_月份|故障"
    public static class JoinReducer extends Reducer<Text, Text, Text, IntWritable> {
        private final IntWritable one = new IntWritable(1);

        @Override
        protected void reduce(Text key, Iterable<Text> values, Context context)
                throws IOException, InterruptedException {
            
            String region = null;
            List<String> faultInfos = new ArrayList<>();

            for (Text val : values) {
                String v = val.toString();
                if (v.startsWith("DEVICE|")) {
                    region = v.split("\\|", 2)[1];
                } else if (v.startsWith("FAULT|")) {
                    faultInfos.add(v.split("\\|", 2)[1]); // 月份|故障类型
                }
            }

            if (region != null && !faultInfos.isEmpty()) {
                for (String info : faultInfos) {
                    // 输出 Key: 区域_月份|故障类型, Value: 1
                    String finalKey = region + "_" + info;
                    context.write(new Text(finalKey), one);
                }
            }
        }
    }

    // ================= 第二阶段：全局聚合 Mapper & Reducer =================

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
                outKey.set(parts[0]); 
                outVal.set(Integer.parseInt(parts[1])); 
                context.write(outKey, outVal);
            }
        }
    }

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
        Job joinJob = Job.getInstance(conf, "MR3_Step1_Join");
        joinJob.setJarByClass(FaultByLocation.class);
        
        MultipleInputs.addInputPath(joinJob, new Path(args[0]), TextInputFormat.class, FaultMapper.class);
        MultipleInputs.addInputPath(joinJob, new Path(args[1]), TextInputFormat.class, DeviceMapper.class);
        
        joinJob.setReducerClass(JoinReducer.class);
        joinJob.setMapOutputKeyClass(Text.class);
        joinJob.setMapOutputValueClass(Text.class);
        joinJob.setOutputKeyClass(Text.class);
        joinJob.setOutputValueClass(IntWritable.class);
        joinJob.setOutputFormatClass(TextOutputFormat.class);
        FileOutputFormat.setOutputPath(joinJob, tempJoinOutput);

        // --- 第二阶段 Job：Aggregation ---
        Job aggJob = Job.getInstance(conf, "MR3_Step2_Aggregation");
        aggJob.setJarByClass(FaultByLocation.class);
        
        aggJob.setMapperClass(AggMapper.class);
        aggJob.setReducerClass(AggReducer.class);
        
        aggJob.setMapOutputKeyClass(Text.class);
        aggJob.setMapOutputValueClass(IntWritable.class);
        aggJob.setOutputKeyClass(Text.class);
        aggJob.setOutputValueClass(IntWritable.class);
        
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