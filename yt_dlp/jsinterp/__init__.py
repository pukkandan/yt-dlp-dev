import functools
import traceback

from . import native, phantomjs  # noqa: F401
from .common import JS_INTERPRETERS, JSI
from ..utils import cached_method


# TODO: update docstrings
class JSDispatcher:
    def __init__(self, ydl, interpreters):
        self.ydl = ydl
        # TODO: Make lazy
        self._interpreters = {jsi.JSI_NAME: jsi for jsi in interpreters if jsi.available}
        for jsi in interpreters:
            assert isinstance(jsi.available, bool), f'{jsi.__name__}.available must be a classproperty'

    @cached_method
    def _instance(self, name):
        return self._interpreters[name](self.ydl)

    def dispatch(self, protocol):
        func_name = protocol.__name__
        assert protocol.__qualname__ == f'JSI.{func_name}', 'Must be a method of JSI'

        def wrapper(*args, **kwargs):
            for jsi in map(self._instance, self._interpreters.keys()):
                try:
                    yield jsi, getattr(jsi, func_name)(*args, **kwargs), None
                except NotImplementedError:
                    continue
                except Exception as e:
                    jsi.logger.info(f'Unable to {func_name}: {e}')
                    jsi.logger.debug(''.join(traceback.format_exception(e)).strip(), only_once=True)
                    yield jsi, None, e
        return wrapper

    def get_first(self, generator, validator=lambda *args: args):
        last_error = None
        for jsi, ret, err in generator:
            result = validator(jsi, ret, err)
            if not result:
                continue
            _, ret, err = result
            if not err:
                return ret
            last_error, err.__cause__ = err, last_error
        if last_error:
            raise last_error
        raise NotImplementedError('No interpreters support this operation')

    def _dispatched(protocol):
        def wrapper(self, *args, **kwargs):
            return self.dispatch(protocol)(*args, **kwargs)

        functools.update_wrapper(wrapper, protocol)
        wrapper.__qualname__ = f'JSDispatcher.{protocol.__name__}'
        doc = protocol.__doc__.replace("\n", "\n    ")
        wrapper.__doc__ = f'''
        @returns DispatchedFunction for {protocol.__qualname__}

        Documentation of {protocol.__qualname__}:
            {doc}
        '''

        return wrapper

    extract_function_code = _dispatched(JSI.extract_function_code)
    run = _dispatched(JSI.run)

    @cached_method
    def evaluate_function(self, name, code, args):
        """
        Evaluates a pure function
        @returns DispatchedFunction that gives the result of the function
        """
        func_code, argnames = self.get_first(self.extract_function_code(name, code))
        for jsi, ret, err in self.run(func_code, dict(zip(argnames, args)), full_code=code):
            if err:
                yield jsi, None, err
            yield jsi, ret.return_value, None


__all__ = ['JSDispatcher', 'JSI', 'JS_INTERPRETERS']


from ..compat.compat_utils import passthrough_module
from ..utils import deprecation_warning

passthrough_module(__name__, '._legacy', callback=lambda attr: deprecation_warning(
    f'{__name__}.{attr} is deprecated', stacklevel=3))

del passthrough_module
