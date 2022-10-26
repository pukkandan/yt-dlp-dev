import json
import re

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

        function saveAndExit() {{
            fs.write({html_file}, page.content, write);
            fs.write({cookie_file}, JSON.stringify(phantom.cookies), write);
            phantom.exit();
        }};

        page.settings.resourceTimeout = {timeout};
        page.onLoadStarted = function() {{
            page.evaluate(function() {{
                delete window._phantom;
                delete window.callPhantom;
            }});
        }};

        JSON.parse(fs.read({cookie_file}, read)).forEach(function(x) {{
            phantom.addCookie(x);
        }});
        page.settings.userAgent = {ua};
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
        jscode = re.sub(r'\b(async|await)\s+', '', jscode)
        if 'phantom.exit();' not in jscode:
            jscode += ';\nphantom.exit();'
        return super().execute(self._BASE_JS + jscode, *args, **kwargs)

    def _make_cmd(self, jsfile, with_dom=False):
        return [self.EXE_NAME, '--ssl-protocol=any', jsfile]
