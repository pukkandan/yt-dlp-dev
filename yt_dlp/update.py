import atexit
import hashlib
import json
import os
import platform
import subprocess
import sys
from zipimport import zipimporter

from .compat import functools  # isort: split
from .compat import compat_realpath
from .utils import Popen, traverse_obj, version_tuple
from .version import __version__


RELEASE_JSON_URL = 'https://api.github.com/repos/yt-dlp/yt-dlp/releases/latest'


@functools.cache
def _get_variant_and_executable_path():
    """@returns (variant, executable_path)"""
    if hasattr(sys, 'frozen'):
        path = sys.executable
        if not hasattr(sys, '_MEIPASS'):
            return 'py2exe', path
        if sys._MEIPASS == os.path.dirname(path):
            return f'{sys.platform}_dir', path
        return f'{sys.platform}_exe', path

    path = os.path.dirname(__file__)
    if isinstance(__loader__, zipimporter):
        return 'zip', os.path.join(path, '..')
    elif os.path.basename(sys.argv[0]) == '__main__.py':
        return 'source', path
    return 'unknown', path


def detect_variant():
    return _get_variant_and_executable_path()[0]


_FILE_SUFFIXES = {
    'zip': '',
    'py2exe': '_min.exe',
    'win32_exe': '.exe',
    'darwin_exe': '_macos',
}

_NON_UPDATEABLE_REASONS = {
    **{variant: None for variant in _FILE_SUFFIXES},  # Updatable
    **{variant: f'Auto-update is not supported for unpackaged {name} executable; Re-download the latest release'
       for variant, name in {'win32_dir': 'Windows', 'darwin_dir': 'MacOS'}.items()},
    'source': 'You cannot update when running from source code; Use git to pull the latest changes',
    'unknown': 'It looks like you installed yt-dlp with a package manager, pip or setup.py; Use that to update',
    'other': 'It looks like you are using an unofficial build of yt-dlp; Build the executable again',
}


def is_non_updateable():
    return _NON_UPDATEABLE_REASONS.get(detect_variant(), _NON_UPDATEABLE_REASONS['other'])


def _sha256_file(path):
    h = hashlib.sha256()
    mv = memoryview(bytearray(128 * 1024))
    with open(os.path.realpath(path), 'rb', buffering=0) as f:
        for n in iter(lambda: f.readinto(mv), 0):
            h.update(mv[:n])
    return h.hexdigest()


