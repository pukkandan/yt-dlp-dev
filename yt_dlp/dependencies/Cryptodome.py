import functools

from ..compat.compat_utils import EnhancedModule, passthrough_module

EnhancedModule(__name__)

try:
    import Cryptodome as _parent
except ImportError:
    try:
        import Crypto as _parent
    except (ImportError, SyntaxError):  # Old Crypto gives SyntaxError in newer Python
        _parent = EnhancedModule('Cryptodome')
        _parent.__bool__ = lambda: False


def __getattr__(name):
    if name in ('Cipher', 'Hash', 'Protocol', 'PublicKey', 'Util', 'Signature', 'IO', 'Math'):
        return passthrough_module(f'{__name__}.{name}', f'{_parent.__name__}.{name}')
    return getattr(_parent, name)


def __bool__():
    return bool(_parent)


@property
@functools.lru_cache(maxsize=None)
def _yt_dlp__identifier():
    if _parent.__name__ == 'Crypto':
        from Crypto.Cipher import AES
        try:
            # In pycrypto, mode defaults to ECB. See:
            # https://www.pycryptodome.org/en/latest/src/vs_pycrypto.html#:~:text=not%20have%20ECB%20as%20default%20mode
            AES.new(b'abcdefghijklmnop')
        except TypeError:
            return 'pycrypto'
    return _parent.__name__
