from .common import NestedScope as LocalNameSpace
from .native import *  # noqa: F401,F403
from .native import NativeJSI


class JSInterpreter(NativeJSI):
    def __init__(self, code, objects=None):
        self.code = code
        self._objects = objects or {}

    def extract_function_code(self, funcname):
        return super().extract_function_code(funcname, self.code)

    def extract_function(self, funcname):
        return self.extract_function_from_code(*self.extract_function_code(funcname))

    def call_function(self, funcname, *args):
        return self.run(
            *self.extract_function_code(self, funcname, self.code), args, full_code=self.code).return_value

    def build_function(self, argnames, code, *global_stack):
        return self._build_function(code, argnames, LocalNameSpace(*global_stack, self._objects))

    extract_function_from_code = build_function
