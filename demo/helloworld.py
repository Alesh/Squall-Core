from signal import SIGINT
from squall.coroutine import sleep, signal, spawn
import squall.coroutine

async def hello(name, seconds):
    while True:
        await sleep(seconds)
        print("Hello, {}!".format(name))


async def terminator(signum):
    await signal(signum)
    squall.coroutine.stop()
    print("Bye!")

if __name__ == '__main__':

    spawn(terminator, SIGINT)
    spawn(hello, "World", 1.0)
    spawn(hello, "Alesh", 2.5)
    squall.coroutine.start()