class Updater:
    REPO = 'yt-dlp/yt-dlp'
    API_URL = f'https://api.github.com/repos/{REPO}/releases/latest'
    _version_cache, _hash_data = None, None

    def __init__(self, ydl):
        self.ydl = ydl

    @property
    def current_version(self):
        return __version__

    def _new_version_info(self):
        if not self._version_cache:
            self.ydl.write_debug(f'Fetching release info: {self.API_URL}')
            self._version_cache = json.loads(self.ydl.urlopen(self.API_URL).read().decode())
        return self._version_cache


    @property
    def new_version(self):
        return self._new_version_info()['tag_name']

    def has_update(self):
        return version_tuple(self.current_version) < version_tuple(self.new_version)

    @functools.cached_property
    def filename(self):
        return compat_realpath(_get_variant_and_executable_path()[1])

    @functools.cached_property
    def variant(self):
        return detect_variant()

    @functools.cached_property
    def release_name(self):
        label = _FILE_SUFFIXES[self.variant]
        if label and platform.architecture()[0][:2] == '32':
            label = f'_x86{label}'
        return f'yt-dlp{label}'

    def download(self, name=None):
        name = name or self.release_name
        url = traverse_obj(self._new_version_info(), (
            'assets', lambda _, v: v['name'] == name, 'browser_download_url'), get_all=False)
        if not url:
            raise Exception('Unable to find download URL')
        self.ydl.write_debug(f'Downloading {name} from {url}')
        return self.ydl.urlopen(url).read()

    def get_release_hash(self):
        if not self._hash_data:
            hash_data = self.download('SHA2-256SUMS')
            self._hash_data = dict(ln.split()[::-1] for ln in hash_data.decode().splitlines())
        return self._hash_data[self.release_name]

    def _report_error(self, msg, expected=False):
        self.ydl.report_error(msg, tb=False if expected else None)

    def _report_unable(self, action, expected=False):
        self._report_error(f'Unable to {action}', expected)

    def _report_permission_error(self, file):
        self._report_unable(f'write to {file}; Try running as administrator', True)

    def _report_network_error(self, action, delim=';'):
        self._report_unable(f'{action}{delim} Visit  https://github.com/{self.REPO}/releases/latest', True)

    def update(self):
        try:
            self.ydl.to_screen(
                f'Latest version: {self.new_version}, Current version: {self.current_version}')
        except Exception:
            return self._report_network_error('obtain version info', delim='; Please try again later or')

        if not self.has_update():
            return self.ydl.to_screen(f'yt-dlp is up to date ({__version__})')

        err = is_non_updateable()
        if err:
            return self._report_error(err, True)

        self.ydl.to_screen(f'Current Build Hash {_sha256_file(self.filename)}')
        self.ydl.to_screen(f'Updating to version {self.new_version} ...')

        directory = os.path.dirname(self.filename)
        if not os.access(self.filename, os.W_OK):
            return self._report_permission_error(self.filename)
        elif not os.access(directory, os.W_OK):
            return self._report_permission_error(directory)

        new_filename, old_filename = f'{self.filename}.new', f'{self.filename}.old'
        if self.variant == 'zip':  # Can be replaced in-place
            new_filename, old_filename = self.filename, None

        try:
            if os.path.exists(old_filename or ''):
                os.remove(old_filename)
        except OSError:
            return self._report_unable('remove the old version')

        try:
            newcontent = self.download()
        except OSError:
            return self._report_network_error('download latest version')
        except Exception:
            return self._report_network_error('fetch updates')

        try:
            expected_hash = self.get_release_hash()
        except Exception:
            self.ydl.report_warning('no hash information found for the release')
        else:
            if hashlib.sha256(newcontent).hexdigest() != expected_hash:
                return self._report_network_error('verify the new executable')

        try:
            with open(new_filename, 'wb') as outf:
                outf.write(newcontent)
        except OSError:
            return self._report_permission_error(new_filename)

        try:
            if old_filename:
                os.rename(self.filename, old_filename)
        except OSError:
            return self._report_unable('move current version')
        try:
            if old_filename:
                os.rename(new_filename, self.filename)
        except OSError:
            self._report_unable('overwrite current version')
            return os.rename(old_filename, self.filename)

        if self.variant not in ('win32_exe', 'py2exe'):
            if old_filename:
                os.remove(old_filename)
        else:
            # Run in the background after yt-dlp exits
            atexit.register(Popen, f'ping 127.0.0.1 -n 5 -w 1000 & del /F "{old_filename}"',
                            shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        self.ydl.to_screen(f'Updated yt-dlp to version {self.new_version}')
        return True


def run_update(ydl):
    """Update the program file with the latest version from the repository
    @returns    Whether whether there was a successfull update (No update = False)
    """
    return Updater(ydl).update()


# Deprecated
def update_self(to_screen, verbose, opener):
    import traceback
    from .utils import write_string

    write_string(
        'DeprecationWarning: "yt_dlp.update.update_self" is deprecated and may be removed in a future version. '
        'Use "yt_dlp.update.run_update(ydl)" instead\n')

    printfn = to_screen

    class FakeYDL():
        to_screen = printfn

        def report_warning(self, msg, *args, **kwargs):
            return printfn(f'WARNING: {msg}', *args, **kwargs)

        def report_error(self, msg, tb=None):
            printfn(f'ERROR: {msg}')
            if not verbose:
                return
            if tb is None:
                # Copied from YoutubeDL.trouble
                if sys.exc_info()[0]:
                    tb = ''
                    if hasattr(sys.exc_info()[1], 'exc_info') and sys.exc_info()[1].exc_info[0]:
                        tb += ''.join(traceback.format_exception(*sys.exc_info()[1].exc_info))
                    tb += traceback.format_exc()
                else:
                    tb_data = traceback.format_list(traceback.extract_stack())
                    tb = ''.join(tb_data)
            if tb:
                printfn(tb)

        def write_debug(self, msg, *args, **kwargs):
            printfn(f'[debug] {msg}', *args, **kwargs)

        def urlopen(self, url):
            return opener.open(url)

    return run_update(FakeYDL())
