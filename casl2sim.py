#!/usr/bin/env python3
# coding:utf-8
"""
CASL2シミュレータ
"""
import argparse
import collections
import random
import re
import sys


RE_LABEL = re.compile(r"([A-Za-z][A-Z0-9a-z]*)(.*)")
RE_OP = re.compile(r"\s+[A-Z].*")
RE_COMMENT = re.compile(r";.*")
RE_DC = re.compile(r"\s+DC\s+")
RE_DC_ARG = re.compile(r"('(''|[^'])+'|[0-9]+|#[0-9A-Fa-f]+|[A-Z][0-9A-Z]*)(.*)")

class Element:
    """
    メモリの1要素分のデータ構造
    """
    def __init__(self, v, l):
        # int 個の要素の値
        self.value = v
        # int (debug用) asmでの行番号を格納する asmと無関係または実行時に書き換えられた場合は0
        self.line = l

    def __str__(self):
        return f"(value={self.value:04x}, line={self.line})"

def err_exit(msg):
    print(f"Error: {msg}", file=sys.stderr)
    sys.exit(1)

class Parser:
    REG_NAME_LIST = ["GR0", "GR1", "GR2", "GR3", "GR4", "GR5", "GR6", "GR7"]

    def __init__(self):
        self._mem = []
        # 未解決のラベルを格納する要素を保持する {ラベル名(str):[格納先の要素(Element), ...]}
        # keyが重複した場合、リストに追加していく
        self._unresolved_labels = {}
        # ラベルの実際の値を保持する {ラベル名(str):実際の番地(int)}
        # keyが重複した場合、エラー
        self._actual_labels = {}
        # 予約語 レジスタ名
        for r in self.REG_NAME_LIST:
            self._actual_labels[r] = None
        # 未割当の定数を格納する要素を保持する {定数(int): [格納先の要素(Element), ...]}
        self._unresolved_consts = {}
        # 開始位置 (START疑似命令の指定先)
        self._start = 0
        self._start_label = None
        # 終了位置 (END疑似命令の位置)
        self._end = -1
        # 解析中の行番号
        self._line_num = 0

    def parse(self, inputf):
        for line in inputf:
            self._line_num += 1
            self._mem.extend(self.parse_line(line))
        if self._end < 0:
            err_exit("syntex error not found 'END'")
        if len(self._mem) > self._end:
            # ENDはプログラムの最後に記述する
            err_exit(f"syntax error: 'END' must be last")
        self.resolve_labels()
        self.resolve_consts()

    def get_mem(self):
        return self._mem[:]

    def get_start(self):
        return self._start

    def get_end(self):
        return self._end

    def add_unresolved_label(self, label, elem):
        if label not in self._unresolved_labels:
            self._unresolved_labels[label] = []
        self._unresolved_labels[label].append(elem)

    def set_actual_label(self, label, line_num):
        if label in self._actual_labels:
            err_exit(f"defined label ({self._line_num}: {label})")
        self._actual_labels[label] = line_num

    def add_unresolved_const(self, const, elem):
        if const not in self._unresolved_consts:
            self._unresolved_consts[const] = []
        self._unresolved_consts[const].append(elem)

    def resolve_labels(self):
        if self._start_label is not None:
            if self._start_label in self._actual_labels:
                err_exit(f"undefined label ({self._start_label})")
            self._start = self._actual_labels[self._start_label]
        for label, elemlist in self._unresolved_labels.items():
            if label not in self._actual_labels:
                err_exit(f"undefined label ({label})")
            addr = self._actual_labels[label]
            if addr is None:
                err_exit(f"reserved label ({label})")
            addr = addr & 0xffff
            for elem in elemlist:
                elem.value = addr

    def resolve_consts(self):
        for const, elemlist in self._unresolved_consts.items():
            self._mem.append(Element(const & 0xffff, 0))
            addr = (len(self._mem) - 1) & 0xffff
            for elem in elemlist:
                elem.value = addr

    def parse_line(self, line):
        """
        lineを解析する
        解析の結果追加されるメモリのリストを返す
        """
        line_ = re.sub(RE_COMMENT, "", line)[:-1]
        if len(line_.strip()) == 0:
            return []
        m = re.match(RE_LABEL, line_)
        if m is not None:
            self.set_actual_label(m.group(1), len(self._mem))
            line_ = m.group(2)
        m = re.match(RE_OP, line_)
        if m is None:
            err_exit(f"syntax error: bad format ({self._line_num})")
        tokens = line_.strip().split()
        op = tokens[0]
        if op == "DC":
            return self.parse_DC(line_)
        args = []
        if len(tokens) >= 2:
            for token in tokens[1:]:
                args.extend(token.split(","))
        macro = self.parse_macro(op, args)
        if macro is not None:
            return macro
        return self.parse_op(op, args)

    def parse_macro(self, op, args):
        if op == "IN":
            if len(args) != 2:
                err_exit(f"bad args ({self._line_num})")
            mem_part = self.parse_op("PUSH", ["0", "GR1"])
            mem_part.extend(self.parse_op("PUSH", ["0", "GR2"]))
            mem_part.extend(self.parse_op("LAD", ["GR1", args[0]]))
            mem_part.extend(self.parse_op("LAD", ["GR2", args[1]]))
            mem_part.extend(self.parse_op("SVC", [str(Comet2.SVC_OP_IN)]))
            mem_part.extend(self.parse_op("POP", ["GR2"]))
            mem_part.extend(self.parse_op("POP", ["GR1"]))
            return mem_part
        elif op == "OUT":
            if len(args) != 2:
                err_exit(f"bad args ({self._line_num})")
            mem_part = self.parse_op("PUSH", ["0", "GR1"])
            mem_part.extend(self.parse_op("PUSH", ["0", "GR2"]))
            mem_part.extend(self.parse_op("LAD", ["GR1", args[0]]))
            mem_part.extend(self.parse_op("LAD", ["GR2", args[1]]))
            mem_part.extend(self.parse_op("SVC", [str(Comet2.SVC_OP_OUT)]))
            mem_part.extend(self.parse_op("POP", ["GR2"]))
            mem_part.extend(self.parse_op("POP", ["GR1"]))
            return mem_part
        elif op == "RPUSH":
            if len(args) != 0:
                err_exit(f"bad args ({self._line_num})")
            mem_part = self.parse_op("PUSH", ["0", "GR1"])
            mem_part = self.parse_op("PUSH", ["0", "GR2"])
            mem_part = self.parse_op("PUSH", ["0", "GR3"])
            mem_part = self.parse_op("PUSH", ["0", "GR4"])
            mem_part = self.parse_op("PUSH", ["0", "GR5"])
            mem_part = self.parse_op("PUSH", ["0", "GR6"])
            mem_part = self.parse_op("PUSH", ["0", "GR7"])
            return mem_part
        elif op == "RPOP":
            if len(args) != 0:
                err_exit(f"bad args ({self._line_num})")
            mem_part.extend(self.parse_op("POP", ["GR7"]))
            mem_part.extend(self.parse_op("POP", ["GR6"]))
            mem_part.extend(self.parse_op("POP", ["GR5"]))
            mem_part.extend(self.parse_op("POP", ["GR4"]))
            mem_part.extend(self.parse_op("POP", ["GR3"]))
            mem_part.extend(self.parse_op("POP", ["GR2"]))
            mem_part.extend(self.parse_op("POP", ["GR1"]))
            return mem_part
        return None

    def parse_op(self, op, args):
        if op == "NOP":
            return self.mk_1word(0x00, 0, 0)
        elif op == "LD":
            return self.op_1or2word(0x14, 0x10, args)
        elif op == "ST":
            return self.op_2word(0x11, args)
        elif op == "LAD":
            return self.op_2word(0x12, args)
        elif op == "ADDA":
            return self.op_1or2word(0x24, 0x20, args)
        elif op == "SUBA":
            return self.op_1or2word(0x25, 0x21, args)
        elif op == "ADDL":
            return self.op_1or2word(0x26, 0x22, args)
        elif op == "SUBL":
            return self.op_1or2word(0x27, 0x23, args)
        elif op == "AND":
            return self.op_1or2word(0x34, 0x30, args)
        elif op == "OR":
            return self.op_1or2word(0x35, 0x31, args)
        elif op == "XOR":
            return self.op_1or2word(0x36, 0x32, args)
        elif op == "CPA":
            return self.op_1or2word(0x44, 0x40, args)
        elif op == "CPL":
            return self.op_1or2word(0x45, 0x41, args)
        elif op == "SLA":
            return self.op_2word(0x50, args)
        elif op == "SRA":
            return self.op_2word(0x51, args)
        elif op == "SLL":
            return self.op_2word(0x52, args)
        elif op == "SRL":
            return self.op_2word(0x53, args)
        elif op == "JMI":
            return self.op_2word(0x61, args, True)
        elif op == "JNZ":
            return self.op_2word(0x61, args, True)
        elif op == "JZE":
            return self.op_2word(0x61, args, True)
        elif op == "JUMP":
            return self.op_2word(0x61, args, True)
        elif op == "JPL":
            return self.op_2word(0x61, args, True)
        elif op == "JOV":
            return self.op_2word(0x61, args, True)
        elif op == "PUSH":
            return self.op_2word(0x70, args, True)
        elif op == "POP":
            opr1 = self.reg(args[0])
            return self.mk_1word(0x71, opr1, 0)
        elif op == "CALL":
            return self.op_2word(0x80, args, True)
        elif op == "RET":
            return self.mk_1word(0x81, 0, 0)
        elif op == "SVC":
            # 1 IN:   GR1(保存先アドレス) GR2(サイズ)
            # 2 OUT:  GR1(出力元アドレス) GR2(サイズ)
            adr = args[0]
            return self.mk_2word(0xf0, 0, adr, 0)
        elif op == "START":
            if len(self._mem) != 0:
                # STARTはプログラムの最初に記述する
                err_exit("syntax error: 'START' must be first")
            if len(args) != 0:
                self._start_label = args[0]
            else:
                self._start = len(self._mem)
            return []
        elif op == "END":
            self._end = len(self._mem)
            return []
        elif op == "DS":
            size = int(args[0])
            return [Element(0, self._line_num) for _ in range(size)]
        elif op == "DC":
            # not reached
            err_exit(f"internal error DC ({self._line_num})")
        err_exit(f"unknown operation ({self._line_num}: {op})")

    def parse_DC(self, line):
        args = re.sub(RE_DC, "", line)
        m = re.match(RE_DC_ARG, args)
        # 最低1つは引数がある前提
        arg = m.group(1)
        args = m.group(3).strip()
        mem_part = self.parse_DC_arg(arg)
        while len(args) != 0:
            if args[0] != ",":
                err_exit(f"syntax error: ',' ({self._line_num})")
            args = args[1:].strip()
            m = re.match(RE_DC_ARG, args)
            arg = m.group(1)
            args = m.group(3)
            mem_part.extend(self.parse_DC_arg(arg))
        return mem_part

    def parse_DC_arg(self, arg):
        ln = self._line_num
        mem_part = []
        if arg[0] == "'":
            # string
            st = arg[1:-1].replace("''", "'")
            for s in st:
                mem_part.append(Element(ord(s)&0xff, ln))
        elif arg[0] == "#":
            # hexadecimal
            mem_part.append(Element(int(arg[1:], 16), ln))
        elif arg[0].isdecimal():
            # decimal
            mem_part.append(Element(int(arg), ln))
        else:
            # label
            elem = Element(0, ln)
            self.add_unresolved_label(arg, elem)
            mem_part.append(elem)
        return mem_part

    def op_1or2word(self, op1word, op2word, args):
        opr1 = self.reg(args[0])
        if args[1] in self.REG_NAME_LIST:
            opr2 = self.reg(args[1])
            return self.mk_1word(op1word, opr1, opr2)
        opr2 = args[1]
        if len(args) <= 2:
            opr3 = 0
        else:
            opr3 = self.reg(args[2])
        return self.mk_2word(op2word, opr1, opr2, opr3)

    def op_1word(self, op, args):
        opr1 = 0
        opr2 = 0
        len_args = len(args)
        if len_args == 1:
            opr1 = self.reg(args[0])
        if len_args >= 2:
            opr2 = self.reg(args[1])
        return self.mk_1word(op, opr1, opr2)

    def op_2word(self, op, args, without_opr1=False):
        opr1 = 0
        opr2 = "0"
        opr3 = 0
        opr3_arg = None
        if args[0] in self.REG_NAME_LIST:
            if without_opr1:
                err_exit(f"syntax error: many reg arg ({self._line_num})")
            opr1 = self.reg(args[0])
            opr2 = args[1]
            if len(args) >3:
                opr3_arg = args[2]
        else:
            if not without_opr1:
                err_exit(f"syntax error: no reg arg ({self._line_num})")
            opr2 = args[0]
            if len(args) >= 2:
                opr3_arg = args[1]
        if opr3_arg is not None:
            opr3 = self.reg(opr3_arg)
        return self.mk_2word(op, opr1, opr2, opr3)

    zero = ord("0")
    def reg(self, regname):
        if regname not in self.REG_NAME_LIST:
            err_exit(f"no register name ({self._line_num}: {regname})")
        return ord(regname[2]) - self.zero

    def mk_1word(self, opcode, operand1, operand2):
        word = ((opcode & 0xff) << 8) | ((operand1 & 0xf) << 4) | (operand2 & 0xf)
        return [Element(word, self._line_num)]

    def mk_2word(self, opcode, operand1, operand2, operand3):
        word1 = ((opcode & 0xff) << 8) | ((operand1 & 0xf) << 4) | (operand3 & 0xf)
        elem1 = Element(word1, self._line_num)
        elem2 = Element(0, self._line_num)
        if operand2[0] == "=":
            self.add_unresolved_const(int(operand2[1:]), elem2)
        elif operand2.isdecimal():
            elem2.value = int(operand2)
        else:
            self.add_unresolved_label(operand2, elem2)
        return [elem1, elem2]
