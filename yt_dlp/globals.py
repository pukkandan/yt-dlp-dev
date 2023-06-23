from contextvars import ContextVar

IN_CLI = ContextVar('IN_CLI', default=False)

# `True`=enabled, `None`=disabled, `False`=force disabled
LAZY_EXTRACTORS = ContextVar('LAZY_EXTRACTORS')

ffmpeg_location = ContextVar('ffmpeg_location', default=None)

# "..." indicates default paths
plugin_dirs = ContextVar('plugin_dirs', default=(..., ))
