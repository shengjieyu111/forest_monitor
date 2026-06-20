import org.apache.hadoop.conf.Configuration;
import org.apache.hadoop.util.ToolRunner;

public class WeatherAnalyticsSuite {
    public static void main(String[] args) throws Exception {
        String input = args.length >= 1 ? args[0] : "/waether/input";
        String outputRoot = args.length >= 2 ? args[1] : "/waether";

        System.setProperty("HADOOP_USER_NAME", "root");

        int daily = ToolRunner.run(
                new Configuration(),
                new WeatherStatsMR(),
                new String[]{input, outputRoot + "/output", "--overwrite"}
        );
        if (daily != 0) {
            System.exit(daily);
        }

        int hourly = ToolRunner.run(
                new Configuration(),
                new WeatherHourlyProfileMR(),
                new String[]{input, outputRoot + "/hourly_output", "--overwrite"}
        );
        if (hourly != 0) {
            System.exit(hourly);
        }

        int risk = ToolRunner.run(
                new Configuration(),
                new WeatherDailyRiskMR(),
                new String[]{input, outputRoot + "/risk_output", "--overwrite"}
        );
        if (risk != 0) {
            System.exit(risk);
        }

        int comfort = ToolRunner.run(
                new Configuration(),
                new WeatherDailyComfortMR(),
                new String[]{input, outputRoot + "/comfort_output", "--overwrite"}
        );
        if (comfort != 0) {
            System.exit(comfort);
        }

        int topN = ToolRunner.run(
                new Configuration(),
                new WeatherRiskTopNMR(),
                new String[]{input, outputRoot + "/topn_output", "--overwrite", "10"}
        );
        System.exit(topN);
    }
}
