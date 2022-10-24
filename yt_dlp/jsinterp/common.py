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


class JSI:
    Result = collections.namedtuple(
        'JSI_Result', ('return_value', 'html', 'stdout'),
        defaults=(None, '<!DOCTYPE html>', ''))

    def __init__(self, ydl):
        self.ydl = ydl
        self.logger = YDLLogger(self)

    def extract_function_code(self, name, full_code):
        """
        Extracts the code of function with name `name` from `full_code`
        @returns (function_code, arg_names)
        """
        raise NotImplementedError('Must be implemented by subclasses')

    def build_function(self, code, argnames, *, full_code=None, timeout=10):
        """
        Builds a callable function from `code` and `argnames`
        @returns  A callable function(args)
        """
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
        """
        Runs given code in the interpreter. If `html` or `url` is given, the code is executed with DOM.
        @returns  JSI.Result
        """
        assert func_code or full_code or html, 'Nothing to do without code and html'
        if html and not url:
            url = 'about:invalid'
        html = html or JSI.Result._field_defaults['html']
        if not url:
            return JSI.Result(
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
        return JSI.Result(ret, html, stdout)

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


class ExternalJSI(JSI):
    _VERSION_OPT = '--version'
    _VERSION_RE = r'([\d.]+)'

    @classproperty
    def EXE_NAME(cls):
        return cls.JSI_NAME

    # TODO: Support custom CLI args
    def _make_cmd(self, jsfile):
        raise NotImplementedError('Must be implemented by subclasses')

    @classproperty
    def version(cls):
        return get_exe_version(cls.EXE_NAME, args=[cls._VERSION_OPT], version_re=cls._VERSION_RE)

    # TODO: Support custom location
    @classproperty
    def available(cls):
        return bool(cls.version)

    @staticmethod
    def new_temp_file():
        return tempfile.NamedTemporaryFile(
            prefix='yt_dlp_', mode='w', encoding='utf-8', delete_on_close=False)

    def execute(self, jscode, *, timeout=10):
        """Execute JS and return stdout"""
        with self.new_temp_file() as tmp:
            tmp.write(jscode)
            tmp.close()

            cmd = self._make_cmd(tmp.name)
            self.logger.debug(f'command line: {shell_quote(cmd)}')
            stdout, stderr, returncode = Popen.run(
                cmd, timeout=timeout, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        if returncode:
            raise Exception(f'{self.JSI_NAME} failed with returncode {returncode}:\n{stderr.strip()}')
        return stdout

    def build_function(self, code, argnames, *, timeout=10, full_code=None):
        return lambda args: json.loads(self.execute(
            self._function_code(code, dict(zip(argnames, args))), timeout=timeout).strip())


class YDLLogger:  # TODO: Generalize with cookies.py
    def __init__(self, jsi):
        self.jsi = jsi

    def info(self, message, **kwargs):
        self.jsi.ydl.to_screen(f'[JSI:{self.jsi.JSI_NAME}] {message}', **kwargs)

    def debug(self, message, **kwargs):
        self.jsi.ydl.write_debug(f'[JSI:{self.jsi.JSI_NAME}] {message}', **kwargs)

    def warning(self, message, **kwargs):
        self.jsi.ydl.report_warning(message, **kwargs)

    def error(self, message, **kwargs):
        self.jsi.ydl.report_error(message, **kwargs)


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


class TempCookieFile:
    def __init__(self, cookiejar, url):
        self.cookiejar = cookiejar
        self.url = url
        self.file = ExternalJSI.new_temp_file()

    def __enter__(self):
        self.file.__enter__()
        self.file.write(json.dumps([self.cookie_to_dict(c, self.url) for c in self.cookiejar]))
        self.file.close()
        return self

    def __exit__(self, *args):
        with open(self.file.name, encoding='utf-8') as f:
            for cookie in json.loads(f.read()):
                self.cookiejar.set_cookie(self.dict_to_cookie(cookie))
        self.file.__exit__(*args)

    @staticmethod
    def cookie_to_dict(cookie, url=None):
        domain = cookie.domain if cookie.domain_specified else urllib.parse.urlparse(url).netloc if url else None
        cookie_dict = filter_dict({
            'name': cookie.name,
            'value': cookie.value,
            'domain': domain,
            'path': cookie.path if cookie.path_specified else '/',
            'port': cookie.port if cookie.port_specified else None,
            'expires': cookie.expires,
            'secure': cookie.secure,
            'discard': cookie.discard,
        })
        with contextlib.suppress(TypeError):
            if (cookie.has_nonstandard_attr('httpOnly')
                    or cookie.has_nonstandard_attr('httponly')
                    or cookie.has_nonstandard_attr('HttpOnly')):
                cookie_dict['httponly'] = True
        return cookie_dict

    @staticmethod
    def dict_to_cookie(cookie):
        return http.cookiejar.Cookie(
            version=0,
            name=cookie['name'],
            value=cookie['value'],
            domain=cookie['domain'],
            domain_specified=bool(cookie['domain']),
            domain_initial_dot=cookie['domain'].startswith('.'),
            path=cookie.get('path', '/'),
            path_specified=True,
            port=cookie.get('port'),
            port_specified=bool(cookie.get('port')),
            expires=cookie.get('expires'),
            secure=cookie.get('secure'),
            discard=cookie.get('discard'),
            comment=None,
            comment_url=None,
            rest={'httpOnly': None} if cookie.get('httponly') else {},
        )
