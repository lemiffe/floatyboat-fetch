from tornado.wsgi import WSGIContainer
from tornado.httpserver import HTTPServer
from tornado.ioloop import IOLoop
import os
from main import *

if __name__ == "__main__":
        http_server = HTTPServer(WSGIContainer(app))
        port = int(os.environ.get("PORT", 1337))
        http_server.listen(port)
        IOLoop.instance().start()