# End Parser

class Comet2:
    MEM_MAX = 0xFFFF
    REG_NUM = 8
    SVC_OP_IN = 1
    SVC_OP_OUT = 2

    def __init__(self, mem, init_mem_rand=False):
        self._gr = [0] * Comet2.REG_NUM
        self._pr = 0
        self._sp = 0
        self._zf = 0
        self._sf = 0
        self._of = 0
        self.init_mem(mem, init_mem_rand)
        self._inputf = None
        self._outputf = None
        self._debugf =None
        self.OP_TABLE = {
                0x10:self.op_LD, 0x11:self.op_ST, 0x12:self.op_LAD,
                0x14:self.op_LD_REG,
                0x20:self.op_ADDA, 0x21:self.op_SUBA, 0x22:self.op_ADDL,
                0x23:self.op_SUBL, 0x24:self.op_ADDA_REG,
                0x25:self.op_SUBA_REG, 0x26:self.op_ADDL_REG,
                0x27:self.op_SUBL_REG,
                0xf0:self.op_SVC}

    def init_mem(self, mem, init_mem_rand):
        self._mem = mem
        len_mem = len(self._mem)
        if len_mem == Comet2.MEM_MAX:
            return
        if len_mem > Comet2.MEM_MAX:
            err_exit("memory over")
        if init_mem_rand:
            padding = [Element(0, random.randint(0, 0xffff)) for _ in range(Comet2.MEM_MAX - len_mem)]
        else:
            padding = [Element(0, 0) for _ in range(Comet2.MEM_MAX - len_mem)]
        self._mem.extend(padding)

    def init_regs(self, grlist, sp, zf, sf, of):
        if len(grlist) != Comet2.REG_NUM:
            err_exit("internal error grlist")
        self._gr = [gr&0xffff for gr in grlist]
        self._sp = sp & 0xffff
        self._zf = int(zf != 0)
        self._sf = int(sf != 0)
        self._of = int(of != 0)

    def run(self, start, end, outputf=None, debugf=None, inputf=None):
        self._outputf = outputf
        self._debugf = debugf
        self._inputf = inputf
        self._pr = start
        while self._pr != end:
            self.operate_once()

    def operate_once(self):
        elem = self.fetch()
        op = (elem.value & 0xff00) >> 8
        if op not in self.OP_TABLE:
            err_exit(f"unknown operation ([{self._pr - 1:04x}]: {elem.value:04x})")
        op_func = self.OP_TABLE[op]
        op_func(elem)

    def output_debug(self, line_num, msg):
        if self._debugf is None:
            return
        if line_num == 0:
            lstr = "L-:"
        else:
            lstr = f"L{line_num}:"
        self._debugf.write(f"{lstr} {msg}\n")

    def output(self, msg):
        if self._outputf is None:
            return
        self._outputf.write(f"OUT: {msg}\n")

    def get_gr(self, n):
        if n < 0 or Comet2.REG_NUM <= n:
            err_exit("GR index out of range")
        return self._gr[n]

    def set_gr(self, n, val):
        if n < 0 or Comet2.REG_NUM <= n:
            err_exit("GR index out of range")
        self._gr[n] = val & 0xffff

    def get_mem(self, adr):
        if adr < 0 or Comet2.MEM_MAX <= adr:
            err_exit("MEM address out of range")
        return self._mem[adr].value

    def set_mem(self, adr, val):
        if adr < 0 or Comet2.MEM_MAX <= adr:
            err_exit("MEM address out of range")
        self._mem[adr].value = val & 0xffff

    def fetch(self):
        m = self._mem[self._pr&0xffff]
        self._pr = (self._pr + 1) & 0xffff
        return m

    def decode_1word(self, code):
        op = (code & 0xff00) >> 8
        opr1 = (code & 0x00f0) >> 4
        opr2 = (code & 0x000f)
        return (op, opr1, opr2)

    def decode_2word(self, code1, code2):
        op = (code1 & 0xff00) >> 8
        opr1 = (code1 & 0x00f0) >> 4
        opr2 = code2
        opr3 = (code1 & 0x000f)
        return (op, opr1, opr2, opr3)

    def get_reg_adr(self, elem):
        code1 = elem.value
        elem2 = self.fetch()
        code2 = elem2.value
        _, opr1, opr2, opr3 = self.decode_2word(code1, code2)
        adr = opr2
        if opr3 != 0:
            adr += self.get_gr(opr3)
        return (opr1, adr)

    def op_LD(self, elem):
        reg, adr = self.get_reg_adr(elem)
        val = self.get_mem(adr)
        self._zf = int(val == 0)
        self._sf = (val&0x8000) >> 15
        self.set_gr(reg, val)
        self.output_debug(elem.line,
                f"GR{reg} <- MEM[{adr:04x}]={val:04x} (ZF <- {self._zf}, SF <- {self._sf})")

    def op_ST(self, elem):
        reg, adr = self.get_reg_adr(elem)
        val = self.get_gr(reg)
        self.set_mem(adr, val)
        self.output_debug(elem.line, f"MEM[{adr:04x}] <- GR{reg}={val:04x}")

    def op_LAD(self, elem):
        reg, adr = self.get_reg_adr(elem)
        self.set_gr(reg, adr)
        self.output_debug(elem.line, f"GR{reg} <- {adr:04x}")

    def op_LD_REG(self, elem):
        code = elem.value
        _, reg1, reg2 = self.decode_1word(code)
        val = self.get_gr(reg2)
        self._zf = int(val == 0)
        self._sf = (val&0x8000) >> 15
        self.set_gr(reg1, val)
        self.output_debug(elem.line, f"GR{reg1} <- GR{reg2}={val:04x} (ZF <- {self._zf}, SF <- {self._sf})")

    def op_ADDA(self, elem):
        reg, adr = self.get_reg_adr(elem)
        v1 = self.get_gr(reg)
        v2 = self.get_mem(adr)
        r = (v1 + v2) & 0xffff
        sv1 = v1 & 0x8000
        sv2 = v2 & 0x8000
        sr = r & 0x8000
        self._zf = int(r == 0)
        self._sf = sr >> 15
        self._of = ((~(sv1 ^ sv2)) & (sv1 ^ sr)) >> 15
        self.set_gr(reg, r)
        self.output_debug(elem.line,
                f"GR{reg} <- {r:04x} <GR{reg}={v1:04x} + MEM[{adr:04x}]={v2:04x}> " +
                f"(ZF <- {self._zf}, SF <- {self._sf}, OF <- {self._of})")

    def op_SUBA(self, elem):
        pass

    def op_ADDL(self, elem):
        pass

    def op_SUBL(self, elem):
        pass

    def op_ADDA_REG(self, elem):
        code = elem.value
        _, reg1, reg2 = self.decode_1word(code)
        v1 = self.get_gr(reg1)
        v2 = self.get_gr(reg2)
        r = v1 + v2
        sv1 = v1 & 0x8000
        sv2 = v2 & 0x8000
        sr = r & 0x8000
        self._zf = int(r == 0)
        self._sf = sr >> 15
        self._of = ((~(sv1 ^ sv2)) & (sv1 ^ sr)) >> 15
        self.set_gr(reg1, r)
        self.output_debug(elem.line,
                f"GR{reg1} <- {r:04x} <GR{reg1}={v1:04x} + GR{reg2}={v2:04x}> " +
                f"(ZF <- {self._zf}, SF <- {self._sf}, OF <- {self._of})")

    def op_SUBA_REG(self, elem):
        pass

    def op_ADDL_REG(self, elem):
        pass

    def op_SUBL_REG(self, elem):
        pass



    def op_SVC(self, elem):
        elem2 = self.fetch()
        code2 = elem2.value
        if code2 == Comet2.SVC_OP_IN:
            self.op_SVC_IN(elem)
        elif code2 == Comet2.SVC_OP_OUT:
            self.op_SVC_OUT(elem)
        else:
            err_exit(f"not implemented 'SVC {code2:04x}'")

    def op_SVC_IN(self, elem):
        if self._inputf is None:
            err_exit(f"no input source")
        start = self.get_gr(1)
        end = start + self.get_gr(2)
        self.output_debug(elem.line, "SVC IN")
        empty_f = False
        # 入力が足りない場合、0で埋める
        for adr in range(start, end):
            adr = adr & Comet2.MEM_MAX
            if not empty_f:
                instr = self._inputf.read(1)
                if instr == "":
                    empty_f = True
                    d = 0
                else:
                    d = ord(instr) & 0xff
            else:
                d = 0
            self.set_mem(adr, d)
            self.output_debug(elem.line, f"IN: MEM[{adr:04x}] <- {d:04x}")

    def op_SVC_OUT(self, elem):
        msg = []
        start = self.get_gr(1)
        end = start + self.get_gr(2)
        for adr in range(start, end):
            adr = adr & Comet2.MEM_MAX
            msg.append(self.get_mem(adr)&0xff)
        self.output_debug(elem.line, "SVC OUT")
        self.output(self.to_str(msg))

    def to_str(self, ilist):
        # TODO ASCIIのみ (本来対応する文字コードはJIS X 0201)
        return "".join([chr(i) for i in ilist])
