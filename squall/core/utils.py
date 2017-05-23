""" Core utils
"""
import os
import errno
import socket
from time import time


class timeout_gen(object):
    """ Timeout generator
    """

    def __init__(self, initial_timeout):
        assert (isinstance(initial_timeout, (int, float)) or
                initial_timeout is None)
        self.deadline = None
        if initial_timeout is not None:
            self.deadline = time() + initial_timeout

    def __iter__(self):
        return self

    def __next__(self):
        if self.deadline is not None:
            value = self.deadline - time()
            return value if value > 0 else -1


class Addr(tuple):
    def __str__(self):
        """ Returns a pretty string representation of a given IP address.
        """
        if len(self) > 2:
            return "[{}]:{}".format(*self[:2])
        else:
            return "{}:{}".format(*self)
