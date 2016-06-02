import html
import logging
from squall import coroutine
from squall.network import bind_sockets
from squall.gateway import SAGIGateway, SCGIBackend

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


class SAGIServer(SCGIBackend):

    def __init__(self, port, address=None):
        gateway = SAGIGateway(self.handle_request)
        sockets = bind_sockets(port, address=address, backlog=256)
        super(SAGIServer, self).__init__(gateway, sockets, timeout=15.0)

    def listen(self):
        super(SAGIServer, self).listen()
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

    logging.basicConfig(level=logging.INFO)
    SAGIServer(9000).listen()
