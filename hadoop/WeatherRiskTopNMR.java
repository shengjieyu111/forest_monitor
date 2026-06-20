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
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Locale;
import java.util.PriorityQueue;

public class WeatherRiskTopNMR extends Configured implements Tool {
    private static final int DEFAULT_TOP_N = 10;

    public static class TopNMapper extends Mapper<Object, Text, Text, Text> {
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

            outKey.set(fields[1]);
            outValue.set(fields[3] + "," + fields[4] + "," + fields[5] + "," + fields[6]);
            context.write(outKey, outValue);
        }
    }

    public static class TopNReducer extends Reducer<Text, Text, Text, Text> {
        private PriorityQueue<DailyRiskRank> topRanks;
        private int topN;

        @Override
        protected void setup(Context context) {
            topN = context.getConfiguration().getInt("weather.topn", DEFAULT_TOP_N);
            topRanks = new PriorityQueue<DailyRiskRank>();
        }

        @Override
        protected void reduce(Text key, Iterable<Text> values, Context context) {
            int samples = 0;
            int dangerousSamples = 0;
            double scoreSum = 0;
            double tempPeak = Double.NEGATIVE_INFINITY;
            double humidityLow = Double.POSITIVE_INFINITY;
            double pm25Peak = Double.NEGATIVE_INFINITY;
            double illuminationPeak = Double.NEGATIVE_INFINITY;

            for (Text value : values) {
                String[] fields = value.toString().split(",");
                if (fields.length != 4) {
                    continue;
                }

                double temp = Double.parseDouble(fields[0]);
                double humidity = Double.parseDouble(fields[1]);
                double pm25 = Double.parseDouble(fields[2]);
                double illumination = Double.parseDouble(fields[3]);
                boolean dangerous = temp >= 28 || humidity >= 85 || pm25 >= 55
                        || (temp >= 28 && humidity <= 72 && illumination >= 75000);

                double score = Math.max(0, temp - 28) * 3.0
                        + Math.max(0, 65 - humidity) * 1.5
                        + Math.max(0, pm25 - 55) * 1.2
                        + (illumination >= 75000 ? 8.0 : 0.0);
                if (temp >= 28 && humidity <= 72 && illumination >= 75000) {
                    score += 25.0;
                }

                samples++;
                dangerousSamples += dangerous ? 1 : 0;
                scoreSum += score;
                tempPeak = Math.max(tempPeak, temp);
                humidityLow = Math.min(humidityLow, humidity);
                pm25Peak = Math.max(pm25Peak, pm25);
                illuminationPeak = Math.max(illuminationPeak, illumination);
            }

            if (samples == 0) {
                return;
            }

            DailyRiskRank rank = new DailyRiskRank(
                    key.toString(),
                    scoreSum / samples,
                    dangerousSamples,
                    tempPeak,
                    humidityLow,
                    pm25Peak,
                    illuminationPeak
            );
            topRanks.offer(rank);
            if (topRanks.size() > topN) {
                topRanks.poll();
            }
        }

        @Override
        protected void cleanup(Context context) throws IOException, InterruptedException {
            List<DailyRiskRank> ranks = new ArrayList<DailyRiskRank>(topRanks);
            Collections.sort(ranks, Collections.reverseOrder());
            for (int index = 0; index < ranks.size(); index++) {
                DailyRiskRank rank = ranks.get(index);
                context.write(
                        new Text(String.format(Locale.US, "%02d", index + 1)),
                        new Text(String.format(
                                Locale.US,
                                "date=%s,risk_score=%.2f,dangerous_count=%d,temp_peak=%.1f,"
                                        + "humidity_low=%.1f,pm25_peak=%.1f,illumination_peak=%.1f",
                                rank.date,
                                rank.riskScore,
                                rank.dangerousCount,
                                rank.tempPeak,
                                rank.humidityLow,
                                rank.pm25Peak,
                                rank.illuminationPeak
                        ))
                );
            }
        }
    }

    private static class DailyRiskRank implements Comparable<DailyRiskRank> {
        private final String date;
        private final double riskScore;
        private final int dangerousCount;
        private final double tempPeak;
        private final double humidityLow;
        private final double pm25Peak;
        private final double illuminationPeak;

        private DailyRiskRank(
                String date,
                double riskScore,
                int dangerousCount,
                double tempPeak,
                double humidityLow,
                double pm25Peak,
                double illuminationPeak
        ) {
            this.date = date;
            this.riskScore = riskScore;
            this.dangerousCount = dangerousCount;
            this.tempPeak = tempPeak;
            this.humidityLow = humidityLow;
            this.pm25Peak = pm25Peak;
            this.illuminationPeak = illuminationPeak;
        }

        @Override
        public int compareTo(DailyRiskRank other) {
            int scoreComparison = Double.compare(riskScore, other.riskScore);
            return scoreComparison != 0 ? scoreComparison : date.compareTo(other.date);
        }
    }

    @Override
    public int run(String[] args) throws Exception {
        String input = args.length >= 1 ? args[0] : "/waether/input";
        String output = args.length >= 2 ? args[1] : "/waether/topn_output";
        boolean overwrite = args.length >= 3 && "--overwrite".equals(args[2]);
        int topN = args.length >= 4 ? Integer.parseInt(args[3]) : DEFAULT_TOP_N;

        Configuration conf = WeatherJobSupport.configureCluster(getConf());
        conf.setInt("weather.topn", topN);
        WeatherJobSupport.prepareOutput(conf, output, overwrite);
        Job job = Job.getInstance(conf, "weather risk top n");
        WeatherJobSupport.attachJobJar(job, WeatherRiskTopNMR.class);
        job.setMapperClass(TopNMapper.class);
        job.setReducerClass(TopNReducer.class);
        job.setNumReduceTasks(1);
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
        System.exit(ToolRunner.run(new Configuration(), new WeatherRiskTopNMR(), args));
    }
}
