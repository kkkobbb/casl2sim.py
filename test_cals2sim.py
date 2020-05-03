#!/usr/bin/env python3
# coding:utf-8
import io
import copy
import unittest
import casl2sim


casl2sim.Element.__eq__ = lambda s,o: s.value == o.value and s.line == o.line
casl2sim.Element.__repr__ = \
        lambda s: f"<{s.__module__}.{type(s).__name__} value={s.value:04x}, line={s.line}>"

class TestParser(unittest.TestCase):
    def test_parse_DC(self):
        p = casl2sim.Parser()
        p.set_actual_label("LAB", 0xff)
        expected = [
                casl2sim.Element(12, 0),
                casl2sim.Element(0xf, 0),
                casl2sim.Element(0xff, 0),
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
                ((0xff, 0xf0), ["GR0", "GR1"], [], (0xff01,), "1 word"),
                ((0xff, 0xf0), ["GR3", "LAB", "GR5"], [],
                    (0xf035, 0x00ff), "2 words label"),
                ((0xff, 0xf0), ["GR3", "=11", "GR5"],
                    [casl2sim.Element(0, 0)]*3,
                    (0xf035, 0x0003), "2 words const addr"),
                ((0xff, 0xf0), ["GR3", "11", "GR5"], [],
                    (0xf035, 0x000b), "2 word const literal")]

        p = casl2sim.Parser()
        for ops, args, mem, expected_vals, msg in patterns:
            with self.subTest(msg):
                p._mem = mem
                p._actual_labels = {"LAB":0xff}
                expected = [casl2sim.Element(v, 0) for v in expected_vals]
                actual = p.op_1or2word(ops[0], ops[1], args)
                p.resolve_labels()
                p.resolve_consts()
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

    def test_op_SVC_IN(self):
        patterns = [
                ("ABCDE", [
                    0xf000, 0x0001, 0x1000, 0x1001, ord("A"), ord("B"), ord("C"),
                    ord("D"), ord("E"), 0x1007, 0x1008, 0x1009, 0x0005], "just input"),
                ("AB", [
                    0xf000, 0x0001, 0x1000, 0x1001, ord("A"), ord("B"), 0x0000,
                    0x0000, 0x0000, 0x1007, 0x1008, 0x1009, 0x0005], "short input"),
                ("ABCDEFGH", [
                    0xf000, 0x0001, 0x1000, 0x1001, ord("A"), ord("B"), ord("C"),
                    ord("D"), ord("E"), 0x1007, 0x1008, 0x1009, 0x0005], "long input")]

        mem_vals = [
                0xf000, 0x0001, 0x1000, 0x1001, 0x1002, 0x1003, 0x1004,
                0x1005, 0x1006, 0x1007, 0x1008, 0x1009, 0x0005]
        for input_str, expected_vals, msg in patterns:
            with self.subTest(msg):
                expected = [casl2sim.Element(v, 0) for v in expected_vals]
                c = casl2sim.Comet2([casl2sim.Element(v, 0) for v in mem_vals])
                c._inputf = io.StringIO(input_str)
                c._pr = 0
                c._gr = [0, 4, 12, 0, 0, 0, 0, 0]
                elem = c.fetch()
                c.op_SVC(elem)
                self.assertEqual(expected, c._mem[:len(mem_vals)])

    def test_op_SVC_OUT(self):
        mem_vals = [
                0xf000, 0x0002, ord("X"), ord("X"), ord("t"), ord("e"),
                ord("s"), ord("t"), ord(" "), ord("O"), ord("U"), ord("T"),
                ord("Y"), ord("Y"), 0x0008]
        mem = [casl2sim.Element(v, 0) for v in mem_vals]
        expected = "  OUT: test OUT\n"
        c = casl2sim.Comet2(mem)
        c._outputf = io.StringIO()
        c._gr[1] = 4
        c._gr[2] = 14
        elem = c.fetch()
        c.op_SVC(elem)
        actual = c._outputf.getvalue()
        self.assertEqual(expected, actual)
# End TestComet2

if __name__ == "__main__":
    unittest.main(verbosity=2)
