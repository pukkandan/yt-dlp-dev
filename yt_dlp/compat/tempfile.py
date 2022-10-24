# flake8: noqa: F405
from tempfile import *
import inspect

from .compat_utils import passthrough_module

passthrough_module(__name__, 'tempfile')
del passthrough_module

if 'delete_on_close' not in inspect.signature(NamedTemporaryFile).parameters:
    # https://github.com/python/cpython/pull/97015
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
            bound_args = inspect.signature(_NamedTemporaryFile).bind(*args, **kwargs)
            bound_args.apply_defaults()
            args, kwargs = [], bound_args.arguments
            delete, kwargs['delete'] = kwargs['delete'], False

        file = _NamedTemporaryFile(*args, **kwargs)
        return _DeleteWrapper(file) if delete else file
