#!/usr/bin/env python3
# coding:utf-8
import io
import copy
import unittest
import casl2sim


casl2sim.Element.__eq__ = lambda s,o: s.value == o.value and s.line == o.line

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

    def test_op_1or2word_1w(self):
        p = casl2sim.Parser()
        expected = [casl2sim.Element(0xff01, 0)]
        actual = p.op_1or2word(0xff, 0xf0, ["GR0", "GR1"])
        self.assertEqual(expected, actual)

    def test_op_1or2word_2w_addr(self):
        p = casl2sim.Parser()
        p.set_actual_label("LAB", 0xff)
        expected = [
                casl2sim.Element(0xf035, 0),
                casl2sim.Element(0x00ff, 0)]
        actual = p.op_1or2word(0xff, 0xf0, ["GR3", "LAB", "GR5"])
        p.resolve_labels()
        self.assertEqual(expected, actual)

    def test_op_1or2word_2w_const(self):
        p = casl2sim.Parser()
        p._mem = [
                casl2sim.Element(0, 0),
                casl2sim.Element(0, 0),
                casl2sim.Element(0, 0)]
        expected = [
                casl2sim.Element(0xf035, 0),
                casl2sim.Element(0x0003, 0)]
        actual = p.op_1or2word(0xff, 0xf0, ["GR3", "=11", "GR5"])
        p.resolve_consts()
        self.assertEqual(expected, actual)

    def test_op_1or2word_2w_const2(self):
        p = casl2sim.Parser()
        expected = [
                casl2sim.Element(0xf035, 0),
                casl2sim.Element(0x000b, 0)]
        actual = p.op_1or2word(0xff, 0xf0, ["GR3", "11", "GR5"])
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
        mem = [
                casl2sim.Element(0x2010, 0),
                casl2sim.Element(0x0002, 0),
                casl2sim.Element(0x0008, 0)]
        c = casl2sim.Comet2(mem)
        c._of = 0
        c._gr[1] = 2
        expected = c._gr[:]
        expected[1] = 10
        elem = c.fetch()
        c.op_ADDA(elem)
        self.assertEqual(expected, c._gr)
        self.assertEqual(0, c._zf)
        self.assertEqual(0, c._sf)
        self.assertEqual(0, c._of)

    def test_op_ADDA_overflow1(self):
        mem = [
                casl2sim.Element(0x2010, 0),
                casl2sim.Element(0x0002, 0),
                casl2sim.Element(0xffff, 0)]
        c = casl2sim.Comet2(mem)
        c._of = 0
        c._gr[1] = 0x8000
        expected = c._gr[:]
        expected[1] = 0x7fff
        elem = c.fetch()
        c.op_ADDA(elem)
        self.assertEqual(expected, c._gr)
        self.assertEqual(0, c._zf)
        self.assertEqual(0, c._sf)
        self.assertEqual(1, c._of)

    def test_op_ADDA_overflow2(self):
        mem = [
                casl2sim.Element(0x2010, 0),
                casl2sim.Element(0x0002, 0),
                casl2sim.Element(0x7fff, 0)]
        c = casl2sim.Comet2(mem)
        c._of = 0
        c._gr[1] = 0x7fff
        expected = c._gr[:]
        expected[1] = 0xfffe
        elem = c.fetch()
        c.op_ADDA(elem)
        self.assertEqual(expected, c._gr)
        self.assertEqual(0, c._zf)
        self.assertEqual(1, c._sf)
        self.assertEqual(1, c._of)

    def test_op_ADDA_REG(self):
        mem = [casl2sim.Element(0x2416, 0)]
        c = casl2sim.Comet2(mem)
        c._of = 0
        c._gr[1] = 2
        c._gr[6] = 5
        expected = c._gr[:]
        expected[1] = 7
        elem = c.fetch()
        c.op_ADDA_REG(elem)
        self.assertEqual(expected, c._gr)
        self.assertEqual(0, c._zf)
        self.assertEqual(0, c._sf)
        self.assertEqual(0, c._of)

    def test_op_SUBA(self):
        mem = [
                casl2sim.Element(0x2110, 0),
                casl2sim.Element(0x0002, 0),
                casl2sim.Element(0x0008, 0)]
        c = casl2sim.Comet2(mem)
        c._of = 0
        c._gr[1] = 2
        expected = c._gr[:]
        expected[1] = (-6) & 0xffff
        elem = c.fetch()
        c.op_SUBA(elem)
        self.assertEqual(expected, c._gr)
        self.assertEqual(0, c._zf)
        self.assertEqual(1, c._sf)
        self.assertEqual(0, c._of)

    def test_op_SUBA_overflow1(self):
        mem = [
                casl2sim.Element(0x2110, 0),
                casl2sim.Element(0x0002, 0),
                casl2sim.Element(0xf000, 0)]
        c = casl2sim.Comet2(mem)
        c._of = 0
        c._gr[1] = 0x7000
        expected = c._gr[:]
        expected[1] = 0x8000
        elem = c.fetch()
        c.op_SUBA(elem)
        self.assertEqual(expected, c._gr)
        self.assertEqual(0, c._zf)
        self.assertEqual(1, c._sf)
        self.assertEqual(1, c._of)

    def test_op_SUBA_overflow2(self):
        mem = [
                casl2sim.Element(0x2110, 0),
                casl2sim.Element(0x0002, 0),
                casl2sim.Element(0x7000, 0)]
        c = casl2sim.Comet2(mem)
        c._of = 0
        c._gr[1] = 0x8001
        expected = c._gr[:]
        expected[1] = 0x1001
        elem = c.fetch()
        c.op_SUBA(elem)
        self.assertEqual(expected, c._gr)
        self.assertEqual(0, c._zf)
        self.assertEqual(0, c._sf)
        self.assertEqual(1, c._of)

    def test_op_SUBA_REG(self):
        mem = [casl2sim.Element(0x2516, 0)]
        c = casl2sim.Comet2(mem)
        c._of = 0
        c._gr[1] = 2
        c._gr[6] = 5
        expected = c._gr[:]
        expected[1] = (-3) & 0xffff
        elem = c.fetch()
        c.op_SUBA_REG(elem)
        self.assertEqual(expected, c._gr)
        self.assertEqual(0, c._zf)
        self.assertEqual(1, c._sf)
        self.assertEqual(0, c._of)

    def test_op_ADDL(self):
        mem = [
                casl2sim.Element(0x2210, 0),
                casl2sim.Element(0x0002, 0),
                casl2sim.Element(0x0008, 0)]
        c = casl2sim.Comet2(mem)
        c._of = 0
        c._gr[1] = 2
        expected = c._gr[:]
        expected[1] = 10
        elem = c.fetch()
        c.op_ADDL(elem)
        self.assertEqual(expected, c._gr)
        self.assertEqual(0, c._zf)
        self.assertEqual(0, c._sf)
        self.assertEqual(0, c._of)

    def test_op_ADDL_overflow1(self):
        mem = [
                casl2sim.Element(0x2210, 0),
                casl2sim.Element(0x0002, 0),
                casl2sim.Element(0xffff, 0)]
        c = casl2sim.Comet2(mem)
        c._of = 0
        c._gr[1] = 0x8000
        expected = c._gr[:]
        expected[1] = 0x7fff
        elem = c.fetch()
        c.op_ADDL(elem)
        self.assertEqual(expected, c._gr)
        self.assertEqual(0, c._zf)
        self.assertEqual(0, c._sf)
        self.assertEqual(1, c._of)

    def test_op_ADDL_overflow2(self):
        mem = [
                casl2sim.Element(0x2210, 0),
                casl2sim.Element(0x0002, 0),
                casl2sim.Element(0x7fff, 0)]
        c = casl2sim.Comet2(mem)
        c._of = 0
        c._gr[1] = 0x7fff
        expected = c._gr[:]
        expected[1] = 0xfffe
        elem = c.fetch()
        c.op_ADDL(elem)
        self.assertEqual(expected, c._gr)
        self.assertEqual(0, c._zf)
        self.assertEqual(0, c._sf)
        self.assertEqual(0, c._of)

    def test_op_ADDL_REG(self):
        mem = [casl2sim.Element(0x2616, 0)]
        c = casl2sim.Comet2(mem)
        c._of = 0
        c._gr[1] = 2
        c._gr[6] = 5
        expected = c._gr[:]
        expected[1] = 7
        elem = c.fetch()
        c.op_ADDL_REG(elem)
        self.assertEqual(expected, c._gr)
        self.assertEqual(0, c._zf)
        self.assertEqual(0, c._sf)
        self.assertEqual(0, c._of)

    def test_op_SUBL(self):
        mem = [
                casl2sim.Element(0x2110, 0),
                casl2sim.Element(0x0002, 0),
                casl2sim.Element(0x0008, 0)]
        c = casl2sim.Comet2(mem)
        c._of = 0
        c._gr[1] = 2
        expected = c._gr[:]
        expected[1] = (-6) & 0xffff
        elem = c.fetch()
        c.op_SUBL(elem)
        self.assertEqual(expected, c._gr)
        self.assertEqual(0, c._zf)
        self.assertEqual(0, c._sf)
        self.assertEqual(1, c._of)

    def test_op_SUBL_overflow1(self):
        mem = [
                casl2sim.Element(0x2110, 0),
                casl2sim.Element(0x0002, 0),
                casl2sim.Element(0xf000, 0)]
        c = casl2sim.Comet2(mem)
        c._of = 0
        c._gr[1] = 0x7000
        expected = c._gr[:]
        expected[1] = 0x8000
        elem = c.fetch()
        c.op_SUBL(elem)
        self.assertEqual(expected, c._gr)
        self.assertEqual(0, c._zf)
        self.assertEqual(0, c._sf)
        self.assertEqual(1, c._of)

    def test_op_SUBL_overflow2(self):
        mem = [
                casl2sim.Element(0x2110, 0),
                casl2sim.Element(0x0002, 0),
                casl2sim.Element(0x7000, 0)]
        c = casl2sim.Comet2(mem)
        c._of = 0
        c._gr[1] = 0x8001
        expected = c._gr[:]
        expected[1] = 0x1001
        elem = c.fetch()
        c.op_SUBL(elem)
        self.assertEqual(expected, c._gr)
        self.assertEqual(0, c._zf)
        self.assertEqual(0, c._sf)
        self.assertEqual(0, c._of)

    def test_op_SUBL_REG(self):
        mem = [casl2sim.Element(0x2516, 0)]
        c = casl2sim.Comet2(mem)
        c._of = 0
        c._gr[1] = 2
        c._gr[6] = 5
        expected = c._gr[:]
        expected[1] = (-3) & 0xffff
        elem = c.fetch()
        c.op_SUBL_REG(elem)
        self.assertEqual(expected, c._gr)
        self.assertEqual(0, c._zf)
        self.assertEqual(0, c._sf)
        self.assertEqual(1, c._of)

    def test_op_AND_1(self):
        mem = [
                casl2sim.Element(0x3010, 0),
                casl2sim.Element(0x0002, 0),
                casl2sim.Element(0x0000, 0)]
        c = casl2sim.Comet2(mem)
        c._gr[1] = 0x0000
        expected = c._gr[:]
        expected[1] = 0
        elem = c.fetch()
        c.op_AND(elem)
        self.assertEqual(expected, c._gr)
        self.assertEqual(1, c._zf)
        self.assertEqual(0, c._sf)
        self.assertEqual(0, c._of)

    def test_op_AND_2(self):
        mem = [
                casl2sim.Element(0x3010, 0),
                casl2sim.Element(0x0002, 0),
                casl2sim.Element(0x0f0f, 0)]
        c = casl2sim.Comet2(mem)
        c._gr[1] = 0xff00
        expected = c._gr[:]
        expected[1] = 0x0f00
        elem = c.fetch()
        c.op_AND(elem)
        self.assertEqual(expected, c._gr)
        self.assertEqual(0, c._zf)
        self.assertEqual(0, c._sf)
        self.assertEqual(0, c._of)

    def test_op_AND_REG(self):
        mem = [casl2sim.Element(0x3410, 0)]
        c = casl2sim.Comet2(mem)
        c._gr[1] = 0xff00
        c._gr[0] = 0xf0f0
        expected = c._gr[:]
        expected[1] = 0xf000
        elem = c.fetch()
        c.op_AND_REG(elem)
        self.assertEqual(expected, c._gr)
        self.assertEqual(0, c._zf)
        self.assertEqual(0, c._sf)
        self.assertEqual(0, c._of)

    def test_op_OR_1(self):
        mem = [
                casl2sim.Element(0x3110, 0),
                casl2sim.Element(0x0002, 0),
                casl2sim.Element(0x0000, 0)]
        c = casl2sim.Comet2(mem)
        c._gr[1] = 0x0000
        expected = c._gr[:]
        expected[1] = 0
        elem = c.fetch()
        c.op_OR(elem)
        self.assertEqual(expected, c._gr)
        self.assertEqual(1, c._zf)
        self.assertEqual(0, c._sf)
        self.assertEqual(0, c._of)

    def test_op_OR_2(self):
        mem = [
                casl2sim.Element(0x3110, 0),
                casl2sim.Element(0x0002, 0),
                casl2sim.Element(0x0f0f, 0)]
        c = casl2sim.Comet2(mem)
        c._gr[1] = 0xff00
        expected = c._gr[:]
        expected[1] = 0xff0f
        elem = c.fetch()
        c.op_OR(elem)
        self.assertEqual(expected, c._gr)
        self.assertEqual(0, c._zf)
        self.assertEqual(0, c._sf)
        self.assertEqual(0, c._of)

    def test_op_OR_REG(self):
        mem = [casl2sim.Element(0x3510, 0)]
        c = casl2sim.Comet2(mem)
        c._gr[1] = 0xff00
        c._gr[0] = 0xf0f0
        expected = c._gr[:]
        expected[1] = 0xfff0
        elem = c.fetch()
        c.op_OR_REG(elem)
        self.assertEqual(expected, c._gr)
        self.assertEqual(0, c._zf)
        self.assertEqual(0, c._sf)
        self.assertEqual(0, c._of)

    def test_op_XOR_1(self):
        mem = [
                casl2sim.Element(0x3210, 0),
                casl2sim.Element(0x0002, 0),
                casl2sim.Element(0x0000, 0)]
        c = casl2sim.Comet2(mem)
        c._gr[1] = 0x0000
        expected = c._gr[:]
        expected[1] = 0
        elem = c.fetch()
        c.op_XOR(elem)
        self.assertEqual(expected, c._gr)
        self.assertEqual(1, c._zf)
        self.assertEqual(0, c._sf)
        self.assertEqual(0, c._of)

    def test_op_XOR_2(self):
        mem = [
                casl2sim.Element(0x3210, 0),
                casl2sim.Element(0x0002, 0),
                casl2sim.Element(0x0f0f, 0)]
        c = casl2sim.Comet2(mem)
        c._gr[1] = 0xff00
        expected = c._gr[:]
        expected[1] = 0xf00f
        elem = c.fetch()
        c.op_XOR(elem)
        self.assertEqual(expected, c._gr)
        self.assertEqual(0, c._zf)
        self.assertEqual(0, c._sf)
        self.assertEqual(0, c._of)

    def test_op_XOR_REG(self):
        mem = [casl2sim.Element(0x3610, 0)]
        c = casl2sim.Comet2(mem)
        c._gr[1] = 0xff00
        c._gr[0] = 0xf0f0
        expected = c._gr[:]
        expected[1] = 0x0ff0
        elem = c.fetch()
        c.op_XOR_REG(elem)
        self.assertEqual(expected, c._gr)
        self.assertEqual(0, c._zf)
        self.assertEqual(0, c._sf)
        self.assertEqual(0, c._of)

    def test_op_CPA_eq(self):
        # ==
        mem = [
                casl2sim.Element(0x4010, 0),
                casl2sim.Element(0x0002, 0),
                casl2sim.Element(0x0005, 0)]
        c = casl2sim.Comet2(mem)
        c._gr[1] = 5
        expected = c._gr[:]
        elem = c.fetch()
        c.op_CPA(elem)
        self.assertEqual(expected, c._gr)
        self.assertEqual(1, c._zf)
        self.assertEqual(0, c._sf)
        self.assertEqual(0, c._of)

    def test_op_CPA_lt(self):
        # <
        mem = [
                casl2sim.Element(0x4010, 0),
                casl2sim.Element(0x0002, 0),
                casl2sim.Element(0x0005, 0)]
        c = casl2sim.Comet2(mem)
        c._gr[1] = 2
        expected = c._gr[:]
        elem = c.fetch()
        c.op_CPA(elem)
        self.assertEqual(expected, c._gr)
        self.assertEqual(0, c._zf)
        self.assertEqual(1, c._sf)
        self.assertEqual(0, c._of)

    def test_op_CPA_gt(self):
        # >
        mem = [
                casl2sim.Element(0x4010, 0),
                casl2sim.Element(0x0002, 0),
                casl2sim.Element(0x0005, 0)]
        c = casl2sim.Comet2(mem)
        c._gr[1] = 12
        expected = c._gr[:]
        elem = c.fetch()
        c.op_CPA(elem)
        self.assertEqual(expected, c._gr)
        self.assertEqual(0, c._zf)
        self.assertEqual(0, c._sf)
        self.assertEqual(0, c._of)

    def test_op_CPA_REG_eq(self):
        # ==
        mem = [casl2sim.Element(0x4412, 0)]
        c = casl2sim.Comet2(mem)
        c._gr[1] = 102
        c._gr[2] = 102
        expected = c._gr[:]
        elem = c.fetch()
        c.op_CPA_REG(elem)
        self.assertEqual(expected, c._gr)
        self.assertEqual(1, c._zf)
        self.assertEqual(0, c._sf)
        self.assertEqual(0, c._of)

    def test_op_CPL_eq(self):
        # ==
        mem = [
                casl2sim.Element(0x4110, 0),
                casl2sim.Element(0x0002, 0),
                casl2sim.Element(0x0005, 0)]
        c = casl2sim.Comet2(mem)
        c._gr[1] = 5
        expected = c._gr[:]
        elem = c.fetch()
        c.op_CPL(elem)
        self.assertEqual(expected, c._gr)
        self.assertEqual(1, c._zf)
        self.assertEqual(0, c._sf)
        self.assertEqual(0, c._of)

    def test_op_CPL_lt(self):
        # <
        mem = [
                casl2sim.Element(0x4110, 0),
                casl2sim.Element(0x0002, 0),
                casl2sim.Element(0x0005, 0)]
        c = casl2sim.Comet2(mem)
        c._gr[1] = 2
        expected = c._gr[:]
        elem = c.fetch()
        c.op_CPL(elem)
        self.assertEqual(expected, c._gr)
        self.assertEqual(0, c._zf)
        self.assertEqual(0, c._sf)
        self.assertEqual(1, c._of)

    def test_op_CPL_gt(self):
        # >
        mem = [
                casl2sim.Element(0x4110, 0),
                casl2sim.Element(0x0002, 0),
                casl2sim.Element(0x0005, 0)]
        c = casl2sim.Comet2(mem)
        c._gr[1] = 12
        expected = c._gr[:]
        elem = c.fetch()
        c.op_CPL(elem)
        self.assertEqual(expected, c._gr)
        self.assertEqual(0, c._zf)
        self.assertEqual(0, c._sf)
        self.assertEqual(0, c._of)

    def test_op_CPL_REG_eq(self):
        # ==
        mem = [casl2sim.Element(0x4412, 0)]
        c = casl2sim.Comet2(mem)
        c._gr[1] = 304
        c._gr[2] = 304
        expected = c._gr[:]
        elem = c.fetch()
        c.op_CPL_REG(elem)
        self.assertEqual(expected, c._gr)
        self.assertEqual(1, c._zf)
        self.assertEqual(0, c._sf)
        self.assertEqual(0, c._of)







    def test_op_SVC_IN_just(self):
        mem = [
                casl2sim.Element(0xf000, 0),
                casl2sim.Element(0x0001, 0),
                casl2sim.Element(0x1000, 0),
                casl2sim.Element(0x1001, 0),
                casl2sim.Element(0x1002, 0),
                casl2sim.Element(0x1003, 0),
                casl2sim.Element(0x1004, 0),
                casl2sim.Element(0x1005, 0),
                casl2sim.Element(0x1006, 0),
                casl2sim.Element(0x1007, 0),
                casl2sim.Element(0x1008, 0),
                casl2sim.Element(0x1009, 0)]
        size = len(mem)
        expected = [m.value for m in mem]
        expected[4:9] = [ord("A"), ord("B"), ord("C"), ord("D"), ord("E")]
        c = casl2sim.Comet2(mem)
        c._inputf = io.StringIO("ABCDE")
        c._gr[1] = 4
        c._gr[2] = 5
        elem = c.fetch()
        c.op_SVC(elem)
        actual = [m.value for m in c._mem[:size]]
        self.assertEqual(expected, actual)

    def test_op_SVC_IN_short(self):
        mem = [
                casl2sim.Element(0xf000, 0),
                casl2sim.Element(0x0001, 0),
                casl2sim.Element(0x1000, 0),
                casl2sim.Element(0x1001, 0),
                casl2sim.Element(0x1002, 0),
                casl2sim.Element(0x1003, 0),
                casl2sim.Element(0x1004, 0),
                casl2sim.Element(0x1005, 0),
                casl2sim.Element(0x1006, 0),
                casl2sim.Element(0x1007, 0),
                casl2sim.Element(0x1008, 0),
                casl2sim.Element(0x1009, 0)]
        size = len(mem)
        expected = [m.value for m in mem]
        expected[4:9] = [ord("A"), ord("B"), 0, 0, 0]
        c = casl2sim.Comet2(mem)
        c._inputf = io.StringIO("AB")
        c._gr[1] = 4
        c._gr[2] = 5
        elem = c.fetch()
        c.op_SVC(elem)
        actual = [m.value for m in c._mem[:size]]
        self.assertEqual(expected, actual)

    def test_op_SVC_IN_long(self):
        mem = [
                casl2sim.Element(0xf000, 0),
                casl2sim.Element(0x0001, 0),
                casl2sim.Element(0x1000, 0),
                casl2sim.Element(0x1001, 0),
                casl2sim.Element(0x1002, 0),
                casl2sim.Element(0x1003, 0),
                casl2sim.Element(0x1004, 0),
                casl2sim.Element(0x1005, 0),
                casl2sim.Element(0x1006, 0),
                casl2sim.Element(0x1007, 0),
                casl2sim.Element(0x1008, 0),
                casl2sim.Element(0x1009, 0)]
        size = len(mem)
        expected = [m.value for m in mem]
        expected[4:9] = [ord("A"), ord("B"), ord("C"), ord("D"), ord("E")]
        c = casl2sim.Comet2(mem)
        c._inputf = io.StringIO("ABCDEFGH")
        c._gr[1] = 4
        c._gr[2] = 5
        elem = c.fetch()
        c.op_SVC(elem)
        actual = [m.value for m in c._mem[:size]]
        self.assertEqual(expected, actual)

    def test_op_SVC_OUT(self):
        mem = [
                casl2sim.Element(0xf000, 0),
                casl2sim.Element(0x0002, 0),
                casl2sim.Element(ord("X"), 0),
                casl2sim.Element(ord("X"), 0),
                casl2sim.Element(ord("t"), 0),
                casl2sim.Element(ord("e"), 0),
                casl2sim.Element(ord("s"), 0),
                casl2sim.Element(ord("t"), 0),
                casl2sim.Element(ord(" "), 0),
                casl2sim.Element(ord("O"), 0),
                casl2sim.Element(ord("U"), 0),
                casl2sim.Element(ord("T"), 0),
                casl2sim.Element(ord("Y"), 0),
                casl2sim.Element(ord("Y"), 0)]
        expected = "  OUT: test OUT\n"
        c = casl2sim.Comet2(mem)
        c._outputf = io.StringIO()
        c._gr[1] = 4
        c._gr[2] = 8
        elem = c.fetch()
        c.op_SVC(elem)
        actual = c._outputf.getvalue()
        self.assertEqual(expected, actual)
# End TestComet2

if __name__ == "__main__":
    unittest.main()
