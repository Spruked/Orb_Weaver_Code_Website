# Offline replay
# Similar to memory/consolidation.py
import yaml

def consolidate_offline(matrix_file):
    with open(matrix_file, 'r') as f:
        data = yaml.safe_load(f)
    print("Offline consolidation...")
    return data

if __name__ == "__main__":
    consolidate_offline("memory/matrix_store.yaml")