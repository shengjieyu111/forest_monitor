import org.apache.hadoop.conf.Configuration;
import org.apache.hadoop.conf.Configured;
import org.apache.hadoop.fs.Path;
import org.apache.hadoop.io.Text;
import org.apache.hadoop.mapreduce.Job;
import org.apache.hadoop.mapreduce.Mapper;
import org.apache.hadoop.mapreduce.Reducer;
import org.apache.hadoop.mapreduce.lib.input.FileInputFormat;
import org.apache.hadoop.mapreduce.lib.output.FileOutputFormat;
import org.apache.hadoop.util.Tool;
import org.apache.hadoop.util.ToolRunner;

import java.io.IOException;

public class WeatherHourlyProfileMR extends Configured implements Tool {
    public static class HourlyMapper extends Mapper<Object, Text, Text, Text> {
        private final Text outKey = new Text();
        private final Text outValue = new Text();

        @Override
        protected void map(Object key, Text value, Context context)
                throws IOException, InterruptedException {
            String line = value.toString().trim();
            if (line.isEmpty() || line.startsWith("city,date,hour")) {
                return;
            }

            String[] fields = line.split(",");
            if (fields.length != 7 || fields[2].length() < 2) {
                return;
            }

            outKey.set(fields[2].substring(0, 2));
            outValue.set(fields[3] + "," + fields[4] + "," + fields[5] + "," + fields[6]);
            context.write(outKey, outValue);
        }
    }

    public static class HourlyReducer extends Reducer<Text, Text, Text, Text> {
        @Override
        protected void reduce(Text key, Iterable<Text> values, Context context)
                throws IOException, InterruptedException {
            int count = 0;
            double temperature = 0;
            double humidity = 0;
            double pm25 = 0;
            double illumination = 0;

            for (Text value : values) {
                String[] fields = value.toString().split(",");
                if (fields.length != 4) {
                    continue;
                }
                count++;
                temperature += Double.parseDouble(fields[0]);
                humidity += Double.parseDouble(fields[1]);
                pm25 += Double.parseDouble(fields[2]);
                illumination += Double.parseDouble(fields[3]);
            }

            if (count == 0) {
                return;
            }

            context.write(key, new Text(String.format(
                    "sample_count=%d,temp_avg=%.2f,humidity_avg=%.2f,pm25_avg=%.2f,illumination_avg=%.2f",
                    count,
                    temperature / count,
                    humidity / count,
                    pm25 / count,
                    illumination / count
            )));
        }
    }

    @Override
    public int run(String[] args) throws Exception {
        String input = args.length >= 1 ? args[0] : "/waether/input";
        String output = args.length >= 2 ? args[1] : "/waether/hourly_output";
        boolean overwrite = args.length >= 3 && "--overwrite".equals(args[2]);

        Configuration conf = WeatherJobSupport.configureCluster(getConf());
        WeatherJobSupport.prepareOutput(conf, output, overwrite);
        Job job = Job.getInstance(conf, "weather hourly profile");
        WeatherJobSupport.attachJobJar(job, WeatherHourlyProfileMR.class);
        job.setMapperClass(HourlyMapper.class);
        job.setReducerClass(HourlyReducer.class);
        job.setMapOutputKeyClass(Text.class);
        job.setMapOutputValueClass(Text.class);
        job.setOutputKeyClass(Text.class);
        job.setOutputValueClass(Text.class);
        FileInputFormat.addInputPath(job, new Path(input));
        FileOutputFormat.setOutputPath(job, new Path(output));
        return WeatherJobSupport.waitForCompletion(job);
    }

    public static void main(String[] args) throws Exception {
        System.setProperty("HADOOP_USER_NAME", "root");
        System.exit(ToolRunner.run(new Configuration(), new WeatherHourlyProfileMR(), args));
    }
}
