import collections
import contextlib
import http.cookiejar
import json
import subprocess
import urllib.parse

from ..compat import tempfile
from ..utils import (
    Popen,
    cached_method,
    classproperty,
    filter_dict,
    get_exe_version,
    join_nonempty,
    shell_quote,
)

JS_INTERPRETERS = []

# XXX: Bad name
Result = collections.namedtuple('Result', ('return_value', 'html', 'stdout'),
                                defaults=(None, '<!DOCTYPE html>', ''))


class JSI:
    def __init__(self, ie):
        self.ie = ie
        self.logger = YDLLogger(self)

    def extract_function_code(self, name, full_code):
        """@returns (function_code, arg_names)"""
        raise NotImplementedError('Must be implemented by subclasses')

    def build_function(self, code, argnames, *, full_code=None, timeout=10):
        """@returns  A callable function(args, kwargs={})"""
        raise NotImplementedError('Must be implemented by subclasses')

    def run_with_dom(self, code, url, html, *, timeout=10):
        """
        `html` is loaded with location = `url` and `code` is executed in `page.onLoadFinished`.
        `saveAndExit();` exits the interpreter, and is mandatory in `code`.

        @returns  (final html of the page, stdout of the executed code)

        It is possible to wait for some element on the webpage, e.g.
            var check = function() {
              var elementFound = page.evaluate(function() {
                return document.querySelector('#b.done') !== null;
              });
              if(elementFound)
                saveAndExit();
              else
                window.setTimeout(check, 500);
            }
            page.evaluate(function(){
              document.querySelector('#a').click();
            });
            check();
        """
        raise NotImplementedError('Must be implemented by subclasses')

    @cached_method
    def __run_function(self, code, args, full_code, timeout):
        return self.build_function(
            code, args.keys(), full_code=full_code, timeout=timeout)(args.values())

    @staticmethod
    def _function_code(body, args, use_page=False):
        arg_string = json.dumps(tuple(args.values()))[1:-1]
        body = f'function({", ".join(args.keys())}) {{\n{body}\n}}'
        code = f'page.evaluate({join_nonempty(body, arg_string, delim=", ")})' if use_page else f'{body}({arg_string})'
        return f'console.log(JSON.stringify({code}));'

    def run(self, func_code=None, func_args={}, *, full_code=None, html=None, url=None, timeout=10):
        """@returns  Result(return_value, html, stdout)"""
        assert func_code or full_code or html, 'Nothing to do without code and html'
        if html and not url:
            url = 'about:invalid'
        html = html or Result._field_defaults['html']
        if not url:
            return Result(
                return_value=self.__run_function(func_code, func_args, full_code, timeout))

        if func_code:
            assert not full_code, 'Cannot specify both func_code and full_code'
            full_code = self._function_code(func_code, func_args, True) + '\nsaveAndExit();'
        else:
            full_code = full_code or 'saveAndExit();'
            assert 'saveAndExit();' in full_code, 'saveAndExit(); must be present in full_code'
            assert not func_args, 'Cannot specify func_args without func_code'

        html, stdout = self.run_with_dom(full_code, url, html, timeout=timeout)
        ret = json.loads(stdout.strip()) if func_code else None
        return Result(ret, html, stdout)

    @classproperty
    def JSI_NAME(cls):
        return cls.__name__[:-3].lower()

    @classproperty
    def available(cls):
        raise NotImplementedError('Must be implemented by subclasses')

    @classmethod
    def __init_subclass__(cls, *, register=False, **kwargs):
        if register:
            JS_INTERPRETERS.append(cls)
        return super().__init_subclass__(**kwargs)


class YDLLogger:  # TODO: Generalize with cookies.py
    def __init__(self, jsi):
        self.jsi = jsi

    @property
    def ydl(self):
        return self.jsi.ie._downloader

    def info(self, message, **kwargs):
        self.ydl.to_screen(f'[JSI:{self.jsi.JSI_NAME}] {message}', **kwargs)

    def debug(self, message, **kwargs):
        self.ydl.write_debug(f'[JSI:{self.jsi.JSI_NAME}] {message}', **kwargs)

    def warning(self, message, **kwargs):
        self.ydl.report_warning(message, **kwargs)

    def error(self, message, **kwargs):
        self.ydl.report_error(message, **kwargs)


class NestedScope(collections.ChainMap):
    mutable = True

    def __setitem__(self, key, value):
        if not self.mutable:
            raise ValueError('Cannot set value to immutable namespace')
        for scope in self.maps:
            if key in scope:
                scope[key] = value
                return
        self.maps[0][key] = value

    def __delitem__(self, key):
        raise NotImplementedError('Deleting is not supported')
