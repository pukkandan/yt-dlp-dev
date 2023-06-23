import os

from ..globals import LAZY_EXTRACTORS
from ..plugins import load_plugins

# NB: Must be before other imports so that plugins can be correctly injected
_PLUGIN_CLASSES = load_plugins('extractor', 'IE')

if os.environ.get('YTDLP_NO_LAZY_EXTRACTORS'):
    LAZY_EXTRACTORS.set(False)
else:
    try:
        from .lazy_extractors import *  # noqa: F403
        from .lazy_extractors import _ALL_CLASSES
    except ImportError:
        LAZY_EXTRACTORS.set(None)
    else:
        LAZY_EXTRACTORS.set(True)

if not LAZY_EXTRACTORS.get():
    from ._extractors import *  # noqa: F403
    _ALL_CLASSES = [  # noqa: F811
        klass
        for name, klass in globals().items()
        if name.endswith('IE') and name != 'GenericIE'
    ]
    _ALL_CLASSES.append(GenericIE)  # noqa: F405

globals().update(_PLUGIN_CLASSES)
_ALL_CLASSES[:0] = _PLUGIN_CLASSES.values()

from .common import _PLUGIN_OVERRIDES  # noqa: F401
