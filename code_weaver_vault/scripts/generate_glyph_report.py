# Visualize traces
import json

def generate_glyph_report(trace_file):
    with open(trace_file, 'r') as f:
        data = json.load(f)
    # Visualize traces
import json

def generate_glyph_report(trace_file):
    with open(trace_file, 'r') as f:
        data = json.load(f)
    print("Glyph Report:", data)
    # Placeholder: Generate SVG or report
    return data

if __name__ == "__main__":
    generate_glyph_report("examples/input_career_change.json")

if __name__ == "__main__":
    generate_glyph_report("examples/input_career_change.json")