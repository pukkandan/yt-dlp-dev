import os

from ..globals import LAZY_EXTRACTORS, extractors

if os.environ.get('YTDLP_NO_LAZY_EXTRACTORS'):
    LAZY_EXTRACTORS.set(False)
else:
    try:
        from .lazy_extractors import _CLASS_LOOKUP
    except ImportError:
        LAZY_EXTRACTORS.set(None)
    else:
        LAZY_EXTRACTORS.set(True)

if not LAZY_EXTRACTORS.get():
    from . import _extractors

    _CLASS_LOOKUP = {  # noqa: F811
        name: value
        # NOTE: inspect.getmembers change the order
        for name, value in vars(_extractors).items()
        if name.endswith('IE') and name != 'GenericIE'
    }
    _CLASS_LOOKUP['GenericIE'] = _extractors.GenericIE

# We want to append to the main lookup
_current = extractors.get()
for name, ie in _CLASS_LOOKUP.items():
    _current.setdefault(name, ie)


def __getattr__(name):
    value = _CLASS_LOOKUP.get(name)
    if not value:
        raise AttributeError(f'module {__name__} has no attribute {name}')
    return value
