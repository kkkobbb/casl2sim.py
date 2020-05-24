#!/usr/bin/env python3
# coding:utf-8
import io
import pathlib
import sys
import unittest
from unittest import mock

import casl2sim


casl2sim.Element.__eq__ = lambda s,o: s.value == o.value and s.line == o.line and s.vlabel == o.vlabel
casl2sim.Element.__repr__ = \
        lambda s: f"<{s.__module__}.{type(s).__name__} " + \
        f"value={s.value:04x}, line={s.line}, label='{s.label}'>"

class TestParser(unittest.TestCase):
    def test_parse_DC(self):
        p = casl2sim.Parser()
        p._defined_labels = {"LAB":0xff}
        expected = [
                casl2sim.Element(12, 0),
                casl2sim.Element(0xf, 0),
                casl2sim.Element(0xff, 0, "LAB"),
                casl2sim.Element(ord("a"), 0),
                casl2sim.Element(ord("b"), 0),
                casl2sim.Element(ord("c"), 0),
                casl2sim.Element(ord("d"), 0),
                casl2sim.Element(ord("'"), 0),
                casl2sim.Element(ord("e"), 0),
                casl2sim.Element(ord("'"), 0)]
        actual = p.parse_DC(" DC 12, #000f, LAB, 'abcd''e'''")
        p.resolve_labels()
        self.assertEqual(expected, actual)

    def test_op_1or2word(self):
        patterns = [
                ((0xff, 0xf0), ["GR0", "GR1"], [],
                    (0xff01,), (None,), "1 word"),
                ((0xff, 0xf0), ["GR3", "LAB", "GR5"], [],
                    (0xf035, 0x00ff), (None, "LAB"), "2 words label"),
                ((0xff, 0xf0), ["GR3", "=11", "GR5"], [casl2sim.Element(0, 0)]*3,
                    (0xf035, 0x0003), (None, "=11"), "2 words const addr"),
                ((0xff, 0xf0), ["GR3", "11", "GR5"], [],
                    (0xf035, 0x000b), (None, None), "2 words const literal")]

        p = casl2sim.Parser()
        for ops, args, mem, expected_vals, expected_lbls, msg in patterns:
            with self.subTest(msg):
                p._mem = mem
                p._defined_labels = {"LAB":0xff}
                expected = [casl2sim.Element(v, 0, b) for v, b in zip(expected_vals, expected_lbls)]
                actual = p.op_1or2word(ops[0], ops[1], args)
                p.resolve_labels()
                p.allocate_consts()
                self.assertEqual(expected, actual)

    def test_op_2word(self):
        patterns = [
                (0x11, ["GR1", "13"], (0x1110, 0x000d), "2 operands"),
                (0x11, ["GR2", "8", "GR6"], (0x1126, 0x0008), "3 operands")]

        p = casl2sim.Parser()
        for op, args, expected_vals, msg in patterns:
            with self.subTest(msg):
                expected = [casl2sim.Element(v, 0) for v in expected_vals]
                actual = p.op_2word(op, args)
                self.assertEqual(expected, actual)

    def test_resolve_labels(self):
        def_labels = {"LAB":0x0020, "LST":0x0010, "ABC":0x0100}
        patterns = [
                ({}, None, {}, -1, {}, "empty"),
                (def_labels, "LST", {}, 0x0010, {}, "start label"),
                (def_labels, None, {"LAB":[casl2sim.Element(0, 0)]},
                    -1, {"LAB":0x0020}, "label"),
                (def_labels, None,
                    {"LAB":[casl2sim.Element(0, 0), casl2sim.Element(0, 1), casl2sim.Element(0, 2)]},
                    -1, {"LAB":0x0020}, "label (multi elements)"),
                (def_labels, None,
                    {"LAB":[casl2sim.Element(0, 0)], "LST":[casl2sim.Element(0, 1)]},
                    -1, {"LAB":0x0020, "LST":0x0010}, "labels"),
                (def_labels, "ABC",
                    {"LAB":[casl2sim.Element(0, 0), casl2sim.Element(0, 1), casl2sim.Element(0, 2)]},
                    0x0100, {"LAB":0x0020}, "start label & label (multi elements)")]

        for def_labels, start_label, unr_labels, expected_start, expected_adrs, msg in patterns:
            with self.subTest(msg):
                p = casl2sim.Parser()
                p._defined_labels.update(def_labels)
                p._unresolved_labels = unr_labels
                p._start_label = start_label
                p.resolve_labels()
                for key in p._unresolved_labels:
                    self.assertTrue(key in expected_adrs)
                    expected_adr = expected_adrs[key]
                    actuals = p._unresolved_labels[key]
                    for i, actual in enumerate(actuals):
                        self.assertEqual(expected_adr, actual.value, msg=f"list[{i}]")
                self.assertEqual(expected_start, p._start)

    @mock.patch("casl2sim.Parser.err_exit", side_effect=SystemExit(1))
    def test_resolve_labels_error(self, mock_err_exit):
        """
        未定義のラベルがあった場合、正しくメッセージを出力して終了するか
        (SystemExit以外の例外が発生しないか)
        """
        def_labels = {"LAB":0x0020}
        patterns = [
                (def_labels, "LST", {}, "undefined start label (LST)", "undefined start label"),
                ({}, "LST", {}, "undefined start label (LST)", "undefined start label (empty)"),
                (def_labels, "LAB", {"LLL":[casl2sim.Element(0, 1)]},
                    "undefined label (L1: LLL)", "undefined label"),
                (def_labels, None, {"GR1":[casl2sim.Element(0, 212)]},
                    "reserved label (L212: GR1)", "reserved label")]

        for def_labels, start_label, unr_labels, expected_err_msg, msg in patterns:
            with self.subTest(msg):
                mock_err_exit.reset_mock()
                p = casl2sim.Parser()
                p._defined_labels.update(def_labels)
                p._start_label = start_label
                p._unresolved_labels = unr_labels
                with self.assertRaises(SystemExit) as cm:
                    p.resolve_labels()
                self.assertEqual(1, cm.exception.code)
                mock_err_exit.assert_called_once_with(expected_err_msg)

    @mock.patch("sys.stderr.write")
    def test_err_exit(self, mock_stderr_write):
        var1 = 12
        patterns = (
                ("syntax error", "err 1"),
                (f"test error '{var1}'", "err 2"),
                ("", "err 3"))

        p = casl2sim.Parser()
        for err_msg, msg in patterns:
            with self.subTest(msg):
                mock_stderr_write.reset_mock()
                with self.assertRaises(SystemExit) as cm:
                    p.err_exit(err_msg)
                self.assertEqual(1, cm.exception.code)
                expected = "Assemble Error: " + err_msg + "\n"
                actual = "".join(["".join(call.args) for call in mock_stderr_write.call_args_list])
                self.assertEqual(expected, actual)
