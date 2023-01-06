from ..compat.compat_utils import passthrough_module

passthrough_module(__name__, '.postprocessors', (None, '__all__'))
del passthrough_module


def get_postprocessor(key):
    from . import postprocessors
    return vars(postprocessors)[key + 'PP']
