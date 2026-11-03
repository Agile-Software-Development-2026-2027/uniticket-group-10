"""Local TCP gateway: forward browser traffic only to the isolated demo app."""
import selectors
import socket
import socketserver


class Forward(socketserver.BaseRequestHandler):
    def handle(self):
        with socket.create_connection(("lab", 8000), timeout=10) as upstream:
            upstream.settimeout(None)
            with selectors.DefaultSelector() as selector:
                selector.register(self.request, selectors.EVENT_READ, upstream)
                selector.register(upstream, selectors.EVENT_READ, self.request)
                while True:
                    for key, _ in selector.select():
                        data = key.fileobj.recv(65536)
                        if not data:
                            return
                        key.data.sendall(data)


class Server(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


with Server(("0.0.0.0", 8000), Forward) as server:
    server.serve_forever()
