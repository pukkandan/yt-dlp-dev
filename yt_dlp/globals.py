import contextvars

ffmpeg_location = contextvars.ContextVar('ffmpeg_location', default=None)

# FIXME: Since plugin imports are global, contextvars is useless here?
#   Should this be a global var inside plugins?
#       Is moving meta_path modification to a function possible?
#   Perhaps, this could be in utils instead?
plugin_dirs = contextvars.ContextVar('plugin_dirs', default=(..., ))

# Other contextvars can also help to give more control over optional dependencies, exe paths and lazy extractor
# since there cannot be controlled from inside YoutubeDL.
#   Would this also help with output rework? E.g, to set the verbosity/warning levels globally?
# Should this module even exist? Or should the different contextvars be moved to their respective modules?
