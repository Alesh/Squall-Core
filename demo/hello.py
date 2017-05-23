""" Sample "Hello world"
"""
from signal import SIGINT
from squall.core import Dispatcher


async def hello(disp, name, *, timeout=None):
    try:
        while True:
            await disp.sleep(timeout)
            print("Hello, {}!".format(name))
    finally:
        print("Bye, {}!".format(name))


async def terminator(disp):
    await disp.signal(SIGINT)
    print("Got SIGINT!")
    disp.stop()


if __name__ == '__main__':
    disp = Dispatcher()
    disp.submit(hello, "World", timeout=1.0)
    disp.submit(hello, "Alesh", timeout=2.5)
    disp.submit(terminator)
    disp.start()
