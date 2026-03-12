import sys
import os
from urllib.request import urlopen
from urllib.parse import urljoin
from html.parser import HTMLParser

if len(sys.argv) < 3:
    print("Usage: python patch_download.py <cfentry> <prefix> [download_dir]")
    sys.exit(1)

cfentry = sys.argv[1]
prefix = sys.argv[2]
download_dir = os.path.expanduser(sys.argv[3]) if len(sys.argv) > 3 else os.path.expanduser("~/Downloads")

os.makedirs(download_dir, exist_ok=True)

class LinkParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            for k, v in attrs:
                if k == "href":
                    self.links.append(v)

url = f"https://commitfest.postgresql.org/patch/{cfentry}"
html = urlopen(url).read().decode()
parser = LinkParser()
parser.feed(html)

for link in parser.links:
    filename = link.split("/")[-1]

    if filename.startswith(prefix):
        file_url = urljoin(url, link)
        print("Downloading", file_url)

        data = urlopen(file_url).read()
        path = os.path.join(download_dir, filename)

        with open(path, "wb") as f:
            f.write(data)

print("Saved to:", download_dir)
