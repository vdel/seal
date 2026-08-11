// Karma configuration used only by the `test` Docker stage (see Dockerfile),
// to run the unit tests headlessly and produce junit + cobertura reports that
// `seal ci` copies back to tests-results/ (see tilt/seal at the repo root).
process.env.CHROME_BIN = process.env.CHROME_BIN || '/usr/bin/chromium-browser';

module.exports = function (config) {
  config.set({
    basePath: '',
    frameworks: ['jasmine'],
    plugins: [
      require('karma-jasmine'),
      require('karma-chrome-launcher'),
      require('karma-coverage'),
      require('karma-junit-reporter'),
    ],
    coverageReporter: {
      dir: require('path').join(__dirname, 'tests-results/ui'),
      subdir: '.',
      reporters: [
        { type: 'cobertura', file: 'coverage.xml' },
        { type: 'text-summary' },
      ],
    },
    junitReporter: {
      outputDir: require('path').join(__dirname, 'tests-results/ui'),
      outputFile: 'junit.xml',
      useBrowserName: false,
    },
    customLaunchers: {
      ChromeHeadlessCI: {
        base: 'ChromeHeadless',
        flags: ['--no-sandbox', '--disable-gpu', '--disable-dev-shm-usage'],
      },
    },
    reporters: ['progress', 'coverage', 'junit'],
    port: 9876,
    colors: true,
    logLevel: config.LOG_INFO,
    autoWatch: false,
    browsers: ['ChromeHeadlessCI'],
    singleRun: true,
    restartOnFileChange: false,
  });
};
