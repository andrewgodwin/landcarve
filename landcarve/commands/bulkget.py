import os
import urllib.request

import click
import requests
import shutil

from landcarve.cli import main


@main.command()
@click.argument("input_path")
@click.argument("output_path")
def bulkget(input_path, output_path):
    """
    Bulk downloads information from the national map downloader, auto-filtering
    out "useless" URLs.
    """
    # Calculate the correct set of urls
    urls = []
    with open(input_path) as fh:
        for line in fh:
            line = line.strip()
            if "metadata" in line or line.endswith(".html") or line.endswith("/"):
                continue
            urls.append(line)
    # Download them
    for n, url in enumerate(urls):
        filename = url.split("/")[-1]
        local_path = os.path.join(output_path, filename)
        click.echo(f"[{n+1}/{len(urls)}] {filename}")
        urllib.request.urlretrieve(url, local_path)

    urllib.request.urlcleanup()
