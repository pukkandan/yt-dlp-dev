from .common import ExternalJSI


class DenoJSI(ExternalJSI, register=True):
    _VERSION_OPT = '-V'

    def _make_cmd(self, jsfile):
        return [self.EXE_NAME, 'run', jsfile]
