// To Prometheus/Grafana
const fs = require('fs');

function exportTelemetry(data) {
  fs.writeFileSync('telemetry_export.json', JSON.stringify(data));
  console.log('Telemetry exported');
}

function formatForPrometheus(metrics) {
  // Placeholder: Format metrics
  return metrics;
}

module.exports = { exportTelemetry, formatForPrometheus };