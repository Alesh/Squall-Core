import sys
import distutils.dir_util
from setuptools import setup, Extension

if sys.version_info[:2] < (3, 5):
    raise NotImplementedError("Required python version 3.5 or greater")

settings = {
    'name': 'squall',
    'version': '0.2.dev4',
    'namespace_packages': ['squall'],
    'package_dir': {'': 'python'},
    'py_modules': ['squall.abc', 'squall.coroutine',
                   'squall.network', 'squall.utils'],
    'author': "Alexey Poryadin",
    'author_email': "alexey.poryadin@gmail.com",
    'description': "The Squall is a framework which implements "
                   "the cooperative multitasking based on event-driven "
                   "switching async/await coroutines.",
    'tests_require': ['nose', 'testfixtures'],
    'test_suite': 'nose.collector',
    'install_requires': []
}

settings['ext_modules'] = [
    Extension('_squall', **{
              'extra_compile_args': ['-std=c++11'],
              'include_dirs': ['./'],
              'sources': ['python/_squall/module.cxx'],
              'libraries': ['ev', 'boost_python-py35']})
]

try:
    setup(**settings)
except:
    print("WARNING! Cannot build C extension "
          "will be used failback module.\n\n")
    distutils.dir_util.remove_tree('./build')
    settings.pop('ext_modules')
    settings['py_modules'].append('_squall')
    settings['install_requires'].append('tornado >= 4.3')
    setup(**settings)
