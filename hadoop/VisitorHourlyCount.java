import java.io.IOException;

import org.apache.hadoop.conf.Configuration;
import org.apache.hadoop.fs.Path;

import org.apache.hadoop.io.IntWritable;
import org.apache.hadoop.io.Text;

import org.apache.hadoop.mapreduce.Job;
import org.apache.hadoop.mapreduce.Mapper;
import org.apache.hadoop.mapreduce.Reducer;

import org.apache.hadoop.mapreduce.lib.input.FileInputFormat;
import org.apache.hadoop.mapreduce.lib.output.FileOutputFormat;


public class VisitorHourlyCount {

    public static class HourlyMapper extends Mapper<Object, Text, Text, IntWritable> {

        private Text outKey = new Text();
        private IntWritable outValue = new IntWritable();

        @Override
        protected void map(Object key, Text value, Context context)
                throws IOException, InterruptedException {

            String line = value.toString();

            
            line = line.replace("\uFEFF", "");

           
            if (line.startsWith("record_id")) {
                return;
            }

            
            String[] fields = line.split(",");

            if (fields.length >= 6) {
                try {
                    String visitTime = fields[1].trim();
                    String visitorCountStr = fields[3].trim();

                   
                    String hour = visitTime.substring(11, 13);

                    int visitorCount = Integer.parseInt(visitorCountStr);

                    outKey.set(hour);
                    outValue.set(visitorCount);

                    context.write(outKey, outValue);
                } catch (Exception e) {
                   
                }
            }
        }
    }


    public static class HourlyReducer extends Reducer<Text, IntWritable, Text, IntWritable> {

        private IntWritable result = new IntWritable();

        @Override
        protected void reduce(Text key, Iterable<IntWritable> values, Context context)
                throws IOException, InterruptedException {

            int sum = 0;

            for (IntWritable value : values) {
                sum += value.get();
            }

            result.set(sum);
            context.write(key, result);
        }
    }


    public static void main(String[] args) throws Exception {

        if (args.length != 2) {
            System.err.println("Usage: VisitorHourlyCount <input path> <output path>");
            System.exit(-1);
        }

        Configuration conf = new Configuration();
        conf.setBoolean("mapreduce.input.fileinputformat.input.dir.recursive", true);
        conf.setBoolean("mapred.input.dir.recursive", true);

        Job job = Job.getInstance(conf, "visitor hourly count");

        job.setJarByClass(VisitorHourlyCount.class);

        job.setMapperClass(HourlyMapper.class);
        job.setReducerClass(HourlyReducer.class);

        job.setOutputKeyClass(Text.class);
        job.setOutputValueClass(IntWritable.class);

        FileInputFormat.addInputPath(job, new Path(args[0]));
        FileOutputFormat.setOutputPath(job, new Path(args[1]));

        System.exit(job.waitForCompletion(true) ? 0 : 1);
    }
}
