from ..jsinterp.phantomjs import PhantomJSJSI, TempCookieFile
from ..utils import (
    ExtractorError,
    deprecation_warning,
    format_field,
    get_exe_version,
    is_outdated_version,
)

# deprecation_warning('"yt_dlp.extractor.openload" is deprecated')

cookie_to_dict = TempCookieFile.cookie_to_dict


def cookie_jar_to_list(cookie_jar):
    return [cookie_to_dict(cookie) for cookie in cookie_jar]


class PhantomJSwrapper(PhantomJSJSI):
    EXE_NAME = PhantomJSJSI.EXE_NAME
    INSTALL_HINT = 'Please download it from https://phantomjs.org/download.html'

    @staticmethod
    def _version():
        return get_exe_version('phantomjs', version_re=r'([0-9.]+)')

    @property
    def extractor(self):
        return self.ie

    def __init__(self, extractor, required_version=None, timeout=10_000):
        super().__init__(extractor)
        if not self.available:
            raise ExtractorError(f'PhantomJS not found, {self.INSTALL_HINT}', expected=True)

        if required_version:
            version = self._version()
            if is_outdated_version(version, required_version):
                self.logger.warn(
                    'Your copy of PhantomJS is outdated, update it to version '
                    f'{required_version} or newer if you encounter any errors.')

        self.options = {'timeout': timeout // 1000}

    def get(self, url, html=None, video_id=None, note=None, note2='Executing JS on webpage', headers={}, jscode='saveAndExit();'):
        if 'saveAndExit();' not in jscode:
            raise ExtractorError('`saveAndExit();` not found in `jscode`')
        if not html:
            html = self.ie._download_webpage(url, video_id, note=note, headers=headers)
        self.ie.to_screen(f'{format_field(video_id, None, "%s: ")}{note2}')
        return super().run_with_dom(jscode, url, html, timeout=self.options['timeout'])

    def execute(self, jscode, video_id=None, *, note='Executing JS', **kwargs):
        """Execute JS and return stdout"""
        self.ie.to_screen(f'{format_field(video_id, None, "%s: ")}{note}')
        try:
            return super().execute(jscode, **kwargs)
        except Exception as e:
            raise ExtractorError(f'{note} failed: {e}', cause=e)
