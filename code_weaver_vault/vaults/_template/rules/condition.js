// Example: Simple condition in JavaScript
function evaluate(input) {
  if (input.query.includes("emergency")) {
    return { action: "escalate", certainty: 0.95 };
  }
  return { action: "ignore", certainty: 0.1 };
}