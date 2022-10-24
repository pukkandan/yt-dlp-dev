import functools
import traceback

from . import native, phantomjs  # noqa: F401
from .common import JS_INTERPRETERS, JSI
from ..utils import DispatchedFunction, cached_method


class JSDispatcher:
    def __init__(self, ie, interpreters):
        self.ie = ie
        # TODO: Make lazy
        self._interpreters = {jsi.JSI_NAME: jsi for jsi in interpreters if jsi.available}
        for jsi in interpreters:
            assert isinstance(jsi.available, bool), f'{jsi.__name__}.available must be a classproperty'

    @cached_method
    def _instance(self, name):
        return self._interpreters[name](self.ie)

    @staticmethod
    def _validate_result(func_name, result):
        logger = result.objects[-1].logger
        if result.error:
            logger.info(f'Unable to {func_name}: {result.error}')
            logger.debug(''.join(traceback.format_exception(result.error)).strip(), only_once=True)
        return result

    def dispatch(self, protocol):
        assert protocol.__qualname__ == f'JSI.{protocol.__name__}', 'Must be a method of JSI'
        return DispatchedFunction(map(self._instance, self._interpreters), protocol,
                                  validators=[functools.partial(self._validate_result, protocol.__name__)])

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
        func = self.dispatch(JSI.extract_function_code).chain(
            JSI.run, lambda ret: ((ret[0], dict(zip(ret[1], args))), {'full_code': code}))
        return func(name, code).transform(lambda x: x.return_value)


__all__ = ['JSDispatcher', 'JSI', 'JS_INTERPRETERS']


from ..compat.compat_utils import passthrough_module
from ..utils import deprecation_warning

passthrough_module(__name__, '._legacy', callback=lambda attr: deprecation_warning(
    f'{__name__}.{attr} is deprecated', stacklevel=3))

del passthrough_module
