from bottle import Bottle, run, template

app = Bottle()


@app.route('/hello/<name>')
def index(name):
    return template('<b>Hello {{name}}</b>!', name=name)


if __name__ == '__main__':

    run(app, host='localhost', port=8090, quiet=True, server='waitress')

# siege -c 1000 -b -r 100 http://127.0.0.1:8090/hello
# python demo/wsgi/botapp/app.py
# Transactions:              99610 hits
# Availability:              99.61 %
# Elapsed time:              78.76 secs
# Data transferred:           1.14 MB
# Response time:              0.48 secs
# Transaction rate:        1264.73 trans/sec
# Throughput:             0.01 MB/sec
# Concurrency:              602.57
# Successful transactions:       99610
# Failed transactions:             390
# Longest transaction:           32.89
# Shortest transaction:           0.00
