# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program. If not, see <https://www.gnu.org/licenses/>.
#
# Copyright (c) [2025] [Roman Tenger]
import re
import math
import sys
import logging
import argparse


logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("gcode_debug.log"),
        logging.StreamHandler(sys.stdout)
    ]
)

# Default parameters for non-planar infill modulation
DEFAULT_AMPLITUDE = 0.6  # Default Z variation in mm
DEFAULT_FREQUENCY = 1.1  # Default frequency of the sine wave
SEGMENT_LENGTH = 1.0  # Split infill lines into segments of this length (mm)

def segment_line(x1, y1, x2, y2, segment_length):
    """Divide a line into smaller segments."""
    segments = []
    total_length = math.sqrt((x2 - x1)**2 + (y2 - y1)**2)
    num_segments = max(1, int(total_length // segment_length))
    
    for i in range(num_segments + 1):
        t = i / num_segments
        x = x1 + t * (x2 - x1)
        y = y1 + t * (y2 - y1)
        segments.append((x, y))
    
    logging.debug(f"Segmented line ({x1}, {y1}) -> ({x2}, {y2}) into {len(segments)} segments.")
    return segments

def reset_modulation_state():
    """Reset parameters for Z-modulation to avoid propagating patterns."""
    global last_sx
    last_sx = 0

def process_gcode(input_file, amplitude, frequency):
    modified_lines = []
    current_z = 0
    in_infill = False
    last_bottom_layer = 0
    next_top_layer = float('inf')
    processed_indices = set()  

    logging.info(f"Processing file: {input_file}")

    with open(input_file, 'r') as file:
        lines = file.readlines()

    solid_infill_heights = []
    for line in lines:
        if line.startswith('G1') and 'Z' in line:
            z_match = re.search(r'Z([-+]?\d*\.?\d+)', line)
            if z_match:
                current_z = float(z_match.group(1))
        if ';TYPE:Solid infill' or ';TYPE:Internal solid infill' in line:
            solid_infill_heights.append(current_z)

    def update_layer_bounds(current_z):
        nonlocal last_bottom_layer, next_top_layer
        lower_layers = [z for z in solid_infill_heights if z < current_z]
        upper_layers = [z for z in solid_infill_heights if z > current_z]
        if lower_layers:
            last_bottom_layer = max(lower_layers)
        if upper_layers:
            next_top_layer = min(upper_layers)

    for line_num, line in enumerate(lines):
        if line.startswith('G1') and 'Z' in line:
            z_match = re.search(r'Z([-+]?\d*\.?\d+)', line)
            if z_match:
                current_z = float(z_match.group(1))
                reset_modulation_state()
                update_layer_bounds(current_z)
                logging.debug(f"Layer change detected: Z = {current_z}")

        if ';TYPE:Internal infill' or ';TYPE:Sparse infill' in line:
            in_infill = True
            logging.debug(f"Entered infill section at line {line_num}.")
        elif line.startswith(';TYPE:'):
            if in_infill:
                logging.debug(f"Exited infill section at line {line_num}.")
            in_infill = False

        if in_infill and line_num not in processed_indices and 'E' in line:
            processed_indices.add(line_num)
            match = re.search(r'X([-+]?\d*\.?\d+)\s*Y([-+]?\d*\.?\d+)\s*E([-+]?\d*\.?\d+)', line)
            if match:
                x1 = float(match.group(1))
                y1 = float(match.group(2))
                e = float(match.group(3))

                next_line_index = line_num + 1
                if next_line_index < len(lines):
                    next_line = lines[next_line_index]
                    next_match = re.search(r'X([-+]?\d*\.?\d+)\s*Y([-+]?\d*\.?\d+)\s*E([-+]?\d*\.?\d+)', next_line)
                    if next_match:
                        x2 = float(next_match.group(1))
                        y2 = float(next_match.group(2))

                        segments = segment_line(x1, y1, x2, y2, SEGMENT_LENGTH)
                        for i, (sx, sy) in enumerate(segments):
                            extrusion_per_segment = e
                            num_segments = len(segments)
                            if num_segments > 0:  
                                extrusion_per_segment = e / num_segments
                           
                            distance_to_top = next_top_layer - current_z
                            distance_to_bottom = current_z - last_bottom_layer
                            total_distance = next_top_layer - last_bottom_layer
                            scaling_factor = min(distance_to_top, distance_to_bottom) / total_distance
                            z_mod = current_z + amplitude * scaling_factor * math.sin(frequency * sx)
                            modified_line = f"G1 X{sx:.3f} Y{sy:.3f} Z{z_mod:.3f} E{extrusion_per_segment:.5f}\n"
                            modified_lines.append(modified_line)
                            logging.debug(f"Modified segment {i}: {modified_line.strip()}")
                        continue

        modified_lines.append(line)

    return modified_lines

def save_gcode(output_file, lines):
    with open(output_file, 'w') as file:
        file.writelines(lines)
    logging.info(f"Saved modified G-code to: {output_file}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Add non-planar modulation to G-code.")
    parser.add_argument("input_file", help="The input G-code file.")
    parser.add_argument("-amplitude", "--amplitude", type=float, default=DEFAULT_AMPLITUDE, help="Amplitude of the Z modulation (default: 0.6).")
    parser.add_argument("-frequency", "--frequency", type=float, default=DEFAULT_FREQUENCY, help="Frequency of the Z modulation (default: 1.1).")

    args = parser.parse_args()

    input_file = args.input_file
    amplitude = args.amplitude
    frequency = args.frequency
    output_file = input_file 

    logging.info(f"Using amplitude: {amplitude}, frequency: {frequency}")

    modified_lines = process_gcode(input_file, amplitude, frequency)
    save_gcode(output_file, modified_lines)
