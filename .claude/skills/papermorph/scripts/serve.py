#!/usr/bin/env python3
"""Local preview without browser caching, so an edited engine or chapter is never hidden by a stale copy.

    python3 serve.py 8765 site        # then open http://localhost:8765/<book>/

python3 -m http.server sends no Cache-Control and has a backlog of 5, which drops connections when a page opens
many files at once; this server sends no-store and queues up to 128.
"""
import functools, http.server, os, sys

class NoStore(http.server.SimpleHTTPRequestHandler):
    """no-store, plus HTTP Range (206): without it browsers cannot seek inside an audio clip and every jump in the
    timeline restarts the clip from 0."""
    def send_head(self):
        rng = self.headers.get("Range")
        path = self.translate_path(self.path)
        if not rng or not rng.startswith("bytes=") or not os.path.isfile(path):
            return super().send_head()
        size = os.path.getsize(path)
        a, _, b = rng[6:].split(",")[0].partition("-")
        try:
            if a == "":
                start, end = max(0, size - int(b)), size - 1
            else:
                start, end = int(a), min(int(b) if b else size - 1, size - 1)
        except ValueError:
            return super().send_head()
        if start > end or start >= size:
            self.send_error(416)
            return None
        f = open(path, "rb")
        f.seek(start)
        self.send_response(206)
        self.send_header("Content-Type", self.guess_type(path))
        self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.send_header("Content-Length", str(end - start + 1))
        self.end_headers()
        self._left = end - start + 1
        return f

    def copyfile(self, source, outputfile):
        left = getattr(self, "_left", None)
        if left is None:
            return super().copyfile(source, outputfile)
        while left > 0:
            chunk = source.read(min(65536, left))
            if not chunk:
                break
            outputfile.write(chunk)
            left -= len(chunk)

    def do_GET(self):
        self._left = None
        super().do_GET()

    def end_headers(self):
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

class Server(http.server.ThreadingHTTPServer):
    request_queue_size = 128
    daemon_threads = True

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(0 if sys.argv[1:] in (["-h"], ["--help"]) else 2)
    port, root = int(sys.argv[1]), sys.argv[2]
    print(f"serving {root} at http://localhost:{port}/ (no-store)", flush=True)
    Server(("", port), functools.partial(NoStore, directory=root)).serve_forever()
