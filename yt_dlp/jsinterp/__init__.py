import functools
import traceback

from . import native, phantomjs  # noqa: F401
from .common import JS_INTERPRETERS, JSI
from ..utils import cached_method

_PASSTHROUGH = lambda *args: args


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

    def _dispatched(protocol):
        func_name = protocol.__name__
        assert protocol.__qualname__ == f'JSI.{func_name}', 'Must be a method of JSI'

        @functools.wraps(protocol)
        def wrapper(self, *args, validate=_PASSTHROUGH, **kwargs):
            last_error = None
            for jsi in map(self._instance, self._interpreters.keys()):
                ret, err = None, None
                try:
                    ret = getattr(jsi, func_name)(*args, **kwargs)
                except NotImplementedError:
                    continue
                except Exception as e:
                    jsi.logger.info(f'Unable to {func_name}: {e}')
                    jsi.logger.debug(''.join(traceback.format_exception(e)).strip(), only_once=True)
                    err = e

                result = validate(jsi, ret, err)
                if not result:
                    continue
                _, ret, err = result
                if not err:
                    return ret
                last_error, err.__cause__ = err, last_error
            if last_error:
                raise last_error
            raise NotImplementedError('No interpreters support this operation')

        wrapper.__qualname__ = f'JSDispatcher.{protocol.__name__}'
        return wrapper

    extract_function_code = _dispatched(JSI.extract_function_code)
    run = _dispatched(JSI.run)

    @cached_method
    def evaluate_function(self, name, code, args, *, validate=_PASSTHROUGH):
        """Evaluates a pure function and returns its result"""
        func_code, argnames = self.extract_function_code(name, code)
        return self.run(
            func_code, dict(zip(argnames, args)), full_code=code, validate=validate).return_value


__all__ = ['JSDispatcher', 'JSI', 'JS_INTERPRETERS']


from ..compat.compat_utils import passthrough_module
from ..utils import deprecation_warning

passthrough_module(__name__, '._legacy', callback=lambda attr: deprecation_warning(
    f'{__name__}.{attr} is deprecated', stacklevel=3))

del passthrough_module
