package main.java;

import org.apache.hadoop.conf.Configuration;
import org.apache.hadoop.fs.Path;
import org.apache.hadoop.io.*;
import org.apache.hadoop.mapreduce.*;
import org.apache.hadoop.mapreduce.lib.input.FileInputFormat;
import org.apache.hadoop.mapreduce.lib.output.FileOutputFormat;

import java.io.IOException;

public class FaultTypeDistribution {

    public static class MapperClass extends Mapper<LongWritable, Text, Text, IntWritable> {

        private final Text outKey = new Text();
        private final IntWritable one = new IntWritable(1);

        @Override
        protected void map(LongWritable key, Text value, Context context)
                throws IOException, InterruptedException {

            String line = value.toString().trim();
            if (line.isEmpty() || line.startsWith("id")) return;

            String[] f = line.split(",");
            if (f.length < 6) return;

            String faultType = f[2].trim();
            if (!faultType.isEmpty()) {
                outKey.set(faultType);
                context.write(outKey, one);
            }
        }
    }

    public static class ReducerClass extends Reducer<Text, IntWritable, Text, IntWritable> {

        private final IntWritable result = new IntWritable();

        @Override
        protected void reduce(Text key, Iterable<IntWritable> values, Context context)
                throws IOException, InterruptedException {

            int sum = 0;
            for (IntWritable v : values) {
                sum += v.get();
            }

            result.set(sum);
            context.write(key, result);
        }
    }

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

        Job job = Job.getInstance(conf, "MR1 FaultTypeDistribution");

        job.setJarByClass(FaultTypeDistribution.class);
        job.setMapperClass(MapperClass.class);
        job.setReducerClass(ReducerClass.class);

        job.setOutputKeyClass(Text.class);
        job.setOutputValueClass(IntWritable.class);

        FileInputFormat.addInputPath(job, new Path(args[0]));
        FileOutputFormat.setOutputPath(job, new Path(args[1]));

        System.exit(job.waitForCompletion(true) ? 0 : 1);
    }
}
