import html
import logging
from squall import coroutine
from squall.network import bind_sockets
from gateway import SAGIGateway

HTML = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Simple ASGI application</title>
</head>
<body>
  <h3>ASGI environ</h3>
  <table>
    <tr><th>Name</th><th>Value</th></tr>
    ----- >8 -----
  </table>
</body>
</html>
"""


class SAGIServer(SAGIGateway):

    def __init__(self):
        super(SAGIServer, self).__init__(
            self.handle_request, timeout=15.0)

    def start(self, port, address=None):
        sockets = bind_sockets(port, address=address, backlog=256)
        super(SAGIServer, self).start(sockets)
        coroutine.run()

    async def handle_request(self, environ, start_response):
        header, footer = HTML.split('----- >8 -----')
        rows = [(k, html.escape(str(v))) for k, v in environ.items()]
        write = start_response('200 OK', [('Content-Type', 'text/html')])
        await write(header.encode('UTF-8'))
        for row in sorted(rows, key=lambda item: item[0]):
            await write("<tr><td>{}</th><td>{}</td></tr>"
                        "\n".format(*row).encode('UTF-8'))
        await write(footer.encode('UTF-8'))


if __name__ == '__main__':

    logging.basicConfig(level=logging.DEBUG)
    SAGIServer().start(9000)
