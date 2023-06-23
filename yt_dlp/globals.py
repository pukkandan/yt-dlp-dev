from collections import defaultdict
from contextvars import ContextVar

IN_CLI = ContextVar('IN_CLI', default=False)

# `True`=enabled, `None`=disabled, `False`=force disabled
LAZY_EXTRACTORS = ContextVar('LAZY_EXTRACTORS')

ffmpeg_location = ContextVar('ffmpeg_location', default=None)

# "..." indicates default paths
plugin_dirs = ContextVar('plugin_dirs', default=(..., ))

postprocessors = ContextVar('postprocessors', default={})
extractors = ContextVar('extractors', default={})

plugin_ies = ContextVar('plugin_ies', default={})
plugin_overrides = ContextVar('plugin_overrides', default=defaultdict(list))
plugin_pps = ContextVar('plugin_pps', default={})
