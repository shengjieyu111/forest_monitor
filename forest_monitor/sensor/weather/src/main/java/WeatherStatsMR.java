
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
import org.apache.log4j.BasicConfigurator;
import org.apache.log4j.Level;
import org.apache.log4j.Logger;

import java.io.IOException;

public class WeatherStatsMR extends Configured implements Tool {
    public static class WeatherMapper extends Mapper<Object, Text, Text, Text> {
        private final Text outKey = new Text();
        private final Text outValue = new Text();

        @Override
        protected void map(Object key, Text value, Context context) throws IOException, InterruptedException {
            String line = value.toString().trim();
            if (line.isEmpty() || line.startsWith("city,date,hour")) {
                return;
            }

            String[] fields = line.split(",");
            if (fields.length != 7) {
                return;
            }

            String date = fields[1];
            String temperature = fields[3];
            String humidity = fields[4];
            String pm25 = fields[5];
            String illumination = fields[6];

            outKey.set(date);
            outValue.set(temperature + "," + humidity + "," + pm25 + "," + illumination);
            context.write(outKey, outValue);
        }
    }

    public static class WeatherReducer extends Reducer<Text, Text, Text, Text> {
        @Override
        protected void reduce(Text key, Iterable<Text> values, Context context) throws IOException, InterruptedException {
            int count = 0;
            double tempSum = 0.0;
            double humiditySum = 0.0;
            double pm25Sum = 0.0;
            double illuminationSum = 0.0;
            double tempPeak = Double.NEGATIVE_INFINITY;
            double humidityPeak = Double.NEGATIVE_INFINITY;
            double pm25Peak = Double.NEGATIVE_INFINITY;
            double illuminationPeak = Double.NEGATIVE_INFINITY;

            for (Text value : values) {
                String[] parts = value.toString().split(",");
                if (parts.length != 4) {
                    continue;
                }

                double temp = Double.parseDouble(parts[0]);
                double humidity = Double.parseDouble(parts[1]);
                double pm25 = Double.parseDouble(parts[2]);
                double illumination = Double.parseDouble(parts[3]);

                count++;
                tempSum += temp;
                humiditySum += humidity;
                pm25Sum += pm25;
                illuminationSum += illumination;
                tempPeak = Math.max(tempPeak, temp);
                humidityPeak = Math.max(humidityPeak, humidity);
                pm25Peak = Math.max(pm25Peak, pm25);
                illuminationPeak = Math.max(illuminationPeak, illumination);
            }

            if (count == 0) {
                return;
            }

            double tempAvg = tempSum / count;
            double humidityAvg = humiditySum / count;
            double pm25Avg = pm25Sum / count;
            double illuminationAvg = illuminationSum / count;
            String warning = buildWarning(tempAvg, tempPeak, humidityAvg, pm25Avg, pm25Peak, illuminationPeak);

            String result = String.format(
                "temp_avg=%.2f,temp_peak=%.1f,humidity_avg=%.2f,humidity_peak=%.1f,pm25_avg=%.2f,pm25_peak=%.1f,illumination_avg=%.2f,illumination_peak=%.1f,risk_warning=%s",
                tempAvg,
                tempPeak,
                humidityAvg,
                humidityPeak,
                pm25Avg,
                pm25Peak,
                illuminationAvg,
                illuminationPeak,
                warning
            );
            context.write(key, new Text(result));
        }

        private String buildWarning(
            double tempAvg,
            double tempPeak,
            double humidityAvg,
            double pm25Avg,
            double pm25Peak,
            double illuminationPeak
        ) {
            StringBuilder warning = new StringBuilder();
            if (tempPeak >= 35 || tempAvg >= 32) {
                appendWarning(warning, "高温预警");
            }
            if (humidityAvg >= 85) {
                appendWarning(warning, "高湿预警");
            }
            if (pm25Peak >= 75 || pm25Avg >= 55) {
                appendWarning(warning, "PM2.5污染预警");
            }
            if (tempPeak >= 28 && humidityAvg <= 72 && illuminationPeak >= 75000) {
                appendWarning(warning, "火灾预警");
            }
            return warning.length() == 0 ? "正常" : warning.toString();
        }

        private void appendWarning(StringBuilder warning, String value) {
            if (warning.length() > 0) {
                warning.append("、");
            }
            warning.append(value);
        }
    }

    @Override
    public int run(String[] args) throws Exception {
        if (args.length != 0 && args.length != 2 && args.length != 3) {
            System.err.println("Usage: WeatherStatsMR [input output --overwrite]");
            return 2;
        }

        String inputPath = args.length >= 2 ? args[0] : "/waether/input";
        String outputPath = args.length >= 2 ? args[1] : "/waether/output";
        boolean overwrite = args.length == 3 && "--overwrite".equals(args[2]);

        System.setProperty("HADOOP_USER_NAME", "root");
        Configuration conf = WeatherJobSupport.configureCluster(getConf());
        WeatherJobSupport.prepareOutput(conf, outputPath, overwrite);

        Job job = Job.getInstance(conf, "weather statistics");
        WeatherJobSupport.attachJobJar(job, WeatherStatsMR.class);

        job.setMapperClass(WeatherMapper.class);
        job.setReducerClass(WeatherReducer.class);

        job.setMapOutputKeyClass(Text.class);
        job.setMapOutputValueClass(Text.class);
        job.setOutputKeyClass(Text.class);
        job.setOutputValueClass(Text.class);

        FileInputFormat.addInputPath(
                job,
                new Path(inputPath)
        );

        FileOutputFormat.setOutputPath(
                job,
                new Path(outputPath)
        );

        return WeatherJobSupport.waitForCompletion(job);
    }

    public static void main(String[] args) throws Exception {
        Logger rootLogger = Logger.getRootLogger();
        if (!rootLogger.getAllAppenders().hasMoreElements()) {
            BasicConfigurator.configure();
            rootLogger.setLevel(Level.INFO);
        }

        int exitCode = ToolRunner.run(new Configuration(), new WeatherStatsMR(), args);
        System.exit(exitCode);
    }
}
