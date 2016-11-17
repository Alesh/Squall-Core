from squall.coroutine import start, spawn, sleep


async def hello(name, timeout):
    try:
        while True:
            await sleep(timeout)
            print("Hello, {}!".format(name))
    finally:
        print("Bye, {}!".format(name))


if __name__ == '__main__':

    spawn(hello, "Alesh", 1.0)
    spawn(hello, "World", 2.5)
    start()
