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

public class WeatherDailyRiskMR extends Configured implements Tool {
    public static class RiskMapper extends Mapper<Object, Text, Text, Text> {
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
            double illumination = Double.parseDouble(fields[6]);
            int highTemp = temp >= 28 ? 1 : 0;
            int highHumidity = humidity >= 85 ? 1 : 0;
            int pollution = pm25 >= 55 ? 1 : 0;
            int fire = temp >= 28 && humidity <= 72 && illumination >= 75000 ? 1 : 0;
            int normal = highTemp == 0 && highHumidity == 0 && pollution == 0 && fire == 0 ? 1 : 0;

            outKey.set(fields[1]);
            outValue.set(highTemp + "," + highHumidity + "," + pollution + "," + fire + "," + normal);
            context.write(outKey, outValue);
        }
    }

    public static class RiskReducer extends Reducer<Text, Text, Text, Text> {
        @Override
        protected void reduce(Text key, Iterable<Text> values, Context context)
                throws IOException, InterruptedException {
            int samples = 0;
            int highTemp = 0;
            int highHumidity = 0;
            int pollution = 0;
            int fire = 0;
            int normal = 0;

            for (Text value : values) {
                String[] fields = value.toString().split(",");
                if (fields.length != 5) {
                    continue;
                }
                samples++;
                highTemp += Integer.parseInt(fields[0]);
                highHumidity += Integer.parseInt(fields[1]);
                pollution += Integer.parseInt(fields[2]);
                fire += Integer.parseInt(fields[3]);
                normal += Integer.parseInt(fields[4]);
            }

            double riskRate = samples == 0 ? 0 : (samples - normal) * 100.0 / samples;
            context.write(key, new Text(String.format(
                    "sample_count=%d,high_temp_count=%d,high_humidity_count=%d,pollution_count=%d,fire_risk_count=%d,normal_count=%d,risk_rate=%.2f",
                    samples,
                    highTemp,
                    highHumidity,
                    pollution,
                    fire,
                    normal,
                    riskRate
            )));
        }
    }

    @Override
    public int run(String[] args) throws Exception {
        String input = args.length >= 1 ? args[0] : "/waether/input";
        String output = args.length >= 2 ? args[1] : "/waether/risk_output";
        boolean overwrite = args.length >= 3 && "--overwrite".equals(args[2]);

        Configuration conf = WeatherJobSupport.configureCluster(getConf());
        WeatherJobSupport.prepareOutput(conf, output, overwrite);
        Job job = Job.getInstance(conf, "weather daily risk");
        WeatherJobSupport.attachJobJar(job, WeatherDailyRiskMR.class);
        job.setMapperClass(RiskMapper.class);
        job.setReducerClass(RiskReducer.class);
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
        System.exit(ToolRunner.run(new Configuration(), new WeatherDailyRiskMR(), args));
    }
}
