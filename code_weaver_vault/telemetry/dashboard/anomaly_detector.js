// Detects failures in modular flows
function detectAnomaly(metrics) {
  if (metrics.drift_score > 0.7) {
    console.log("Anomaly detected: High drift score");
    return true;
  }
  return false;
}

module.exports = { detectAnomaly };