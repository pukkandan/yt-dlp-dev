from ..utils import remove_terminal_sequences
from .common import ExternalJSI


class DenoJSI(ExternalJSI, register=True):
    _VERSION_OPT = '-V'

    _PAGE_TEMPLATE = R'''
        import puppeteer from "https://deno.land/x/puppeteer/mod.ts";
        const browser = await puppeteer.launch({{
            headless: !{debug},
            args: ["--disable-web-security"],  // Bypass CORS so we can set URL
        }})
        const page = await browser.newPage();

        async function saveAndExit(code) {{
            Deno.writeTextFileSync({cookie_file}, JSON.stringify(page.cookies()));
            Deno.writeTextFileSync({html_file}, await page.content());
            browser.close();
            Deno.exit(code);
        }}
        window.setTimeout((async () => await saveAndExit(1)), {timeout});
        page.on("close", (async () => await saveAndExit(1)));
        page.resourceTimeout = {timeout};

        await page.setRequestInterception(true);
        page.on("request", request => request.abort());  // block all requests

        page.setCookie(...JSON.parse(await Deno.readTextFile({cookie_file})));
        page.setUserAgent({ua});
        await page.evaluate("window.history.replaceState('', '', " + JSON.stringify({url}) + ")");
        await page.setContent(await Deno.readTextFile({html_file}));

        {jscode}
    '''

    def _make_cmd(self, jsfile, with_dom=False):
        yield from (self.EXE_NAME, 'run')
        if with_dom:
            yield '--allow-all'
        yield jsfile

    def execute(self, jscode, *args, **kwargs):
        try:
            return super().execute(jscode, *args, **kwargs)
        except self.Exception as e:
            if remove_terminal_sequences(e.msg).startswith('error: Uncaught Error: Could not find browser'):
                raise NotImplementedError('Run: deno run -A https://deno.land/x/puppeteer@16.2.0/install.ts"')
            raise
