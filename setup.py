import sys
from setuptools import setup

if sys.version_info[:2] < (3, 5):
    raise NotImplementedError("Required python version 3.5 or greater")

settings = {
    'name': 'squall',
    'version': '0.2.dev3',
    'py_modules': ['_squall', 'squall.abc',
                   'squall.coroutine', 'squall.network'],
    'author': "Alexey Poryadin",
    'author_email': "alexey.poryadin@gmail.com",
    'description': "The Squall is a framework which implements "
                   "the cooperative multitasking based on event-driven "
                   "switching async/await coroutines.",
}

setup(**settings)