# End Comet2


def base_int(nstr):
    return int(nstr, 0)

class Stdout:
    def __enter__(self):
        return sys.stdout
    def __exit__(self, typ, val, trace):
        pass
# End Stdout

class Stdin:
    def __enter__(self):
        return sys.stdin
    def __exit__(self, typ, val, trace):
        pass
# End Stdin

def main():
    parser = argparse.ArgumentParser(
            description=__doc__,
            formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("asmfile", help="casl2 code")
    parser.add_argument("--input-src", help="casl2での入力時の入力元", metavar="file")
    parser.add_argument("--output", help="casl2での出力先", metavar="file")
    parser.add_argument("--output-debug", help="casl2でのデバッグ出力先", metavar="file")
    parser.add_argument("--emit-bin", action="store_true", help="アセンブル後のバイナリを出力して終了する")
    parser.add_argument("--rand-mem", action="store_true", help="値が未指定のメモリを乱数で初期化する")
    parser.add_argument("--rand-seed", type=int, help="乱数のシード値", metavar="seed")
    parser.add_argument("--set-gr0", type=base_int, default=0, help="GR0の初期値", metavar="n")
    parser.add_argument("--set-gr1", type=base_int, default=0, help="GR1の初期値", metavar="n")
    parser.add_argument("--set-gr2", type=base_int, default=0, help="GR2の初期値", metavar="n")
    parser.add_argument("--set-gr3", type=base_int, default=0, help="GR3の初期値", metavar="n")
    parser.add_argument("--set-gr4", type=base_int, default=0, help="GR4の初期値", metavar="n")
    parser.add_argument("--set-gr5", type=base_int, default=0, help="GR5の初期値", metavar="n")
    parser.add_argument("--set-gr6", type=base_int, default=0, help="GR6の初期値", metavar="n")
    parser.add_argument("--set-gr7", type=base_int, default=0, help="GR7の初期値", metavar="n")
    parser.add_argument("--set-sp", type=base_int, default=Comet2.MEM_MAX, help="SPの初期値", metavar="n")
    parser.add_argument("--set-zf", type=base_int, default=0, help="FR(zero flag)の初期値", metavar="n")
    parser.add_argument("--set-sf", type=base_int, default=0, help="FR(sign flag)の初期値", metavar="n")
    parser.add_argument("--set-of", type=base_int, default=0, help="FR(overflow flag)の初期値", metavar="n")

    # レジスタ、メモリの値はデフォルトでは0

    args = parser.parse_args()

    if args.rand_seed is not None:
        random.seed(args.rand_seed)

    p = Parser()
    with open(args.asmfile) as f:
        p.parse(f)
    mem = p.get_mem()
    start = p.get_start()
    end = p.get_end()

    if args.emit_bin:
        width = 8
        for i in range(len(mem)):
            rest = i % width
            if rest == 0:
                print(f"[{i:04x}]:", end="")
            print(f" {mem[i].value:04x}", end="")
            if rest == width - 1:
                print("")
        if len(mem) % width != 0:
            print("")
        return

    c = Comet2(mem, args.rand_mem)
    grlist = [args.set_gr0, args.set_gr1, args.set_gr2, args.set_gr3,
            args.set_gr4, args.set_gr5, args.set_gr6, args.set_gr7]
    c.init_regs(grlist, args.set_sp, args.set_zf, args.set_sf, args.set_of)
    with open(args.output, "w") if args.output else Stdout() as fo:
        eq_output = args.output_debug == args.output
        with fo if eq_output else open(args.output_debug, "w") if args.output_debug else Stdout() as fd:
                with open(args.input_src) if args.input_src else Stdin() as fi:
                    c.run(start, end, fo, fd, fi)

if __name__ == "__main__":
    main()
