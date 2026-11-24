// All options: https://remotion.dev/docs/config (they apply to the CLI, not the Node APIs).
import { Config } from "@remotion/cli/config";

Config.setRspack(true);
Config.setVideoImageFormat("jpeg");
Config.setOverwriteOutput(true);
Config.setDefaultPremountInSeconds(2);
