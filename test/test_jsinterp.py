#!/usr/bin/env python3

# Allow direct execution
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import math
import re

from test.helper import FakeYDL
from yt_dlp.jsinterp import JSDispatcher
from yt_dlp.jsinterp.native import JS_Undefined, NativeJSI


class TestNativeJSI(unittest.TestCase):
    def setUp(self):
        self.jsi = JSDispatcher(FakeYDL(), [NativeJSI])

    def call(self, code, name, *args):
        return self.jsi.evaluate_function(name, code, args).first()

    def test_basic(self):
        self.assertEqual(self.call('function x(){;}', 'x'), None)
        self.assertEqual(self.call('function x3(){return 42;}', 'x3'), 42)
        self.assertEqual(self.call('function x3(){42}', 'x3'), None)
        self.assertEqual(self.call('var x5 = function(){return 42;}', 'x5'), 42)

    def test_calc(self):
        self.assertEqual(self.call('function x4(a){return 2*a+1;}', 'x4', 3), 7)

    def test_empty_return(self):
        self.assertEqual(self.call('function f(){return; y()}', 'f'), None)

    def test_morespace(self):
        self.assertEqual(self.call('function x (a) { return 2 * a + 1 ; }', 'x', 3), 7)
        self.assertEqual(self.call('function f () { x =  2  ; return x; }', 'f'), 2)

    def test_strange_chars(self):
        self.assertEqual(self.call(
            'function $_xY1 ($_axY1) { var $_axY2 = $_axY1 + 1; return $_axY2; }', '$_xY1', 20), 21)

    def test_operators(self):
        self.assertEqual(self.call('function f(){return 1 << 5;}', 'f'), 32)
        self.assertEqual(self.call('function f(){return 2 ** 5}', 'f'), 32)
        self.assertEqual(self.call('function f(){return 19 & 21;}', 'f'), 17)
        self.assertEqual(self.call('function f(){return 11 >> 2;}', 'f'), 2)
        self.assertEqual(self.call('function f(){return []? 2+3: 4;}', 'f'), 5)
        self.assertEqual(self.call('function f(){return 1 == 2}', 'f'), False)
        self.assertEqual(self.call('function f(){return 0 && 1 || 2;}', 'f'), 2)
        self.assertEqual(self.call('function f(){return 0 ?? 42;}', 'f'), 0)
        self.assertFalse(self.call('function f(){return "string" < 42;}', 'f'))

    def test_array_access(self):
        self.assertEqual(self.call(
            'function f(){var x = [1,2,3]; x[0] = 4; x[0] = 5; x[2.0] = 7; return x;}', 'f'), [5, 2, 7])

    def test_parens(self):
        self.assertEqual(self.call(
            'function f(){return (1) + (2) * ((( (( (((((3)))))) )) ));}', 'f'), 7)
        self.assertEqual(self.call('function f(){return (1 + 2) * 3;}', 'f'), 9)

    def test_quotes(self):
        self.assertEqual(self.call(R'function f(){return "a\"\\("}', 'f'), R'a"\(')

    def test_assignments(self):
        self.assertEqual(self.call('function f(){var x = 20; x = 30 + 1; return x;}', 'f'), 31)
        self.assertEqual(self.call('function f(){var x = 20; x += 30 + 1; return x;}', 'f'), 51)
        self.assertEqual(self.call('function f(){var x = 20; x -= 30 + 1; return x;}', 'f'), -11)

    def test_comments(self):
        'Skipping: Not yet fully implemented'
        return
        self.assertEqual(self.call('''
            function x() {
                var x = /* 1 + */ 2;
                var y = /* 30
                * 40 */ 50;
                return x + y;
            }
            ''', 'x'), 52)

        self.assertEqual(self.call('''
            function f() {
                var x = "/*";
                var y = 1 /* comment */ + 2;
                return y;
            }
            ''', 'f'), 3)

    def test_precedence(self):
        self.assertEqual(self.call('''
            function x() {
                var a = [10, 20, 30, 40, 50];
                var b = 6;
                a[0]=a[b%a.length];
                return a;
            }''', 'x'), [20, 20, 30, 40, 50])

    def test_builtins(self):
        self.assertTrue(math.isnan(self.call('function x() { return NaN }', 'x')))
        self.assertEqual(self.call(
            'function x() { return new Date(\'Wednesday 31 December 1969 18:01:26 MDT\') - 0; }', 'x'), 86000)
        self.assertEqual(self.call(
            'function x(dt) { return new Date(dt) - 0; }', 'x', 'Wednesday 31 December 1969 18:01:26 MDT'), 86000)

    def test_call(self):
        code = '''
            function x() { return 2; }
            function y(a) { return x() + (a?a:0); }
            function z() { return y(3); }
        '''
        self.assertEqual(self.call(code, 'z'), 5)
        self.assertEqual(self.call(code, 'y'), 2)

    def test_for_loop(self):
        self.assertEqual(self.call(
            'function x() { a=0; for (i=0; i-10; i++) {a++} return a }', 'x'), 10)

    def test_switch(self):
        code = '''
            function x(f) { switch(f){
                case 1:f+=1;
                case 2:f+=2;
                case 3:f+=3;break;
                case 4:f+=4;
                default:f=0;
            } return f }
        '''
        self.assertEqual(self.call(code, 'x', 1), 7)
        self.assertEqual(self.call(code, 'x', 3), 6)
        self.assertEqual(self.call(code, 'x', 5), 0)

    def test_switch_default(self):
        code = '''
            function x(f) { switch(f){
                case 2: f+=2;
                default: f-=1;
                case 5:
                case 6: f+=6;
                case 0: break;
                case 1: f+=1;
            } return f }
        '''
        self.assertEqual(self.call(code, 'x', 1), 2)
        self.assertEqual(self.call(code, 'x', 5), 11)
        self.assertEqual(self.call(code, 'x', 9), 14)

    def test_try(self):
        self.assertEqual(self.call('function x() { try{return 10} catch(e){return 5} }', 'x'), 10)

    def test_catch(self):
        self.assertEqual(self.call('function x() { try{throw 10} catch(e){return 5} }', 'x'), 5)

    def test_finally(self):
        self.assertEqual(self.call(
            'function x() { try{throw 10} finally {return 42} }', 'x'), 42)
        self.assertEqual(self.call(
            'function x() { try{throw 10} catch(e){return 5} finally {return 42} }', 'x'), 42)

    def test_nested_try(self):
        self.assertEqual(self.call('''
            function x() {try {
                try{throw 10} finally {throw 42}
                } catch(e){return 5} }
            ''', 'x'), 5)

    def test_for_loop_continue(self):
        self.assertEqual(self.call(
            'function x() { a=0; for (i=0; i-10; i++) { continue; a++ } return a }', 'x'), 0)

    def test_for_loop_break(self):
        self.assertEqual(self.call('function x() { a=0; for (i=0; i-10; i++) { break; a++ } return a }', 'x'), 0)

    def test_for_loop_try(self):
        self.assertEqual(self.call('''
            function x() {
                for (i=0; i-10; i++) { try { if (i == 5) throw i} catch {return 10} finally {break} };
                return 42 }
            ''', 'x'), 42)

    def test_literal_list(self):
        self.assertEqual(self.call('function x() { return [1, 2, "asdf", [5, 6, 7]][3] }', 'x'), [5, 6, 7])

    def test_comma(self):
        self.assertEqual(self.call('function x() { a=5; a -= 1, a+=3; return a }', 'x'), 7)
        self.assertEqual(self.call('function x() { a=5; return (a -= 1, a+=3, a); }', 'x'), 7)
        self.assertEqual(self.call(
            'function x() { return (l=[0,1,2,3], function(a, b){return a+b})((l[1], l[2]), l[3]) }', 'x'), 5)

    def test_void(self):
        self.assertEqual(self.call('function x() { return void 42; }', 'x'), None)

    def test_return_function(self):
        self.assertEqual(self.call('function x() { return [1, function(){return 1}][1] }', 'x')([]), 1)

    def test_null(self):
        self.assertEqual(self.call('function x() { return null; }', 'x'), None)
        self.assertEqual(self.call(
            'function x() { return [null > 0, null < 0, null == 0, null === 0]; }', 'x'), [False, False, False, False])
        self.assertEqual(self.call('function x() { return [null >= 0, null <= 0]; }', 'x'), [True, True])

    def test_undefined(self):
        self.assertEqual(self.call('function x() { return undefined === undefined; }', 'x'), True)
        self.assertEqual(self.call('function x() { return undefined; }', 'x'), JS_Undefined)
        self.assertEqual(self.call('function x() { let v; return v; }', 'x'), JS_Undefined)
        self.assertEqual(self.call(
            'function x() { return [undefined === undefined, undefined == undefined, undefined < undefined, undefined > undefined]; }',
            'x'), [True, True, False, False])
        self.assertEqual(self.call(
            'function x() { return [undefined === 0, undefined == 0, undefined < 0, undefined > 0]; }',
            'x'), [False, False, False, False])
        self.assertEqual(self.call(
            'function x() { return [undefined >= 0, undefined <= 0]; }', 'x'), [False, False])
        self.assertEqual(self.call(
            'function x() { return [undefined > null, undefined < null, undefined == null, undefined === null]; }',
            'x'), [False, False, True, False])
        self.assertEqual(self.call(
            'function x() { return [undefined === null, undefined == null, undefined < null, undefined > null]; }',
            'x'), [False, True, False, False])

        for y in self.call('function x() { let v; return [42+v, v+42, v**42, 42**v, 0**v]; }', 'x'):
            self.assertTrue(math.isnan(y))
        self.assertEqual(self.call('function x() { let v; return v**0; }', 'x'), 1)
        self.assertEqual(self.call(
            'function x() { let v; return [v>42, v<=42, v&&42, 42&&v]; }', 'x'), [False, False, JS_Undefined, JS_Undefined])
        self.assertEqual(self.call('function x(){return undefined ?? 42; }', 'x'), 42)

    def test_object(self):
        self.assertEqual(self.call('function x() { return {}; }', 'x'), {})
        self.assertEqual(self.call(
            'function x() { let a = {m1: 42, m2: 0 }; return [a["m1"], a.m2]; }', 'x'), [42, 0])
        self.assertEqual(self.call('function x() { let a; return a?.qq; }', 'x'), JS_Undefined)
        self.assertEqual(self.call(
            'function x() { let a = {m1: 42, m2: 0 }; return a?.qq; }', 'x'), JS_Undefined)

    def test_regex(self):
        self.assertEqual(self.call('function x() { let a=/,,[/,913,/](,)}/; }', 'x'), None)
        self.assertIsInstance(self.call('function x() { let a=/,,[/,913,/](,)}/; return a; }', 'x'), re.Pattern)
        self.assertEqual(self.call(
            'function x() { let a=/,,[/,913,/](,)}/i; return a; }', 'x').flags & re.I, re.I)
        self.assertEqual(self.call(
            R'function x() { let a=/,][}",],()}(\[)/; return a; }', 'x').pattern, r',][}",],()}(\[)')

        self.assertEqual(self.call(
            R'''function x() { let a=[/[)\\]/]; return a[0]; }''', 'x').pattern, r'[)\\]')

    def test_char_code_at(self):
        code = 'function x(i){return "test".charCodeAt(i)}'
        self.assertEqual(self.call(code, 'x', 0), 116)
        self.assertEqual(self.call(code, 'x', 1), 101)
        self.assertEqual(self.call(code, 'x', 2), 115)
        self.assertEqual(self.call(code, 'x', 3), 116)
        self.assertEqual(self.call(code, 'x', 4), None)
        self.assertEqual(self.call(code, 'x', 'not_a_number'), 116)

    def test_bitwise_operators_overflow(self):
        self.assertEqual(self.call('function x(){return -524999584 << 5}', 'x'), 379882496)
        self.assertEqual(self.call('function x(){return 1236566549 << 5}', 'x'), 915423904)


if __name__ == '__main__':
    unittest.main()
