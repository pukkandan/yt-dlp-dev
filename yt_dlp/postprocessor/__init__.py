from .common import PostProcessor
from .ffmpeg import FFmpegPostProcessor
from .postprocessors import *  # noqa: 403
from ..globals import plugin_pps, postprocessors
from ..plugins import PACKAGE_NAME
from ..utils import deprecation_warning


def __getattr__(name):
    lookup = plugin_pps.get()
    if name in lookup:
        deprecation_warning(
            f'Importing a plugin Post-Processor from {__name__} is deprecated. '
            f'Please import {PACKAGE_NAME}.postprocessor.{name} instead.')
        return lookup[name]

    raise AttributeError(f'module {__name__!r} has no attribute {name!r}')


def get_postprocessor(key):
    return postprocessors.get()[key + 'PP']


_default_pps = {name: value for name, value in globals().items() if name.endswith('PP')}
postprocessors.set(_default_pps)

__all__ = [*_default_pps.keys(), 'PostProcessor', 'FFmpegPostProcessor']
