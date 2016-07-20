import html
import logging
from squall import scgi

HTML = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Simple SCGI application</title>
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

async def application(environ, start_response):
    charset = 'UTF-8'
    header, footer = HTML.split('----- >8 -----')
    rows = [(k, html.escape(str(v))) for k, v in environ.items()]
    write = start_response('200 OK', [('Content-Type',
                                       'text/html; charset=' + charset)])
    await write(header.encode(charset))
    for row in sorted(rows, key=lambda item: item[0]):
        await write("<tr><td>{}</th><td>{}</td></tr>"
                    "\n".format(*row).encode(charset))
    await write(footer.encode(charset))


if __name__ == '__main__':

    logging.basicConfig(level=logging.DEBUG)

    server = scgi.Server(application)
    server.bind(9000, '127.0.0.1')
    server.start()
