"""Download compatible large wheels with parallel ranges and SHA256 verification."""
import hashlib
import json
from pathlib import Path
import urllib.request
import sys
from packaging.tags import sys_tags
from packaging.utils import parse_wheel_filename
from install_ollama_cpu import RemoteZip, SSL_CONTEXT

target = Path('.downloads')
target.mkdir(exist_ok=True)
tags = set(sys_tags())
versions = {'av': '17.1.0', 'ctranslate2': '4.8.5', 'onnxruntime': '1.31.1',
            'tokenizers': '0.23.3', 'hf-xet': '1.8.0'}
for package, version in versions.items():
    if len(sys.argv) > 1 and package not in sys.argv[1:]:
        continue
    with urllib.request.urlopen(f'https://pypi.org/pypi/{package}/{version}/json', timeout=120, context=SSL_CONTEXT) as r:
        metadata = json.load(r)
    for item in metadata['urls']:
        if not item['filename'].endswith('.whl'):
            continue
        if not (parse_wheel_filename(item['filename'])[3] & tags):
            continue
        path = target / item['filename']
        digest = item['digests']['sha256']
        if not path.exists() or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            print('Downloading', item['filename'], flush=True)
            data = RemoteZip(item['url']).read()
            if hashlib.sha256(data).hexdigest() != digest:
                raise RuntimeError('Wheel checksum mismatch')
            path.write_bytes(data)
        print('Verified', path.name, flush=True)
        break
    else:
        raise RuntimeError(f'No compatible wheel for {package}')
