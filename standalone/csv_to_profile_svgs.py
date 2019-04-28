"""
CSV-to-SVG converter.
"""

from __future__ import unicode_literals

import csv
import argparse
import svgwrite

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("-x", "--xspacing", type=float, default=1)
    parser.add_argument("-y", "--yspacing", type=float, default=50)
    parser.add_argument("-d", "--distortion", type=float, default=0.05)
    parser.add_argument("-r", "--root", type=float, default=1)
    parser.add_argument("-s", "--stroke", type=float, default=10)
    parser.add_argument("-m", "--smoothing", type=float, default=0)
    parser.add_argument("-g", "--merge", type=int, default=1)
    parser.add_argument("-p", "--printable", type=bool, default=False)
    parser.add_argument("-z", "--minyspacing", type=float, default=0)
    parser.add_argument("-o", "--output", default="output.svg")
    parser.add_argument("file")
    args = parser.parse_args()

    rows = {}

    # Load the CSV
    print("Loading CSV")
    with open(args.file) as csvfile:
        reader = csv.reader(csvfile)
        for x, y, _, value in reader:
            if x == "X":
                continue
            x, y, value = float(x), float(y), float(value)
            rows.setdefault(y, [])
            # Scale value compared to max height
            if value < 0:
                value = 0
            rows[y].append((x, (value ** args.root)))

    # Draw lines from sorted data
    print("Saving")
    image_height = (len(rows) + 2) * args.yspacing
    image_width = len(rows.values()[0]) * args.xspacing
    output = svgwrite.Drawing(args.output, (image_width, image_height), profile="tiny")
    if args.printable:
        output_y = 0
    else:
        output_y = image_height - args.yspacing
    for y, values in sorted(rows.items()):
        # Optionally reduce values down
        if args.merge > 1:
            new_values = []
            value_iter = iter(sorted(values))
            total = 0
            try:
                while True:
                    total = 0
                    for _ in range(args.merge):
                        new_x, old_value = value_iter.next()
                        total += old_value
                    new_values.append((new_x, total / float(args.merge)))
            except StopIteration:
                pass
            values = new_values
        # Create points list
        points = [(0, output_y)]
        output_x = 0
        last_value = 0
        for x, value in sorted(values):
            output_x += (args.xspacing * args.merge)
            smoothed_value = (value * (1 - args.smoothing)) + (last_value * args.smoothing)
            points.append((
                float(output_x),
                float(output_y - (smoothed_value * args.distortion)),
            ))
            last_value = value
        if args.printable:
            #points.extend((x, y - args.stroke) for (x, y) in reversed(list(points)))
            points.append((output_x, output_y + args.stroke))
            points.append((0, output_y + args.stroke))
            points.append((0, output_y))
            output.add(output.polyline(points=points, stroke="none", fill="gray"))
            y_delta = output_y - (min(y for x, y in points) - args.yspacing - args.stroke)
            output_y -= max(y_delta, args.minyspacing)
        else:
            output.add(output.polyline(points=points, stroke="black", fill="none", stroke_width=args.stroke))
            output_y -= args.yspacing
    output.save()
    print("Saved %i rows with %i columns" % (len(rows), len(values)))

if __name__ == '__main__':
    main()
