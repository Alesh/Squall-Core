import unittest
from time import sleep
from squall.utils import timeout_gen


class TestTimeoutGen(unittest.TestCase):
    """ timeout_gen
    """

    def test_timeout_none(self):
        tg = timeout_gen(None)
        self.assertIsNone(next(tg))
        self.assertIsNone(next(tg))
        self.assertIsNone(next(tg))
        self.assertIsNone(next(tg))
        self.assertIsNone(next(tg))

    def test_timeout_real(self):
        tg = timeout_gen(1.0)
        sleep(0.1)
        self.assertEqual(round(next(tg), 1), 0.9)
        sleep(0.3)
        self.assertEqual(round(next(tg), 1), 0.6)
        sleep(0.5)
        self.assertEqual(round(next(tg), 1), 0.1)
        sleep(0.09)
        self.assertEqual(round(next(tg), 1), 0.0)
        sleep(0.1)
        self.assertEqual(round(next(tg), 1), -1)
        sleep(0.1)
        self.assertEqual(round(next(tg), 1), -1)
        sleep(0.1)
        self.assertEqual(round(next(tg), 1), -1)


if __name__ == '__main__':
    unittest.main()
