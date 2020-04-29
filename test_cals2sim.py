#!/usr/bin/env python3
# coding:utf-8
import unittest
import casl2sim
import sys


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
        elem = c.get_pr_inc()
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
        elem = c.get_pr_inc()
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
        elem = c.get_pr_inc()
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
        elem = c.get_pr_inc()
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
        elem = c.get_pr_inc()
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
        elem = c.get_pr_inc()
        c.op_LAD(elem)
        self.assertEqual(expected, c._gr)

    def test_op_LD_REG(self):
        mem = [
                casl2sim.Element(0x1415, 0)]
        c = casl2sim.Comet2(mem)
        c._gr[5] = 23
        expected = c._gr[:]
        expected[1] = c._gr[5]
        elem = c.get_pr_inc()
        c.op_LD_REG(elem)
        self.assertEqual(expected, c._gr)


# End TestComet2

if __name__ == "__main__":
    unittest.main()
