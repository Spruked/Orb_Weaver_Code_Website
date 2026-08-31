# Scripts: write/read/consolidate (e.g., sleep-like replay)
import yaml
import json

def consolidate_memory(matrix_file):
    with open(matrix_file, 'r') as f:
        data = yaml.safe_load(f)
    # Example: Simple consolidation logic
    print("Consolidating memory matrix...")
    # Implement replay and hash logic here
    consolidated = {}
    for key, value in data.get('matrices', {}).items():
        consolidated[key] = value  # Placeholder
    return consolidated

def write_memory(key, value, matrix_file):
    with open(matrix_file, 'r') as f:
        data = yaml.safe_load(f)
    data['matrices'][key] = value
    with open(matrix_file, 'w') as f:
        yaml.dump(data, f)
    print(f"Memory written: {key}")

def read_memory(key, matrix_file):
    with open(matrix_file, 'r') as f:
        data = yaml.safe_load(f)
    return data.get('matrices', {}).get(key)

if __name__ == "__main__":
    consolidate_memory("matrix_store.yaml")