# End TestParser

class TestComet2(unittest.TestCase):
    def test_op_LD_no_opr3(self):
        mem = [
                casl2sim.Element(0x1010, 0),
                casl2sim.Element(0x0003, 0),
                casl2sim.Element(0x0000, 0),
                casl2sim.Element(0x0012, 0)]
        c = casl2sim.Comet2(mem)
        expected = c._gr[:]
        expected[1] = 0x0012
        elem = c.fetch()
        c.op_LD(elem)
        self.assertEqual(expected, c._gr)

    def test_op_LD_opr3(self):
        mem = [
                casl2sim.Element(0x1013, 0),
                casl2sim.Element(0x0003, 0),
                casl2sim.Element(0x0000, 0),
                casl2sim.Element(0x0001, 0),
                casl2sim.Element(0x0012, 0)]
        c = casl2sim.Comet2(mem)
        c._gr[3] = 1
        expected = c._gr[:]
        expected[1] = 0x0012
        elem = c.fetch()
        c.op_LD(elem)
        self.assertEqual(expected, c._gr)

    def test_op_ST_no_opr3(self):
        mem = [
                casl2sim.Element(0x1110, 0),
                casl2sim.Element(0x0003, 0),
                casl2sim.Element(0x0001, 0),
                casl2sim.Element(0x0002, 0)]
        c = casl2sim.Comet2(mem)
        c._gr[1] = 0x0007
        expected = 0x0007
        elem = c.fetch()
        c.op_ST(elem)
        self.assertEqual(expected, c._mem[0x0003].value)

    def test_op_ST_opr3(self):
        mem = [
                casl2sim.Element(0x1112, 0),
                casl2sim.Element(0x0003, 0),
                casl2sim.Element(0x0001, 0),
                casl2sim.Element(0x0002, 0),
                casl2sim.Element(0x0003, 0)]
        c = casl2sim.Comet2(mem)
        c._gr[1] = 0x0007
        c._gr[2] = 0x0001
        expected = 0x0007
        elem = c.fetch()
        c.op_ST(elem)
        self.assertEqual(0x0002, c._mem[0x0003].value)
        self.assertEqual(expected, c._mem[0x0004].value)

    def test_op_LAD_no_opr3(self):
        mem = [
                casl2sim.Element(0x1210, 0),
                casl2sim.Element(0x0007, 0)]
        c = casl2sim.Comet2(mem)
        expected = c._gr[:]
        expected[1] = 0x0007
        elem = c.fetch()
        c.op_LAD(elem)
        self.assertEqual(expected, c._gr)

    def test_op_LAD_opr3(self):
        mem = [
                casl2sim.Element(0x1215, 0),
                casl2sim.Element(0x0007, 0)]
        c = casl2sim.Comet2(mem)
        c._gr[5] = 3
        expected = c._gr[:]
        expected[1] = 0x000a
        elem = c.fetch()
        c.op_LAD(elem)
        self.assertEqual(expected, c._gr)

    def test_op_LD_REG(self):
        mem = [
                casl2sim.Element(0x1415, 0)]
        c = casl2sim.Comet2(mem)
        c._gr[5] = 23
        expected = c._gr[:]
        expected[1] = c._gr[5]
        elem = c.fetch()
        c.op_LD_REG(elem)
        self.assertEqual(expected, c._gr)

    def test_op_ADDA(self):
        patterns = [
                (0x0002, 0x0008, 0x000a, (0, 0, 0), "no flag"),
                (0x8000, 0xffff, 0x7fff, (0, 0, 1), "overflow 1"),
                (0x7fff, 0x7fff, 0xfffe, (0, 1, 1), "overflow 2")]

        mem = [
                casl2sim.Element(0x2010, 0),
                casl2sim.Element(0x0002, 0)]
        c = casl2sim.Comet2(mem)
        for rval, mval, expected_rval, expected_flags, msg in patterns:
            with self.subTest(msg):
                c._pr = 0
                c._gr = [0, rval, 0, 0, 0, 0, 0, 0]
                c._zf, c._sf, c._of = 0, 0, 0
                c._mem[2].value = mval
                elem = c.fetch()
                c.op_ADDA(elem)
                self.assertEqual([0, expected_rval, 0, 0, 0, 0, 0, 0], c._gr)
                self.assertEqual(expected_flags, (c._zf, c._sf, c._of))

    def test_op_ADDA_REG(self):
        mem = [casl2sim.Element(0x2416, 0)]
        c = casl2sim.Comet2(mem)
        c._gr[1] = 2
        c._gr[6] = 5
        c._zf, c._sf, c._of = 0, 0, 0
        expected = c._gr[:]
        expected[1] = 7
        elem = c.fetch()
        c.op_ADDA_REG(elem)
        self.assertEqual(expected, c._gr)
        self.assertEqual((0, 0, 0), (c._zf, c._sf, c._of))

    def test_op_SUBA(self):
        patterns = [
                (0x0008, 0x0006, 0x0002, (0, 0, 0), "no flag"),
                (0x7000, 0xf000, 0x8000, (0, 1, 1), "overflow 1"),
                (0x8001, 0x7000, 0x1001, (0, 0, 1), "overflow 2")]

        mem = [
                casl2sim.Element(0x2110, 0),
                casl2sim.Element(0x0002, 0)]
        c = casl2sim.Comet2(mem)
        for rval, mval, expected_rval, expected_flags, msg in patterns:
            with self.subTest(msg):
                c._pr = 0
                c._gr = [0, rval, 0, 0, 0, 0, 0, 0]
                c._zf, c._sf, c._of = 0, 0, 0
                c._mem[2].value = mval
                elem = c.fetch()
                c.op_SUBA(elem)
                self.assertEqual([0, expected_rval, 0, 0, 0, 0, 0, 0], c._gr)
                self.assertEqual(expected_flags, (c._zf, c._sf, c._of))

    def test_op_SUBA_REG(self):
        mem = [casl2sim.Element(0x2516, 0)]
        c = casl2sim.Comet2(mem)
        c._gr[1] = 2
        c._gr[6] = 5
        c._zf, c._sf, c._of = 0, 0, 0
        expected = c._gr[:]
        expected[1] = (-3) & 0xffff
        elem = c.fetch()
        c.op_SUBA_REG(elem)
        self.assertEqual(expected, c._gr)
        self.assertEqual((0, 1, 0), (c._zf, c._sf, c._of))

    def test_op_ADDL(self):
        patterns = [
                (0x0002, 0x0008, 0x000a, (0, 0, 0), "no flag"),
                (0x8000, 0xffff, 0x7fff, (0, 0, 1), "overflow 1"),
                (0x7fff, 0x7fff, 0xfffe, (0, 0, 0), "overflow 2")]

        mem = [
                casl2sim.Element(0x2210, 0),
                casl2sim.Element(0x0002, 0)]
        c = casl2sim.Comet2(mem)
        for rval, mval, expected_rval, expected_flags, msg in patterns:
            with self.subTest(msg):
                c._pr = 0
                c._gr = [0, rval, 0, 0, 0, 0, 0, 0]
                c._zf, c._sf, c._of = 0, 0, 0
                c._mem[2].value = mval
                elem = c.fetch()
                c.op_ADDL(elem)
                self.assertEqual([0, expected_rval, 0, 0, 0, 0, 0, 0], c._gr)
                self.assertEqual(expected_flags, (c._zf, c._sf, c._of))

    def test_op_ADDL_REG(self):
        mem = [casl2sim.Element(0x2616, 0)]
        c = casl2sim.Comet2(mem)
        c._gr[1] = 2
        c._gr[6] = 5
        c._zf, c._sf, c._of = 0, 0, 0
        expected = c._gr[:]
        expected[1] = 7
        elem = c.fetch()
        c.op_ADDL_REG(elem)
        self.assertEqual(expected, c._gr)
        self.assertEqual((0, 0, 0), (c._zf, c._sf, c._of))

    def test_op_SUBL(self):
        patterns = [
                (0x0008, 0x0006, 0x0002, (0, 0, 0), "no flag"),
                (0x7000, 0xf000, 0x8000, (0, 0, 1), "overflow 1"),
                (0x8001, 0x7000, 0x1001, (0, 0, 0), "overflow 2")]

        mem = [
                casl2sim.Element(0x2310, 0),
                casl2sim.Element(0x0002, 0)]
        c = casl2sim.Comet2(mem)
        for rval, mval, expected_rval, expected_flags, msg in patterns:
            with self.subTest(msg):
                c._pr = 0
                c._gr = [0, rval, 0, 0, 0, 0, 0, 0]
                c._zf, c._sf, c._of = 0, 0, 0
                c._mem[2].value = mval
                elem = c.fetch()
                c.op_SUBL(elem)
                self.assertEqual([0, expected_rval, 0, 0, 0, 0, 0, 0], c._gr)
                self.assertEqual(expected_flags, (c._zf, c._sf, c._of))

    def test_op_SUBL_REG(self):
        mem = [casl2sim.Element(0x2516, 0)]
        c = casl2sim.Comet2(mem)
        c._gr[1] = 2
        c._gr[6] = 5
        c._zf, c._sf, c._of = 0, 0, 0
        expected = c._gr[:]
        expected[1] = (-3) & 0xffff
        elem = c.fetch()
        c.op_SUBL_REG(elem)
        self.assertEqual(expected, c._gr)
        self.assertEqual((0, 0, 1), (c._zf, c._sf, c._of))

    def test_op_AND(self):
        patterns = [
                (0x0000, 0x0000, 0x0000, (1, 0, 0), "zero"),
                (0xff00, 0x0f0f, 0x0f00, (0, 0, 0), "no zero")]

        mem = [
                casl2sim.Element(0x3010, 0),
                casl2sim.Element(0x0002, 0)]
        c = casl2sim.Comet2(mem)
        for rval, mval, expected_rval, expected_flags, msg in patterns:
            with self.subTest(msg):
                c._pr = 0
                c._gr = [0, rval, 0, 0, 0, 0, 0, 0]
                c._zf, c._sf, c._of = 0, 0, 0
                c._mem[2].value = mval
                elem = c.fetch()
                c.op_AND(elem)
                self.assertEqual([0, expected_rval, 0, 0, 0, 0, 0, 0], c._gr)
                self.assertEqual(expected_flags, (c._zf, c._sf, c._of))

    def test_op_AND_REG(self):
        mem = [casl2sim.Element(0x3410, 0)]
        c = casl2sim.Comet2(mem)
        c._gr[1] = 0xff00
        c._gr[0] = 0xf0f0
        c._zf, c._sf, c._of = 0, 0, 0
        expected = c._gr[:]
        expected[1] = 0xf000
        elem = c.fetch()
        c.op_AND_REG(elem)
        self.assertEqual(expected, c._gr)
        self.assertEqual((0, 0, 0), (c._zf, c._sf, c._of))

    def test_op_OR(self):
        patterns = [
                (0x0000, 0x0000, 0x0000, (1, 0, 0), "zero"),
                (0xff00, 0x0f0f, 0xff0f, (0, 0, 0), "no zero")]

        mem = [
                casl2sim.Element(0x3110, 0),
                casl2sim.Element(0x0002, 0)]
        c = casl2sim.Comet2(mem)
        for rval, mval, expected_rval, expected_flags, msg in patterns:
            with self.subTest(msg):
                c._pr = 0
                c._gr = [0, rval, 0, 0, 0, 0, 0, 0]
                c._zf, c._sf, c._of = 0, 0, 0
                c._mem[2].value = mval
                elem = c.fetch()
                c.op_OR(elem)
                self.assertEqual([0, expected_rval, 0, 0, 0, 0, 0, 0], c._gr)
                self.assertEqual(expected_flags, (c._zf, c._sf, c._of))

    def test_op_OR_REG(self):
        mem = [casl2sim.Element(0x3510, 0)]
        c = casl2sim.Comet2(mem)
        c._gr[1] = 0xff00
        c._gr[0] = 0xf0f0
        c._zf, c._sf, c._of = 0, 0, 0
        expected = c._gr[:]
        expected[1] = 0xfff0
        elem = c.fetch()
        c.op_OR_REG(elem)
        self.assertEqual(expected, c._gr)
        self.assertEqual((0, 0, 0), (c._zf, c._sf, c._of))

    def test_op_XOR(self):
        patterns = [
                (0x0000, 0x0000, 0x0000, (1, 0, 0), "zero"),
                (0xff00, 0x0f0f, 0xf00f, (0, 0, 0), "no zero")]

        mem = [
                casl2sim.Element(0x3110, 0),
                casl2sim.Element(0x0002, 0)]
        c = casl2sim.Comet2(mem)
        for rval, mval, expected_rval, expected_flags, msg in patterns:
            with self.subTest(msg):
                c._pr = 0
                c._gr = [0, rval, 0, 0, 0, 0, 0, 0]
                c._zf, c._sf, c._of = 0, 0, 0
                c._mem[2].value = mval
                elem = c.fetch()
                c.op_XOR(elem)
                self.assertEqual([0, expected_rval, 0, 0, 0, 0, 0, 0], c._gr)
                self.assertEqual(expected_flags, (c._zf, c._sf, c._of))

    def test_op_XOR_REG(self):
        mem = [casl2sim.Element(0x3610, 0)]
        c = casl2sim.Comet2(mem)
        c._gr[1] = 0xff00
        c._gr[0] = 0xf0f0
        c._zf, c._sf, c._of = 0, 0, 0
        expected = c._gr[:]
        expected[1] = 0x0ff0
        elem = c.fetch()
        c.op_XOR_REG(elem)
        self.assertEqual(expected, c._gr)
        self.assertEqual((0, 0, 0), (c._zf, c._sf, c._of))

    def test_op_CPA(self):
        patterns = [
                (0x0005, 0x0005, (1, 0, 0), "=="),
                (0xf000, 0x000f, (0, 1, 0), "<"),
                (0x000f, 0xf000, (0, 0, 0), ">")]

        mem = [
                casl2sim.Element(0x4010, 0),
                casl2sim.Element(0x0002, 0)]
        c = casl2sim.Comet2(mem)
        for rval, mval, expected_flags, msg in patterns:
            with self.subTest(msg):
                c._pr = 0
                c._gr = [0, rval, 0, 0, 0, 0, 0, 0]
                c._zf, c._sf, c._of = 0, 0, 0
                c._mem[2].value = mval
                expected_gr = c._gr
                elem = c.fetch()
                c.op_CPA(elem)
                self.assertEqual(expected_gr, c._gr)
                self.assertEqual(expected_flags, (c._zf, c._sf, c._of))

    def test_op_CPA_REG(self):
        # ==
        mem = [casl2sim.Element(0x4412, 0)]
        c = casl2sim.Comet2(mem)
        c._gr[1] = 102
        c._gr[2] = 102
        c._zf, c._sf, c._of = 0, 0, 0
        expected = c._gr[:]
        elem = c.fetch()
        c.op_CPA_REG(elem)
        self.assertEqual(expected, c._gr)
        self.assertEqual((1, 0, 0), (c._zf, c._sf, c._of))

    def test_op_CPL(self):
        patterns = [
                (0x0005, 0x0005, (1, 0, 0), "=="),
                (0x000f, 0xf000, (0, 1, 0), "<"),
                (0xf000, 0x000f, (0, 0, 0), ">")]

        mem = [
                casl2sim.Element(0x4110, 0),
                casl2sim.Element(0x0002, 0)]
        c = casl2sim.Comet2(mem)
        for rval, mval, expected_flags, msg in patterns:
            with self.subTest(msg):
                c._pr = 0
                c._gr = [0, rval, 0, 0, 0, 0, 0, 0]
                c._zf, c._sf, c._of = 0, 0, 0
                c._mem[2].value = mval
                expected_gr = c._gr
                elem = c.fetch()
                c.op_CPL(elem)
                self.assertEqual(expected_gr, c._gr)
                self.assertEqual(expected_flags, (c._zf, c._sf, c._of))

    def test_op_CPL_REG(self):
        # ==
        mem = [casl2sim.Element(0x4412, 0)]
        c = casl2sim.Comet2(mem)
        c._gr[1] = 304
        c._gr[2] = 304
        c._zf, c._sf, c._of = 0, 0, 0
        expected = c._gr[:]
        elem = c.fetch()
        c.op_CPL_REG(elem)
        self.assertEqual(expected, c._gr)
        self.assertEqual((1, 0, 0), (c._zf, c._sf, c._of))

    def test_op_SLA(self):
        patterns = [
                (0x000f, 0x0004, 0x00f0, (0, 0, 0), "no flag"),
                (0x180f, 0x0004, 0x00f0, (0, 0, 1), "overflow"),
                (0x7f00, 0x0009, 0x0000, (1, 0, 0), "zero"),
                (0xbf01, 0x000f, 0x8000, (0, 1, 1), "15bit shift"),
                (0xbf01, 0x0010, 0x8000, (0, 1, 0), "16bit shift"),
                (0x7f00, 0xffff, 0x0000, (1, 0, 0), "long shift positive"),
                (0xff00, 0xffff, 0x8000, (0, 1, 0), "long shift negative")]

        mem = [
                casl2sim.Element(0x5010, 0),
                casl2sim.Element(0x0002, 0)]
        c = casl2sim.Comet2(mem)
        for rval, mval, expected_rval, expected_flags, msg in patterns:
            with self.subTest(msg):
                c._pr = 0
                c._gr = [0, rval, 0, 0, 0, 0, 0, 0]
                c._zf, c._sf, c._of = 0, 0, 0
                c._mem[2].value = mval
                elem = c.fetch()
                c.op_SLA(elem)
                self.assertEqual([0, expected_rval, 0, 0, 0, 0, 0, 0], c._gr)
                self.assertEqual(expected_flags, (c._zf, c._sf, c._of))

    def test_op_SRA(self):
        patterns = [
                (0x7000, 0x0004, 0x0700, (0, 0, 0), "no flag"),
                (0xf00f, 0x0004, 0xff00, (0, 1, 1), "overflow"),
                (0x0007, 0x0004, 0x0000, (1, 0, 0), "zero"),
                (0xbf01, 0x000f, 0xffff, (0, 1, 0), "15bit shift"),
                (0xbf01, 0x0010, 0xffff, (0, 1, 1), "16bit shift"),
                (0x7f00, 0xffff, 0x0000, (1, 0, 0), "long shift positive"),
                (0xff00, 0xffff, 0xffff, (0, 1, 1), "long shift negative")]

        mem = [
                casl2sim.Element(0x5120, 0),
                casl2sim.Element(0x0002, 0)]
        c = casl2sim.Comet2(mem)
        for rval, mval, expected_rval, expected_flags, msg in patterns:
            with self.subTest(msg):
                c._pr = 0
                c._gr = [0, 0, rval, 0, 0, 0, 0, 0]
                c._zf, c._sf, c._of = 0, 0, 0
                c._mem[2].value = mval
                elem = c.fetch()
                c.op_SRA(elem)
                self.assertEqual([0, 0, expected_rval, 0, 0, 0, 0, 0], c._gr)
                self.assertEqual(expected_flags, (c._zf, c._sf, c._of))

    def test_op_SLL(self):
        patterns = [
                (0x000f, 0x0004, 0x00f0, (0, 0, 0), "no flag"),
                (0x180f, 0x0004, 0x80f0, (0, 0, 1), "overflow"),
                (0x7f00, 0x0009, 0x0000, (1, 0, 0), "zero"),
                (0xbf01, 0x0010, 0x0000, (1, 0, 1), "16bit shift"),
                (0xbf01, 0x0011, 0x0000, (1, 0, 0), "17bit shift"),
                (0x7f00, 0xffff, 0x0000, (1, 0, 0), "long shift positive"),
                (0xff00, 0xffff, 0x0000, (1, 0, 0), "long shift negative")]

        mem = [
                casl2sim.Element(0x5230, 0),
                casl2sim.Element(0x0002, 0)]
        c = casl2sim.Comet2(mem)
        for rval, mval, expected_rval, expected_flags, msg in patterns:
            with self.subTest(msg):
                c._pr = 0
                c._gr = [0, 0, 0, rval, 0, 0, 0, 0]
                c._zf, c._sf, c._of = 0, 0, 0
                c._mem[2].value = mval
                elem = c.fetch()
                c.op_SLL(elem)
                self.assertEqual([0, 0, 0, expected_rval, 0, 0, 0, 0], c._gr)
                self.assertEqual(expected_flags, (c._zf, c._sf, c._of))

    def test_op_SRL(self):
        patterns = [
                (0x7000, 0x0004, 0x0700, (0, 0, 0), "no flag"),
                (0xf00f, 0x0004, 0x0f00, (0, 0, 1), "overflow"),
                (0x0007, 0x0004, 0x0000, (1, 0, 0), "zero"),
                (0xbf00, 0x0010, 0x0000, (1, 0, 1), "16bit shift"),
                (0xbf00, 0x0011, 0x0000, (1, 0, 0), "17bit shift"),
                (0x7f00, 0xffff, 0x0000, (1, 0, 0), "long shift positive"),
                (0xff00, 0xffff, 0x0000, (1, 0, 0), "long shift negative")]

        mem = [
                casl2sim.Element(0x5340, 0),
                casl2sim.Element(0x0002, 0)]
        c = casl2sim.Comet2(mem)
        for rval, mval, expected_rval, expected_flags, msg in patterns:
            with self.subTest(msg):
                c._pr = 0
                c._gr = [0, 0, 0, 0, rval, 0, 0, 0]
                c._zf, c._sf, c._of = 0, 0, 0
                c._mem[2].value = mval
                elem = c.fetch()
                c.op_SRL(elem)
                self.assertEqual([0, 0, 0, 0, expected_rval, 0, 0, 0], c._gr)
                self.assertEqual(expected_flags, (c._zf, c._sf, c._of))

    def test_op_JMI(self):
        patterns = [
                ((0, 1, 0), True, "jump 1"),
                ((1, 1, 1), True, "jump 2"),
                ((0, 0, 0), False, "not jump 1"),
                ((1, 0, 0), False, "not jump 2"),
                ((1, 0, 1), False, "not jump 3")]

        mem = [
                casl2sim.Element(0x6100, 0),
                casl2sim.Element(0xbeef, 0)]
        c = casl2sim.Comet2(mem)
        for flags, expected_branched, msg in patterns:
            with self.subTest(msg):
                c._pr = 0
                c._gr = [0, 0, 0, 0, 0, 0, 0, 0]
                c._zf, c._sf, c._of = flags
                elem = c.fetch()
                c.op_JMI(elem)
                expected_pr = 0xbeef if expected_branched else 0x0002
                self.assertEqual([0, 0, 0, 0, 0, 0, 0, 0], c._gr)
                self.assertEqual(flags, (c._zf, c._sf, c._of))
                self.assertEqual(expected_pr, c._pr)

    def test_op_JNZ(self):
        patterns = [
                ((0, 0, 0), True, "jump 1"),
                ((0, 1, 1), True, "jump 2"),
                ((1, 0, 0), False, "not jump 1"),
                ((1, 1, 0), False, "not jump 2"),
                ((1, 1, 1), False, "not jump 3")]

        mem = [
                casl2sim.Element(0x6200, 0),
                casl2sim.Element(0xbeef, 0)]
        c = casl2sim.Comet2(mem)
        for flags, expected_branched, msg in patterns:
            with self.subTest(msg):
                c._pr = 0
                c._gr = [0, 0, 0, 0, 0, 0, 0, 0]
                c._zf, c._sf, c._of = flags
                elem = c.fetch()
                c.op_JNZ(elem)
                expected_pr = 0xbeef if expected_branched else 0x0002
                self.assertEqual([0, 0, 0, 0, 0, 0, 0, 0], c._gr)
                self.assertEqual(flags, (c._zf, c._sf, c._of))
                self.assertEqual(expected_pr, c._pr)

    def test_op_JZE(self):
        patterns = [
                ((1, 0, 0), True, "jump 1"),
                ((1, 1, 1), True, "jump 2"),
                ((0, 0, 0), False, "not jump 1"),
                ((0, 1, 0), False, "not jump 2"),
                ((0, 1, 1), False, "not jump 3")]

        mem = [
                casl2sim.Element(0x6300, 0),
                casl2sim.Element(0xbeef, 0)]
        c = casl2sim.Comet2(mem)
        for flags, expected_branched, msg in patterns:
            with self.subTest(msg):
                c._pr = 0
                c._gr = [0, 0, 0, 0, 0, 0, 0, 0]
                c._zf, c._sf, c._of = flags
                elem = c.fetch()
                c.op_JZE(elem)
                expected_pr = 0xbeef if expected_branched else 0x0002
                self.assertEqual([0, 0, 0, 0, 0, 0, 0, 0], c._gr)
                self.assertEqual(flags, (c._zf, c._sf, c._of))
                self.assertEqual(expected_pr, c._pr)

    def test_op_JUMP(self):
        patterns = [
                ((0, 0, 0), True, "jump 1"),
                ((1, 1, 1), True, "jump 2")]

        mem = [
                casl2sim.Element(0x6400, 0),
                casl2sim.Element(0xbeef, 0)]
        c = casl2sim.Comet2(mem)
        for flags, expected_branched, msg in patterns:
            with self.subTest(msg):
                c._pr = 0
                c._gr = [0, 0, 0, 0, 0, 0, 0, 0]
                c._zf, c._sf, c._of = flags
                elem = c.fetch()
                c.op_JUMP(elem)
                expected_pr = 0xbeef if expected_branched else 0x0002
                self.assertEqual([0, 0, 0, 0, 0, 0, 0, 0], c._gr)
                self.assertEqual(flags, (c._zf, c._sf, c._of))
                self.assertEqual(expected_pr, c._pr)

    def test_op_JPL(self):
        patterns = [
                ((0, 0, 0), True, "jump 1"),
                ((0, 0, 1), True, "jump 2"),
                ((0, 1, 0), False, "not jump 1"),
                ((1, 0, 0), False, "not jump 2"),
                ((1, 1, 1), False, "not jump 3")]

        mem = [
                casl2sim.Element(0x6500, 0),
                casl2sim.Element(0xbeef, 0)]
        c = casl2sim.Comet2(mem)
        for flags, expected_branched, msg in patterns:
            with self.subTest(msg):
                c._pr = 0
                c._gr = [0, 0, 0, 0, 0, 0, 0, 0]
                c._zf, c._sf, c._of = flags
                elem = c.fetch()
                c.op_JPL(elem)
                expected_pr = 0xbeef if expected_branched else 0x0002
                self.assertEqual([0, 0, 0, 0, 0, 0, 0, 0], c._gr)
                self.assertEqual(flags, (c._zf, c._sf, c._of))
                self.assertEqual(expected_pr, c._pr)

    def test_op_JOV(self):
        patterns = [
                ((0, 0, 1), True, "jump 1"),
                ((1, 1, 1), True, "jump 2"),
                ((0, 1, 0), False, "not jump 1"),
                ((1, 0, 0), False, "not jump 2"),
                ((1, 1, 0), False, "not jump 3")]

        mem = [
                casl2sim.Element(0x6600, 0),
                casl2sim.Element(0xbeef, 0)]
        c = casl2sim.Comet2(mem)
        for flags, expected_branched, msg in patterns:
            with self.subTest(msg):
                c._pr = 0
                c._gr = [0, 0, 0, 0, 0, 0, 0, 0]
                c._zf, c._sf, c._of = flags
                elem = c.fetch()
                c.op_JOV(elem)
                expected_pr = 0xbeef if expected_branched else 0x0002
                self.assertEqual([0, 0, 0, 0, 0, 0, 0, 0], c._gr)
                self.assertEqual(flags, (c._zf, c._sf, c._of))
                self.assertEqual(expected_pr, c._pr)

    def test_op_PUSH(self):
        patterns = [
                (0x0000, 0xbeef, "no reg"),
                (0x0010, 0xbeff, "reg")]

        mem = [
                casl2sim.Element(0x7002, 0),
                casl2sim.Element(0xbeef, 0)]
        c = casl2sim.Comet2(mem)
        for rval, expected_mval, msg in patterns:
            with self.subTest(msg):
                c._pr = 0
                c._sp = 0
                c._gr = [0, 0, rval, 0, 0, 0, 0, 0]
                elem = c.fetch()
                c.op_PUSH(elem)
                self.assertEqual([0, 0, rval, 0, 0, 0, 0, 0], c._gr)
                self.assertEqual(c._mem[c._sp].value, expected_mval)
                self.assertEqual(0xffff, c._sp)

    def test_op_POP(self):
        mem = [casl2sim.Element(0x7120, 0)]
        c = casl2sim.Comet2(mem)
        c._mem[0xff00].value = 0xbeef
        c._pr = 0
        c._sp = 0xff00
        c._gr = [0, 0, 0, 0, 0, 0, 0, 0]
        elem = c.fetch()
        c.op_POP(elem)
        self.assertEqual([0, 0, 0xbeef, 0, 0, 0, 0, 0], c._gr)
        self.assertEqual(0xff01, c._sp)

    def test_op_CALL(self):
        patterns = [
                (0x0000, 0xbeef, "no reg"),
                (0x0010, 0xbeff, "reg")]

        mem = [
                casl2sim.Element(0x8002, 0),
                casl2sim.Element(0xbeef, 0)]
        c = casl2sim.Comet2(mem)
        for rval, expected_mval, msg in patterns:
            with self.subTest(msg):
                c._pr = 0
                c._sp = 0
                c._gr = [0, 0, rval, 0, 0, 0, 0, 0]
                elem = c.fetch()
                c.op_CALL(elem)
                self.assertEqual([0, 0, rval, 0, 0, 0, 0, 0], c._gr)
                self.assertEqual(c._mem[c._sp].value, 2)
                self.assertEqual(c._pr, expected_mval)
                self.assertEqual(0xffff, c._sp)

    def test_op_RET(self):
        mem = [casl2sim.Element(0x8100, 0)]
        c = casl2sim.Comet2(mem)
        c._mem[0xff00].value = 0xbeef
        c._pr = 0
        c._sp = 0xff00
        c._gr = [0, 0, 0, 0, 0, 0, 0, 0]
        elem = c.fetch()
        c.op_RET(elem)
        self.assertEqual([0, 0, 0, 0, 0, 0, 0, 0], c._gr)
        self.assertEqual(c._pr, 0xbeef)
        self.assertEqual(0xff01, c._sp)

    def test_op_SVC_IN_size(self):
        patterns = [
                (256, "just input"),
                (0, "no input"),
                (11, "short input"),
                (300, "long input")]

        mem_vals = [0xf000, 0x0001]
        mem_vals.extend([i for i in range(0x1000, 0x1100)])
        for input_size, msg in patterns:
            with self.subTest(msg):
                valid_input_size = min(input_size, 256)
                input_vals = ["X" for _ in range(valid_input_size)]
                expected_vals = mem_vals[:]
                expected_vals[3] = min(valid_input_size, 256)
                expected_vals[4:4+valid_input_size] = [ord(s) for s in input_vals]
                expected = [casl2sim.Element(s, 0) for s in expected_vals]
                c = casl2sim.Comet2([casl2sim.Element(v, 0) for v in mem_vals])
                c._fin = io.StringIO("".join(input_vals))
                c._pr = 0
                c._gr = [0, 4, 3, 0, 0, 0, 0, 0]
                elem = c.fetch()
                c.op_SVC(elem)
                self.assertEqual(expected, c._mem[:len(expected)])

    def test_op_SVC_IN_newline(self):
        mem_vals = [0xf000, 0x0001]
        mem_vals.extend([i for i in range(0x1000, 0x1100)])
        input_str = '1111 test\nTEST\r!"#$'
        expected_str = '1111testTEST!"#$'
        input_size = len(expected_str)
        expected_vals = mem_vals[:]
        expected_vals[3] = input_size
        expected_vals[4:4+input_size] = [ord(s) for s in expected_str]
        expected = [casl2sim.Element(s, 0) for s in expected_vals]
        c = casl2sim.Comet2([casl2sim.Element(v, 0) for v in mem_vals])
        c._fin = io.StringIO(input_str)
        c._pr = 0
        c._gr = [0, 4, 3, 0, 0, 0, 0, 0]
        elem = c.fetch()
        c.op_SVC(elem)
        self.assertEqual(expected, c._mem[:len(expected)])

    def test_op_SVC_OUT(self):
        mem_vals = [
                0xf000, 0x0002, ord("X"), ord("X"), ord("t"), ord("e"),
                ord("s"), ord("t"), ord(" "), ord("O"), ord("U"), ord("T"),
                ord("Y"), ord("Y"), 0x0008]
        mem = [casl2sim.Element(v, 0) for v in mem_vals]
        expected = "  OUT: test OUT\n"
        c = casl2sim.Comet2(mem)
        c._fout = io.StringIO()
        c._gr[1] = 4
        c._gr[2] = 14
        elem = c.fetch()
        c.op_SVC(elem)
        actual = c._fout.getvalue()
        self.assertEqual(expected, actual)

    @mock.patch("sys.stderr.write")
    def test_err_exit_no_print_regs(self, mock_stderr_write):
        var1 = 12
        patterns = (
                ("syntax error", "err 1"),
                (f"test error '{var1}'", "err 2"),
                ("", "err 3"))

        c = casl2sim.Comet2([])
        for err_msg, msg in patterns:
            with self.subTest(msg):
                mock_stderr_write.reset_mock()
                with self.assertRaises(SystemExit) as cm:
                    c.err_exit(err_msg)
                self.assertEqual(1, cm.exception.code)
                expected = "Runtime Error: " + err_msg + "\n"
                actual = "".join(["".join(call.args) for call in mock_stderr_write.call_args_list])
                self.assertEqual(expected, actual)
# End TestComet2

class TestMain(unittest.TestCase):
    def setUp(self):
        self.orig_argv = sys.argv

    def tearDown(self):
        sys.argv = self.orig_argv

    def test_run_asmfile(self):
        asmdir = pathlib.Path("asm")
        testfiles = [str(p) for p in
                filter(lambda p: p.is_file() and p.name.startswith("test_"),
                    asmdir.iterdir())]
        for testfile in testfiles:
            with self.subTest(testfile=testfile):
                print(testfile)
                sys.argv = ["./casl2sim.py", testfile, "--input-src="]
                casl2sim.main()
        # エラーが発生しないこと
# End TestMain

if __name__ == "__main__":
    #unittest.main(verbosity=2)
    unittest.main(buffer=True)
