# flake8: noqa: F405
from tempfile import *

from .compat_utils import passthrough_module

passthrough_module(__name__, 'tempfile')
del passthrough_module

try:
    # https://github.com/python/cpython/pull/97015
    NamedTemporaryFile(delete_on_close=False)
except TypeError:
    import functools
    import os
    from tempfile import NamedTemporaryFile as _NamedTemporaryFile

    class _DeleteWrapper:
        __deleted = False

        def __init__(self, file):
            functools.update_wrapper(self, file)
            self.__file = file
            # This may run after file and os have been garbage collected
            self.__delete_file = functools.partial(os.remove, file.name)

        def __getattr__(self, name):
            return getattr(self.__file, name)

        def __iter__(self):
            return iter(self.__file)

        def __enter__(self):
            self.__file.__enter__()
            return self

        def __delete(self):
            if not self.__deleted:
                self.__delete_file()
            self.__deleted = True

        def __del__(self):
            del self.__file
            self.__delete()

        def __exit__(self, *args):
            self.__file.__exit__(*args)
            self.__delete()

    @functools.wraps(_NamedTemporaryFile)
    def NamedTemporaryFile(*args, delete_on_close=True, **kwargs):
        delete = False
        if not delete_on_close:
            if len(args) >= 8:
                delete, args[7] = args[7], False
            else:
                delete = kwargs.get('delete', True)
                kwargs['delete'] = False

        file = _NamedTemporaryFile(*args, **kwargs)
        return _DeleteWrapper(file) if delete else file
