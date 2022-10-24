import json

from .common import ExternalJSI, TempCookieFile
from ..utils import classproperty, is_outdated_version


class PhantomJSJSI(ExternalJSI, register=True):
    _BASE_JS = R'''
        phantom.onError = function(msg, trace) {
            var msgStack = ['PHANTOM ERROR: ' + msg];
            if(trace && trace.length) {
            msgStack.push('TRACE:');
            trace.forEach(function(t) {
                msgStack.push(' -> ' + (t.file || t.sourceURL) + ': ' + t.line
                + (t.function ? ' (in function ' + t.function +')' : ''));
            });
            }
            console.error(msgStack.join('\n'));
            phantom.exit(1);
        };
    '''

    _PAGE_TEMPLATE = R'''
        var page = require('webpage').create();
        var fs = require('fs');
        var read = {{ mode: 'r', charset: 'utf-8' }};
        var write = {{ mode: 'w', charset: 'utf-8' }};
        JSON.parse(fs.read({cookie_file}, read)).forEach(function(x) {{
            phantom.addCookie(x);
        }});
        page.settings.resourceTimeout = {timeout};
        page.settings.userAgent = {ua};
        page.onLoadStarted = function() {{
            page.evaluate(function() {{
                delete window._phantom;
                delete window.callPhantom;
            }});
        }};
        var saveAndExit = function() {{
            fs.write({html_file}, page.content, write);
            fs.write({cookie_file}, JSON.stringify(phantom.cookies), write);
            phantom.exit();
        }};
        page.onLoadFinished = function(status) {{
            if(page.url === "") {{
                page.setContent(fs.read({html_file}, read), {url});
            }}
            else {{
                {jscode}
            }}
        }};
        page.open("");
    '''

    @classproperty
    def available(cls):
        return not is_outdated_version(cls.version, '2.0', False)

    def execute(self, jscode, *args, **kwargs):
        if 'phantom.exit();' not in jscode:
            jscode += ';\nphantom.exit();'
        return super().execute(self._BASE_JS + jscode, *args, **kwargs)

    def _make_cmd(self, jsfile):
        return [self.EXE_NAME, '--ssl-protocol=any', jsfile]

    def run_with_dom(self, code, url, html, timeout=10):
        with TempCookieFile(self.ydl.cookiejar, url) as cookiejar, self.new_temp_file() as html_file:
            html_file.write(html)
            html_file.close()

            stdout = self.execute(self._PAGE_TEMPLATE.format_map({
                'url': json.dumps(url),
                'ua': json.dumps(self.ydl.params['http_headers']['User-Agent']),
                'jscode': code,
                'cookie_file': json.dumps(cookiejar.file.name),
                'html_file': json.dumps(html_file.name),
                'timeout': timeout * 1000,
            }), timeout=timeout)

            with open(html_file.name, encoding='utf-8') as f:
                html = f.read()
            return html, stdout
