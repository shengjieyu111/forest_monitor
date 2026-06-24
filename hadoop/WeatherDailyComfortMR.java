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

public class WeatherDailyComfortMR extends Configured implements Tool {
    public static class ComfortMapper extends Mapper<Object, Text, Text, Text> {
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
            if (fields.length != 7) {
                return;
            }

            double temp = Double.parseDouble(fields[3]);
            double humidity = Double.parseDouble(fields[4]);
            double pm25 = Double.parseDouble(fields[5]);
            double comfortIndex = temp - 0.55 * (1 - humidity / 100.0) * (temp - 14.5);

            int comfortable = comfortIndex >= 18 && comfortIndex <= 26 && pm25 < 55 ? 1 : 0;
            int uncomfortable = comfortIndex < 15 || comfortIndex > 29 || pm25 >= 75 ? 1 : 0;
            int attention = comfortable == 0 && uncomfortable == 0 ? 1 : 0;

            outKey.set(fields[1]);
            outValue.set(String.format("%.4f,%d,%d,%d", comfortIndex, comfortable, attention, uncomfortable));
            context.write(outKey, outValue);
        }
    }

    public static class ComfortReducer extends Reducer<Text, Text, Text, Text> {
        @Override
        protected void reduce(Text key, Iterable<Text> values, Context context)
                throws IOException, InterruptedException {
            int samples = 0;
            int comfortable = 0;
            int attention = 0;
            int uncomfortable = 0;
            double indexSum = 0;

            for (Text value : values) {
                String[] fields = value.toString().split(",");
                if (fields.length != 4) {
                    continue;
                }
                samples++;
                indexSum += Double.parseDouble(fields[0]);
                comfortable += Integer.parseInt(fields[1]);
                attention += Integer.parseInt(fields[2]);
                uncomfortable += Integer.parseInt(fields[3]);
            }

            double average = samples == 0 ? 0 : indexSum / samples;
            double comfortRate = samples == 0 ? 0 : comfortable * 100.0 / samples;
            context.write(key, new Text(String.format(
                    "sample_count=%d,comfort_index_avg=%.2f,comfortable_count=%d,attention_count=%d,uncomfortable_count=%d,comfort_rate=%.2f",
                    samples,
                    average,
                    comfortable,
                    attention,
                    uncomfortable,
                    comfortRate
            )));
        }
    }

    @Override
    public int run(String[] args) throws Exception {
        String input = args.length >= 1 ? args[0] : "/waether/input";
        String output = args.length >= 2 ? args[1] : "/waether/comfort_output";
        boolean overwrite = args.length >= 3 && "--overwrite".equals(args[2]);

        Configuration conf = WeatherJobSupport.configureCluster(getConf());
        WeatherJobSupport.prepareOutput(conf, output, overwrite);
        Job job = Job.getInstance(conf, "weather daily comfort");
        WeatherJobSupport.attachJobJar(job, WeatherDailyComfortMR.class);
        job.setMapperClass(ComfortMapper.class);
        job.setReducerClass(ComfortReducer.class);
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
        System.exit(ToolRunner.run(new Configuration(), new WeatherDailyComfortMR(), args));
    }
}
