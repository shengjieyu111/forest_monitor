package main.java;

import org.apache.hadoop.conf.Configuration;
import org.apache.hadoop.fs.Path;
import org.apache.hadoop.io.*;
import org.apache.hadoop.mapreduce.*;
import org.apache.hadoop.mapreduce.lib.input.FileInputFormat;
import org.apache.hadoop.mapreduce.lib.output.FileOutputFormat;

import java.io.IOException;

public class DeviceWorkAnalysis {

    public static class MapperClass extends Mapper<LongWritable, Text, Text, Text> {

        private final Text keyOut = new Text();
        private final Text valueOut = new Text();

        @Override
        protected void map(LongWritable key, Text value, Context context)
                throws IOException, InterruptedException {

            String line = value.toString().trim();
            if (line.isEmpty() || line.startsWith("device_id")) return;

            String[] f = line.split(",");
            if (f.length < 9) return; 

            try {
                String deviceId = f[1]; 

                double cpu = Double.parseDouble(f[2]);
                double memory = Double.parseDouble(f[3]);
                double temp = Double.parseDouble(f[4]);
                double power = Double.parseDouble(f[5]);
                double net = Double.parseDouble(f[6]);

                keyOut.set(deviceId);

                valueOut.set(cpu + "|" + memory + "|" + temp + "|" + power + "|" + net + "|1");

                context.write(keyOut, valueOut);

            } catch (Exception e) {
                System.err.println("解析失败的行: " + line);
                e.printStackTrace();
            }
        }
    }

    public static class ReducerClass extends Reducer<Text, Text, Text, Text> {

        private final Text outValue = new Text();

        @Override
        protected void reduce(Text key, Iterable<Text> values, Context context)
                throws IOException, InterruptedException {

            double cpuSum = 0, memSum = 0, tempSum = 0, powerSum = 0, netSum = 0;
            long count = 0;

            for (Text v : values) {
                String[] p = v.toString().split("\\|");

                if (p.length < 5) continue; 

                cpuSum += Double.parseDouble(p[0]);
                memSum += Double.parseDouble(p[1]);
                tempSum += Double.parseDouble(p[2]);
                powerSum += Double.parseDouble(p[3]);
                netSum += Double.parseDouble(p[4]);
                count += 1;
            }

            if (count == 0) return;

            // 直接输出 5 个平均值
            // 输出格式: avg_cpu \t avg_memory \t avg_temp \t avg_power \t avg_net
            outValue.set(
                    String.format("%.2f\t%.2f\t%.2f\t%.2f\t%.2f",
                            cpuSum / count,
                            memSum / count,
                            tempSum / count,
                            powerSum / count,
                            netSum / count
                    )
            );

            context.write(key, outValue);
        }
    }

    public static void main(String[] args) throws Exception {

        Configuration conf = new Configuration();
        conf.set("fs.defaultFS", "hdfs://node11:8020");
        conf.set("mapreduce.framework.name", "yarn");
        conf.set("yarn.resourcemanager.address", "node12:8032");

        Job job = Job.getInstance(conf, "MR4 DeviceAnalysis");

        job.setJarByClass(DeviceWorkAnalysis.class);

        job.setMapperClass(MapperClass.class);
        job.setReducerClass(ReducerClass.class);

        job.setOutputKeyClass(Text.class);
        job.setOutputValueClass(Text.class);

        FileInputFormat.addInputPath(job, new Path(args[0]));
        FileOutputFormat.setOutputPath(job, new Path(args[1]));

        System.exit(job.waitForCompletion(true) ? 0 : 1);
    }
}