import os
import struct
import numpy as np

def get_ply_bbox(filepath):
    """Parses a PLY file and returns the bounding box (min_x, min_y, min_z, max_x, max_y, max_z)."""
    with open(filepath, 'rb') as f:
        header = ""
        while True:
            line = f.readline().decode('ascii', errors='ignore')
            header += line
            if "end_header" in line:
                break
        
        # Simple header parsing
        num_vertices = 0
        is_binary = "format binary_little_endian" in header
        
        for line in header.split('\n'):
            if "element vertex" in line:
                num_vertices = int(line.split()[-1])
        
        if num_vertices == 0:
            return None

        points = []
        if is_binary:
            # Assumes vertex format is float x, y, z (3 * 4 bytes)
            # Find property offset (usually 0)
            data = f.read(num_vertices * 12) # 3 floats
            points = np.frombuffer(data, dtype='f4').reshape(-1, 3)
        else:
            # ASCII - very slow for large files but robust
            for _ in range(num_vertices):
                line = f.readline().decode('ascii', errors='ignore').split()
                if len(line) >= 3:
                    points.append([float(line[0]), float(line[1]), float(line[2])])
            points = np.array(points)

        return np.min(points, axis=0), np.max(points, axis=0)

ply_dir = "PLY_FILES"
results = {}

for filename in os.listdir(ply_dir):
    if filename.endswith(".ply"):
        path = os.path.join(ply_dir, filename)
        print(f"Analyzing {filename}...")
        bbox = get_ply_bbox(path)
        if bbox:
            results[filename] = {
                "min": bbox[0].tolist(),
                "max": bbox[1].tolist(),
                "center": ((bbox[0] + bbox[1]) / 2).tolist(),
                "size": (bbox[1] - bbox[0]).tolist()
            }

import json
print(json.dumps(results, indent=4))
