"""Local static production-build preview with same-origin API proxy; not for production."""
import http.client
from http.server import SimpleHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path

class Handler(SimpleHTTPRequestHandler):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,directory=str(Path(__file__).resolve().parents[1]/'frontend'/'out'),**kwargs)
    def proxy(self):
        length=int(self.headers.get('content-length','0'))
        body=self.rfile.read(length) if length else None
        conn=http.client.HTTPConnection('127.0.0.1',8000,timeout=60)
        conn.request(self.command,self.path,body,dict(self.headers))
        response=conn.getresponse();data=response.read()
        self.send_response(response.status)
        for k,v in response.getheaders():
            if k.lower() not in ['transfer-encoding','connection','content-length']:
                self.send_header(k,v)
        self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data);conn.close()
    def do_GET(self):
        return self.proxy() if self.path.startswith('/api/') else super().do_GET()
    do_POST=proxy
    do_DELETE=proxy
    do_PATCH=proxy
    do_PUT=proxy

ThreadingHTTPServer(('127.0.0.1',3000),Handler).serve_forever()
