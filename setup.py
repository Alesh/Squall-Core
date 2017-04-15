import sys
import os.path
from setuptools import setup, Extension

try:
    from Cython.Build import cythonize
except ImportError:
    cythonize = None

if sys.version_info[:2] < (3, 5):
    raise NotImplementedError("Required python version 3.5 or greater")

settings = {
    'name': 'Squall-Core',
    'version': '0.1.dev31',
    'author': 'Alexey Poryadin',
    'author_email': 'alexey.poryadin@gmail.com',
    'description': "The Squall this is set of modules which implements"
                   "the cooperative multitasking based on event-driven"
                   "switching async/await coroutines.",
    'namespace_packages': ['squall'],
    'packages': ['squall.core'],
    'py_modules': ['squall.core_fallback'],
    'setup_requires': ['pytest-runner'],
    'tests_require': ['pytest', 'pytest_catchlog'],
    'zip_safe': False
}

try:
    if cythonize is not None:
        include_dirs = [
            os.path.join(os.path.dirname(__file__), '..', 'CXX', 'include')
        ]

        print('include_dirs', include_dirs)

        settings['ext_modules'] = cythonize([
            Extension('squall.core_cython',
                      ['squall/core_cython/core_cython.pyx'],
                      include_dirs=include_dirs,
                      language="c++", libraries=['ev'],
                      extra_compile_args=["-std=c++11"])])
    setup(**settings)
except Exception:
    settings.pop('ext_modules', None)
    setup(**settings)
