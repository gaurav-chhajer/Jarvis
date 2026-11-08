"""Install the official portable Ollama CPU runtime without GPU downloads."""
import io
import urllib.request
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import time
import ssl

SSL_CONTEXT = ssl.create_default_context()

URL = 'https://github.com/ollama/ollama/releases/download/v0.40.15/ollama-windows-amd64.zip'


class RemoteZip(io.RawIOBase):
    def __init__(self, url=URL):
        with urllib.request.urlopen(urllib.request.Request(url, method='HEAD'), timeout=60, context=SSL_CONTEXT) as r:
            self.url = r.url
            self.size = int(r.headers['Content-Length'])
        self.pos = 0
        self.cache = []

    def seekable(self):
        return True

    def tell(self):
        return self.pos

    def seek(self, offset, whence=0):
        self.pos = offset if whence == 0 else (self.pos if whence == 1 else self.size) + offset
        return self.pos

    def read(self, size=-1):
        end = self.size if size < 0 else min(self.size, self.pos + size)
        if end <= self.pos:
            return b''
        for start, data in self.cache:
            if start <= self.pos and end <= start + len(data):
                result = data[self.pos-start:end-start]
                self.pos = end
                return result
        def fetch(bounds):
            start, stop = bounds
            for attempt in range(4):
                try:
                    req = urllib.request.Request(self.url, headers={'Range': f'bytes={start}-{stop-1}'})
                    with urllib.request.urlopen(req, timeout=120, context=SSL_CONTEXT) as r:
                        if r.status != 206:
                            raise RuntimeError('Server did not honor byte range')
                        data = r.read()
                    if len(data) != stop - start:
                        raise RuntimeError('Incomplete range response')
                    return data
                except Exception:
                    if attempt == 3:
                        raise
                    time.sleep(1)
        chunks = [(start, min(start + 1048576, end)) for start in range(self.pos, end, 1048576)]
        with ThreadPoolExecutor(max_workers=32) as pool:
            data = b''.join(pool.map(fetch, chunks))
        self.pos += len(data)
        return data


if __name__ == '__main__':
    remote = RemoteZip()
    with zipfile.ZipFile(remote) as z:
        target = Path('.runtime/ollama').resolve()
        entries = [entry for entry in z.infolist() if not entry.is_dir() and (
            entry.filename == 'ollama.exe' or
            entry.filename.startswith('lib/ollama/') and entry.filename.count('/') == 2)]
        ranges = []
        for entry in sorted(entries, key=lambda e: e.header_offset):
            start = entry.header_offset
            end = start + 30 + len(entry.filename.encode()) + len(entry.extra) + entry.compress_size + 512
            if ranges and start <= ranges[-1][1]:
                ranges[-1][1] = max(ranges[-1][1], end)
            else:
                ranges.append([start, min(end, remote.size)])
        for start, end in ranges:
            print('Downloading CPU archive range:', end-start, 'bytes', flush=True)
            remote.seek(start)
            remote.cache.append((start, remote.read(end-start)))
        for entry in entries:
            destination = (target / entry.filename).resolve()
            if not destination.is_relative_to(target):
                raise RuntimeError('Unsafe archive path')
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(z.read(entry))  # zipfile verifies each entry's CRC.
            print('Extracted', entry.filename, flush=True)
