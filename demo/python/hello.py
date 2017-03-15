""" Sample "Hello world"
"""
from signal import SIGINT

from squall.core import Dispatcher as API


async def hello(api, name, *, timeout=None):
    try:
        while True:
            await api.sleep(timeout)
            print("Hello, {}!".format(name))
    finally:
        print("Bye, {}!".format(name))


async def terminator(api):
    await api.signal(SIGINT)
    print("Got SIGINT!")
    api.stop()


if __name__ == '__main__':
    api = API()
    api.spawn(hello, "World", timeout=1.0)
    api.spawn(hello, "Alesh", timeout=2.5)
    api.spawn(terminator)
    api.start()
