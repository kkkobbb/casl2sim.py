#!/usr/bin/env python3
# coding:utf-8
"""
CASL2シミュレータ

STARTの位置から開始し、
ENDの位置に来た時終了する
"""
import argparse
import contextlib
import re
import sys


RE_LABEL = re.compile(r"([A-Za-z][A-Z0-9a-z]*)(.*)") # 本来は大文字、数字のみ
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
# End Element

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
            self.err_exit("syntax error [not found 'END']")
        if len(self._mem) > self._end:
            # ENDはプログラムの最後に記述する
            self.err_exit(f"syntax error ['END' must be last]")
        self.resolve_labels()
        self.resolve_consts()

    def err_exit(self, msg):
        print(f"Assemble Error: {msg}", file=sys.stderr)
        sys.exit(1)

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
            self.err_exit(f"defined label (L{self._line_num}: {label})")
        self._actual_labels[label] = line_num

    def add_unresolved_const(self, const, elem):
        if const not in self._unresolved_consts:
            self._unresolved_consts[const] = []
        self._unresolved_consts[const].append(elem)

    def resolve_labels(self):
        if self._start_label is not None:
            if self._start_label in self._actual_labels:
                self.err_exit(f"undefined label ({self._start_label})")
            self._start = self._actual_labels[self._start_label]
        for label, elemlist in self._unresolved_labels.items():
            if label not in self._actual_labels:
                self.err_exit(f"undefined label ({label})")
            addr = self._actual_labels[label] & 0xffff
            if addr is None:
                self.err_exit(f"reserved label ({label})")
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
        if re.match(RE_OP, line_) is None:
            self.err_exit(f"syntax error [bad format] (L{self._line_num})")
        tokens = line_.strip().split()
        op = tokens[0]
        if op == "DC":
            return self.parse_DC(line_)
        args = []
        for token in tokens[1:]:
            args.extend(token.split(","))
        macro = self.parse_macro(op, args)
        if macro is not None:
            return macro
        return self.parse_op(op, args)

    def parse_macro(self, op, args):
        mem_part = None
        if op == "IN":
            if len(args) != 2:
                self.err_exit(f"bad args (L{self._line_num})")
            mem_part = self.parse_op("PUSH", ["0", "GR1"])
            mem_part.extend(self.parse_op("PUSH", ["0", "GR2"]))
            mem_part.extend(self.parse_op("LAD", ["GR1", args[0]]))
            mem_part.extend(self.parse_op("LAD", ["GR2", args[1]]))
            mem_part.extend(self.parse_op("SVC", [str(Comet2.SVC_OP_IN)]))
            mem_part.extend(self.parse_op("POP", ["GR2"]))
            mem_part.extend(self.parse_op("POP", ["GR1"]))
        elif op == "OUT":
            if len(args) != 2:
                self.err_exit(f"bad args (L{self._line_num})")
            mem_part = self.parse_op("PUSH", ["0", "GR1"])
            mem_part.extend(self.parse_op("PUSH", ["0", "GR2"]))
            mem_part.extend(self.parse_op("LAD", ["GR1", args[0]]))
            mem_part.extend(self.parse_op("LAD", ["GR2", args[1]]))
            mem_part.extend(self.parse_op("SVC", [str(Comet2.SVC_OP_OUT)]))
            mem_part.extend(self.parse_op("POP", ["GR2"]))
            mem_part.extend(self.parse_op("POP", ["GR1"]))
        elif op == "RPUSH":
            if len(args) != 0:
                self.err_exit(f"bad args (L{self._line_num})")
            mem_part = self.parse_op("PUSH", ["0", "GR1"])
            mem_part.extend(self.parse_op("PUSH", ["0", "GR2"]))
            mem_part.extend(self.parse_op("PUSH", ["0", "GR3"]))
            mem_part.extend(self.parse_op("PUSH", ["0", "GR4"]))
            mem_part.extend(self.parse_op("PUSH", ["0", "GR5"]))
            mem_part.extend(self.parse_op("PUSH", ["0", "GR6"]))
            mem_part.extend(self.parse_op("PUSH", ["0", "GR7"]))
        elif op == "RPOP":
            if len(args) != 0:
                self.err_exit(f"bad args (L{self._line_num})")
            mem_part = self.parse_op("POP", ["GR7"])
            mem_part.extend(self.parse_op("POP", ["GR6"]))
            mem_part.extend(self.parse_op("POP", ["GR5"]))
            mem_part.extend(self.parse_op("POP", ["GR4"]))
            mem_part.extend(self.parse_op("POP", ["GR3"]))
            mem_part.extend(self.parse_op("POP", ["GR2"]))
            mem_part.extend(self.parse_op("POP", ["GR1"]))
        return mem_part

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
            return self.op_2word(0x62, args, True)
        elif op == "JZE":
            return self.op_2word(0x63, args, True)
        elif op == "JUMP":
            return self.op_2word(0x64, args, True)
        elif op == "JPL":
            return self.op_2word(0x65, args, True)
        elif op == "JOV":
            return self.op_2word(0x66, args, True)
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
            return self.mk_2word(0xf0, 0, args[0], 0)
        elif op == "START":
            if len(self._mem) != 0:
                # STARTはプログラムの最初に記述する
                self.err_exit("syntax error ['START' must be first]")
            if len(args) != 0:
                self._start_label = args[0]
            else:
                self._start = len(self._mem)
            return []
        elif op == "END":
            self._end = len(self._mem)
            return []
        elif op == "DS":
            return [Element(0, self._line_num) for _ in range(int(args[0]))]
        elif op == "DC":
            # not reached
            self.err_exit(f"internal error DC (L{self._line_num})")
        self.err_exit(f"unknown operation (L{self._line_num}: {op})")

    def parse_DC(self, line):
        args = re.sub(RE_DC, "", line)
        m = re.match(RE_DC_ARG, args)
        # 最低1つは引数がある前提
        arg = m.group(1)
        args = m.group(3).strip()
        mem_part = self.parse_DC_arg(arg)
        while len(args) != 0:
            if args[0] != ",":
                self.err_exit(f"syntax error [','] (L{self._line_num})")
            args = args[1:].strip()
            m = re.match(RE_DC_ARG, args)
            arg, _, args = m.groups()
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
                self.err_exit(f"syntax error [too many register arg] (L{self._line_num})")
            opr1 = self.reg(args[0])
            opr2 = args[1]
            if len(args) >= 3:
                opr3_arg = args[2]
        else:
            if not without_opr1:
                self.err_exit(f"syntax error [no register arg] (L{self._line_num})")
            opr2 = args[0]
            if len(args) >= 2:
                opr3_arg = args[1]
        if opr3_arg is not None:
            opr3 = self.reg(opr3_arg)
        return self.mk_2word(op, opr1, opr2, opr3)

    def reg(self, regname):
        if regname not in self.REG_NAME_LIST:
            self.err_exit(f"bad register name (L{self._line_num}: {regname})")
        return ord(regname[2]) - ord("0")

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
    ADR_MAX = 0xffff
    REG_NUM = 8
    REG_BITS = 16
    SVC_OP_IN = 1
    SVC_OP_OUT = 2

    def __init__(self, mem, print_regs=False):
        self._gr = [0] * Comet2.REG_NUM
        self._pr = 0
        self._sp = 0
        self._zf = 0
        self._sf = 0
        self._of = 0
        self.init_mem(mem)
        self._inputf = None
        self._outputf = None
        self._debugf =None
        self.OP_TABLE = {
                0x00:self.op_NOP,
                0x10:self.op_LD, 0x11:self.op_ST, 0x12:self.op_LAD,
                0x14:self.op_LD_REG,
                0x20:self.op_ADDA, 0x21:self.op_SUBA, 0x22:self.op_ADDL,
                0x23:self.op_SUBL, 0x24:self.op_ADDA_REG,
                0x25:self.op_SUBA_REG, 0x26:self.op_ADDL_REG,
                0x27:self.op_SUBL_REG,
                0x30:self.op_AND, 0x31:self.op_OR, 0x32:self.op_XOR,
                0x34:self.op_AND_REG, 0x35:self.op_OR_REG,
                0x36:self.op_XOR_REG,
                0x40:self.op_CPA, 0x41:self.op_CPL, 0x44:self.op_CPA_REG,
                0x45:self.op_CPL_REG,
                0x50:self.op_SLA, 0x51:self.op_SRA, 0x52:self.op_SLL,
                0x53:self.op_SRL,
                0x61:self.op_JMI, 0x62:self.op_JNZ, 0x63:self.op_JZE,
                0x64:self.op_JUMP, 0x65:self.op_JPL, 0x66:self.op_JOV,
                0x70:self.op_PUSH, 0x71:self.op_POP,
                0x80:self.op_CALL, 0x81:self.op_RET,
                0xf0:self.op_SVC}
        self._print_regs = print_regs

    def init_mem(self, mem):
        self._mem = mem
        len_mem = len(self._mem)
        len_max = Comet2.ADR_MAX + 1
        if len_mem == len_max:
            return
        if len_mem > len_max:
            self.err_exit("memory over")
        else:
            self._mem.extend([Element(0, 0) for _ in range(len_max - len_mem)])

    def init_regs(self, grlist=[0,0,0,0,0,0,0,0], pr=0, sp=0, zf=0, sf=0, of=0):
        if len(grlist) != Comet2.REG_NUM:
            self.err_exit("internal error grlist")
        self._gr = [gr&0xffff for gr in grlist]
        self._pr = pr & 0xffff
        self._sp = sp & 0xffff
        self._zf = int(zf != 0)
        self._sf = int(sf != 0)
        self._of = int(of != 0)

    def run(self, start, end, outputf=None, debugf=None, inputf=None, virtual_call=False):
        self._outputf = outputf
        self._debugf = debugf
        self._inputf = inputf
        self._pr = start & 0xffff
        end = end & 0xffff
        self.output_regs()
        if virtual_call:
            self._sp = (self._sp - 1) & 0xffff
            self._mem[self._sp].value = end
            if self._debugf is not None:
                self._debugf.write("VCALL: " +
                        f"MEM[{self._sp:04x}] <- {end:04x} (SP <- {self._sp:04x})\n")
        while self._pr != end:
            self.run_once()
        self.output_regs()

    def run_once(self):
        elem = self.fetch()
        op = (elem.value & 0xff00) >> 8
        if op not in self.OP_TABLE:
            lstr = "" if elem.line == 0 else f"L{elem.line} "
            self.err_exit(f"unknown operation ({lstr}[{self._pr - 1:04x}]: {elem.value:04x})")
        self.OP_TABLE[op](elem)

    def err_exit(self, msg):
        print(f"Runtime Error: {msg}", file=sys.stderr)
        self.output_regs()
        sys.exit(1)

    def output_debug(self, line_num, msg):
        if self._debugf is None:
            return
        lstr = "--:" if line_num == 0 else f"L{line_num}:"
        self._debugf.write(f"{lstr:>6} {msg}\n")

    def output(self, msg):
        if self._outputf is None:
            return
        self._outputf.write(f"  OUT: {msg}\n")

    def output_regs(self):
        if not self._print_regs:
            return
        grlist = " ".join([f"GR{i}={gr:04x}" for i, gr in enumerate(self._gr)])
        self._debugf.write("\nREG LIST\n")
        self._debugf.write(f"  {grlist}\n")
        self._debugf.write(f"  PR={self._pr:04x} SP={self._sp:04x} ")
        self._debugf.write(f"ZF={self._zf} SF={self._sf} OF={self._of}\n\n")

    def get_gr(self, n):
        if n < 0 or Comet2.REG_NUM <= n:
            self.err_exit("GR index out of range")
        return self._gr[n]

    def set_gr(self, n, val):
        if n < 0 or Comet2.REG_NUM <= n:
            self.err_exit("GR index out of range")
        self._gr[n] = val & 0xffff

    def get_mem(self, adr):
        if adr < 0 or Comet2.ADR_MAX < adr:
            self.err_exit("MEM address out of range")
        return self._mem[adr].value

    def set_mem(self, adr, val):
        if adr < 0 or Comet2.ADR_MAX < adr:
            self.err_exit("MEM address out of range")
        self._mem[adr].value = val & 0xffff
        self._mem[adr].line = 0

    def fetch(self):
        m = self._mem[self._pr&0xffff]
        self._pr = (self._pr + 1) & 0xffff
        return m

    @staticmethod
    def decode_1word(code):
        return ((code&0xff00)>>8, (code&0x00f0)>>4, (code&0x000f))

    @staticmethod
    def decode_2word(code1, code2):
        return ((code1&0xff00)>>8, (code1&0x00f0)>>4, code2, (code1&0x000f))

    def get_reg_adr(self, elem):
        code1 = elem.value
        code2 = self.fetch().value
        _, opr1, opr2, opr3 = Comet2.decode_2word(code1, code2)
        adr = opr2 if opr3 == 0 else opr2 + self.get_gr(opr3)
        return (opr1, adr&0xffff)

    def op_NOP(self, elem):
        self.output_debug(elem.line, "NOP")

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
        _, reg1, reg2 = Comet2.decode_1word(elem.value)
        val = self.get_gr(reg2)
        self._zf = int(val == 0)
        self._sf = (val&0x8000) >> 15
        self.set_gr(reg1, val)
        self.output_debug(elem.line, f"GR{reg1} <- GR{reg2}={val:04x} (ZF <- {self._zf}, SF <- {self._sf})")

    def add_flag(self, v1, v2, arithmetic=True):
        r = v1 + v2
        self._zf = int(r == 0)
        if arithmetic:
            sr = r & 0x8000
            sv1 = v1 & 0x8000
            sv2 = v2 & 0x8000
            self._sf = sr >> 15
            self._of = ((~(sv1 ^ sv2)) & (sv1 ^ sr)) >> 15
        else:
            self._sf = 0
            self._of = int(r > 0xffff)
        return r & 0xffff

    def sub_flag(self, v1, v2, arithmetic=True):
        r = v1 - v2
        self._zf = int(r == 0)
        if arithmetic:
            sr = r & 0x8000
            sv1 = v1 & 0x8000
            sv2 = v2 & 0x8000
            self._sf = sr >> 15
            self._of = ((sv1 ^ sv2) & (sv1 ^ sr)) >> 15
        else:
            self._sf = 0
            self._of = int(v1 < v2)
        return r & 0xffff

    def op_ADDA(self, elem):
        reg, adr = self.get_reg_adr(elem)
        v1 = self.get_gr(reg)
        v2 = self.get_mem(adr)
        r = self.add_flag(v1, v2)
        self.set_gr(reg, r)
        self.output_debug(elem.line,
                f"GR{reg} <- {r:04x} <GR{reg}={v1:04x} + MEM[{adr:04x}]={v2:04x}> " +
                f"(ZF <- {self._zf}, SF <- {self._sf}, OF <- {self._of})")

    def op_SUBA(self, elem):
        reg, adr = self.get_reg_adr(elem)
        v1 = self.get_gr(reg)
        v2 = self.get_mem(adr)
        r = self.sub_flag(v1, v2)
        self.set_gr(reg, r)
        self.output_debug(elem.line,
                f"GR{reg} <- {r:04x} <GR{reg}={v1:04x} - MEM[{adr:04x}]={v2:04x}> " +
                f"(ZF <- {self._zf}, SF <- {self._sf}, OF <- {self._of})")

    def op_ADDL(self, elem):
        reg, adr = self.get_reg_adr(elem)
        v1 = self.get_gr(reg)
        v2 = self.get_mem(adr)
        r = self.add_flag(v1, v2, False)
        self.set_gr(reg, r)
        self.output_debug(elem.line,
                f"GR{reg} <- {r:04x} <GR{reg}={v1:04x} +L MEM[{adr:04x}]={v2:04x}> " +
                f"(ZF <- {self._zf}, SF <- {self._sf}, OF <- {self._of})")

    def op_SUBL(self, elem):
        reg, adr = self.get_reg_adr(elem)
        v1 = self.get_gr(reg)
        v2 = self.get_mem(adr)
        r = self.sub_flag(v1, v2, False)
        self.set_gr(reg, r)
        self.output_debug(elem.line,
                f"GR{reg} <- {r:04x} <GR{reg}={v1:04x} -L MEM[{adr:04x}]={v2:04x}> " +
                f"(ZF <- {self._zf}, SF <- {self._sf}, OF <- {self._of})")

    def op_ADDA_REG(self, elem):
        _, reg1, reg2 = Comet2.decode_1word(elem.value)
        v1 = self.get_gr(reg1)
        v2 = self.get_gr(reg2)
        r = self.add_flag(v1, v2)
        self.set_gr(reg1, r)
        self.output_debug(elem.line,
                f"GR{reg1} <- {r:04x} <GR{reg1}={v1:04x} + GR{reg2}={v2:04x}> " +
                f"(ZF <- {self._zf}, SF <- {self._sf}, OF <- {self._of})")

    def op_SUBA_REG(self, elem):
        _, reg1, reg2 = Comet2.decode_1word(elem.value)
        v1 = self.get_gr(reg1)
        v2 = self.get_gr(reg2)
        r = self.sub_flag(v1, v2)
        self.set_gr(reg1, r)
        self.output_debug(elem.line,
                f"GR{reg1} <- {r:04x} <GR{reg1}={v1:04x} - GR{reg2}={v2:04x}> " +
                f"(ZF <- {self._zf}, SF <- {self._sf}, OF <- {self._of})")

    def op_ADDL_REG(self, elem):
        _, reg1, reg2 = Comet2.decode_1word(elem.value)
        v1 = self.get_gr(reg1)
        v2 = self.get_gr(reg2)
        r = self.add_flag(v1, v2, False)
        self.set_gr(reg1, r)
        self.output_debug(elem.line,
                f"GR{reg1} <- {r:04x} <GR{reg1}={v1:04x} +L GR{reg2}={v2:04x}> " +
                f"(ZF <- {self._zf}, SF <- {self._sf}, OF <- {self._of})")

    def op_SUBL_REG(self, elem):
        _, reg1, reg2 = Comet2.decode_1word(elem.value)
        v1 = self.get_gr(reg1)
        v2 = self.get_gr(reg2)
        r = self.sub_flag(v1, v2, False)
        self.set_gr(reg1, r)
        self.output_debug(elem.line,
                f"GR{reg1} <- {r:04x} <GR{reg1}={v1:04x} -L GR{reg2}={v2:04x}> " +
                f"(ZF <- {self._zf}, SF <- {self._sf}, OF <- {self._of})")

    def bit_flag(self, op, v1, v2):
        r = op(v1, v2)
        self._zf = int(r == 0)
        self._sf = 0
        self._of = 0
        return r & 0xffff

    def op_AND(self, elem):
        reg, adr = self.get_reg_adr(elem)
        v1 = self.get_gr(reg)
        v2 = self.get_mem(adr)
        r = self.bit_flag(lambda v1, v2: v1 & v2, v1, v2)
        self.set_gr(reg, r)
        self.output_debug(elem.line,
                f"GR{reg} <- {r:04x} <GR{reg}={v1:04x} & MEM[{adr:04x}]={v2:04x}> " +
                f"(ZF <- {self._zf}, SF <- {self._sf}, OF <- {self._of})")

    def op_OR(self, elem):
        reg, adr = self.get_reg_adr(elem)
        v1 = self.get_gr(reg)
        v2 = self.get_mem(adr)
        r = self.bit_flag(lambda v1, v2: v1 | v2, v1, v2)
        self.set_gr(reg, r)
        self.output_debug(elem.line,
                f"GR{reg} <- {r:04x} <GR{reg}={v1:04x} | MEM[{adr:04x}]={v2:04x}> " +
                f"(ZF <- {self._zf}, SF <- {self._sf}, OF <- {self._of})")

    def op_XOR(self, elem):
        reg, adr = self.get_reg_adr(elem)
        v1 = self.get_gr(reg)
        v2 = self.get_mem(adr)
        r = self.bit_flag(lambda v1, v2: v1 ^ v2, v1, v2)
        self.set_gr(reg, r)
        self.output_debug(elem.line,
                f"GR{reg} <- {r:04x} <GR{reg}={v1:04x} ^ MEM[{adr:04x}]={v2:04x}> " +
                f"(ZF <- {self._zf}, SF <- {self._sf}, OF <- {self._of})")

    def op_AND_REG(self, elem):
        _, reg1, reg2 = Comet2.decode_1word(elem.value)
        v1 = self.get_gr(reg1)
        v2 = self.get_gr(reg2)
        r = self.bit_flag(lambda v1, v2: v1 & v2, v1, v2)
        self.set_gr(reg1, r)
        self.output_debug(elem.line,
                f"GR{reg1} <- {r:04x} <GR{reg1}={v1:04x} & GR{reg2}={v2:04x}> " +
                f"(ZF <- {self._zf}, SF <- {self._sf}, OF <- {self._of})")

    def op_OR_REG(self, elem):
        _, reg1, reg2 = Comet2.decode_1word(elem.value)
        v1 = self.get_gr(reg1)
        v2 = self.get_gr(reg2)
        r = self.bit_flag(lambda v1, v2: v1 | v2, v1, v2)
        self.set_gr(reg1, r)
        self.output_debug(elem.line,
                f"GR{reg1} <- {r:04x} <GR{reg1}={v1:04x} | GR{reg2}={v2:04x}> " +
                f"(ZF <- {self._zf}, SF <- {self._sf}, OF <- {self._of})")

    def op_XOR_REG(self, elem):
        _, reg1, reg2 = Comet2.decode_1word(elem.value)
        v1 = self.get_gr(reg1)
        v2 = self.get_gr(reg2)
        r = self.bit_flag(lambda v1, v2: v1 ^ v2, v1, v2)
        self.set_gr(reg1, r)
        self.output_debug(elem.line,
                f"GR{reg1} <- {r:04x} <GR{reg1}={v1:04x} ^ GR{reg2}={v2:04x}> " +
                f"(ZF <- {self._zf}, SF <- {self._sf}, OF <- {self._of})")

    @staticmethod
    def expand_bit(v):
        return v if (v & 0x8000) == 0 else -1 * (((~v) + 1) & 0xffff)

    def cmp_flag(self, v1, v2, arithmetic=True):
        self._of = 0
        if v1 == v2:
            self._zf = 1
            self._sf = 0
            return
        self._zf = 0
        if arithmetic:
            self._sf = int(Comet2.expand_bit(v1) < Comet2.expand_bit(v2))
        else:
            self._sf = int(v1 < v2)

    def op_CPA(self, elem):
        reg, adr = self.get_reg_adr(elem)
        v1 = self.get_gr(reg)
        v2 = self.get_mem(adr)
        self.cmp_flag(v1, v2)
        self.output_debug(elem.line,
                f"<GR{reg}={v1:04x} - MEM[{adr:04x}]={v2:04x}> " +
                f"(ZF <- {self._zf}, SF <- {self._sf}, OF <- {self._of})")

    def op_CPL(self, elem):
        reg, adr = self.get_reg_adr(elem)
        v1 = self.get_gr(reg)
        v2 = self.get_mem(adr)
        self.cmp_flag(v1, v2, False)
        self.output_debug(elem.line,
                f"<GR{reg}={v1:04x} -L MEM[{adr:04x}]={v2:04x}> " +
                f"(ZF <- {self._zf}, SF <- {self._sf}, OF <- {self._of})")

    def op_CPA_REG(self, elem):
        _, reg1, reg2 = Comet2.decode_1word(elem.value)
        v1 = self.get_gr(reg1)
        v2 = self.get_gr(reg2)
        self.cmp_flag(v1, v2)
        self.output_debug(elem.line,
                f"<GR{reg1}={v1:04x} - GR{reg2}={v2:04x}> " +
                f"(ZF <- {self._zf}, SF <- {self._sf}, OF <- {self._of})")

    def op_CPL_REG(self, elem):
        _, reg1, reg2 = Comet2.decode_1word(elem.value)
        v1 = self.get_gr(reg1)
        v2 = self.get_gr(reg2)
        self.cmp_flag(v1, v2, False)
        self.output_debug(elem.line,
                f"<GR{reg1}={v1:04x} -L GR{reg2}={v2:04x}> " +
                f"(ZF <- {self._zf}, SF <- {self._sf}, OF <- {self._of})")

    def op_SLA(self, elem):
        reg, adr = self.get_reg_adr(elem)
        v1 = self.get_gr(reg)
        v2 = self.get_mem(adr)
        if v2 == 0:
            self.output_debug(elem.line,
                    f"GR{reg} <- {v1:04x} <GR{reg}={v1:04x} << MEM[{adr:04x}]={v2:04x}>")
            return
        elif v2 >= self.REG_BITS:
            v2 = self.REG_BITS
            self._of = (v1 & 0x8000) >> 15
        else:
            self._of = int((v1 & (1 << (self.REG_BITS - v2))) != 0)
        r = (v1 << v2) & 0xffff
        r = ((r & 0x7fff) | (v1 & 0x8000))
        self._zf = int(r == 0)
        self._sf = (v1 & 0x8000) >> 15
        self.set_gr(reg, r)
        self.output_debug(elem.line,
                f"GR{reg} <- {r:04x} <GR{reg}={v1:04x} << MEM[{adr:04x}]={v2:04x}> " +
                f"(ZF <- {self._zf}, SF <- {self._sf}, OF <- {self._of})")

    def op_SRA(self, elem):
        reg, adr = self.get_reg_adr(elem)
        v1 = self.get_gr(reg)
        v2 = self.get_mem(adr)
        if v2 == 0:
            self.output_debug(elem.line,
                    f"GR{reg} <- {v1:04x} <GR{reg}={v1:04x} >> MEM[{adr:04x}]={v2:04x}>")
            return
        elif v2 >= self.REG_BITS:
            v2 = self.REG_BITS
            self._of = 1
        else:
            self._of = int((v1 & (1 << (v2 - 1))) != 0)
        r = v1 >> v2
        self._sf = (v1 & 0x8000) >> 15
        if self._sf != 0:
            r = r | ((~((1 << (Comet2.REG_BITS - v2)) - 1))&0xffff)
        self._zf = int(r == 0)
        self.set_gr(reg, r)
        self.output_debug(elem.line,
                f"GR{reg} <- {r:04x} <GR{reg}={v1:04x} >> MEM[{adr:04x}]={v2:04x}> " +
                f"(ZF <- {self._zf}, SF <- {self._sf}, OF <- {self._of})")

    def op_SLL(self, elem):
        reg, adr = self.get_reg_adr(elem)
        v1 = self.get_gr(reg)
        v2 = self.get_mem(adr)
        if v2 == 0:
            self.output_debug(elem.line,
                    f"GR{reg} <- {v1:04x} <GR{reg}={v1:04x} <<L MEM[{adr:04x}]={v2:04x}>")
            return
        elif v2 > self.REG_BITS:
            v2 = self.REG_BITS
            self._of = 0
        else:
            self._of = int((v1 & (1 << (self.REG_BITS - v2))) != 0)
        r = (v1 << v2) & 0xffff
        self._zf = int(r == 0)
        self._sf = 0
        self.set_gr(reg, r)
        self.output_debug(elem.line,
                f"GR{reg} <- {r:04x} <GR{reg}={v1:04x} <<L MEM[{adr:04x}]={v2:04x}> " +
                f"(ZF <- {self._zf}, SF <- {self._sf}, OF <- {self._of})")

    def op_SRL(self, elem):
        reg, adr = self.get_reg_adr(elem)
        v1 = self.get_gr(reg)
        v2 = self.get_mem(adr)
        if v2 == 0:
            self.output_debug(elem.line,
                    f"GR{reg} <- {v1:04x} <GR{reg}={v1:04x} >>L MEM[{adr:04x}]={v2:04x}>")
            return
        elif v2 > self.REG_BITS:
            v2 = self.REG_BITS
            self._of = 0
        else:
            self._of = int((v1 & (1 << (v2 - 1))) != 0)
        r = v1 >> v2
        self._zf = int(r == 0)
        self._sf = 0
        self.set_gr(reg, r)
        self.output_debug(elem.line,
                f"GR{reg} <- {r:04x} <GR{reg}={v1:04x} >>L MEM[{adr:04x}]={v2:04x}> " +
                f"(ZF <- {self._zf}, SF <- {self._sf}, OF <- {self._of})")

    def op_JMI(self, elem):
        _, adr = self.get_reg_adr(elem)
        msg = ""
        if self._sf != 0:
            self._pr = adr
            msg = f"PR <- {adr:04x} "
        self.output_debug(elem.line, msg + "<if SF == 1>")

    def op_JNZ(self, elem):
        _, adr = self.get_reg_adr(elem)
        msg = ""
        if self._zf == 0:
            self._pr = adr
            msg = f"PR <- {adr:04x} "
        self.output_debug(elem.line, msg + "<if ZF == 0>")

    def op_JZE(self, elem):
        _, adr = self.get_reg_adr(elem)
        msg = ""
        if self._zf != 0:
            self._pr = adr
            msg = f"PR <- {adr:04x} "
        self.output_debug(elem.line, msg + "<if ZF == 1>")

    def op_JUMP(self, elem):
        _, adr = self.get_reg_adr(elem)
        self._pr = adr
        self.output_debug(elem.line, f"PR <- {adr:04x}")

    def op_JPL(self, elem):
        _, adr = self.get_reg_adr(elem)
        msg = ""
        if self._sf == 0 and self._zf == 0:
            self._pr = adr
            msg = f"PR <- {adr:04x} "
        self.output_debug(elem.line, msg + "<if SF == 0 and ZF == 0>")

    def op_JOV(self, elem):
        _, adr = self.get_reg_adr(elem)
        msg = ""
        if self._of != 0:
            self._pr = adr
            msg = f"PR <- {adr:04x} "
        self.output_debug(elem.line, msg + "<if OF == 1>")

    def op_PUSH(self, elem):
        code1 = elem.value
        code2 = self.fetch().value
        _, _, opr2, opr3 = Comet2.decode_2word(code1, code2)
        val = opr2
        if opr3 != 0:
            offset = self.get_gr(opr3)
            val = (val + offset) & 0xffff
            msg_val = f"<{opr2:04x} + GR{opr3}={offset:04x}>"
        else:
            msg_val = f"<{opr2:04x}>"
        self._sp = (self._sp - 1) & 0xffff
        self.set_mem(self._sp, val)
        self.output_debug(elem.line,
                f"MEM[{self._sp:04x}] <- {val:04x} {msg_val} (SP <- {self._sp:04x})")

    def op_POP(self, elem):
        _, reg, _ = Comet2.decode_1word(elem.value)
        adr = self._sp
        val = self.get_mem(adr)
        self.set_gr(reg, val)
        self._sp = (self._sp + 1) & 0xffff
        self.output_debug(elem.line,
                f"GR{reg} <- {val:04x} <MEM[{adr:04x}]> (SP <- {self._sp:04x})")

    def op_CALL(self, elem):
        _, next_pr = self.get_reg_adr(elem)
        self._sp = (self._sp - 1) & 0xffff
        val = self._pr
        self.set_mem(self._sp, val)
        self._pr = next_pr
        self.output_debug(elem.line,
                f"PR <- {next_pr:04x}, MEM[{self._sp:04x}] <- PR={val:04x} " +
                f"(SP <- {self._sp:04x})")

    def op_RET(self, elem):
        self._pr = self.get_mem(self._sp)
        self._sp = (self._sp + 1) & 0xffff
        self.output_debug(elem.line,
                f"PR <- {self._pr:04x} (SP <- {self._sp:04x})")

    def op_SVC(self, elem):
        code2 = self.fetch().value
        if code2 == Comet2.SVC_OP_IN:
            self.op_SVC_IN(elem)
        elif code2 == Comet2.SVC_OP_OUT:
            self.op_SVC_OUT(elem)
        else:
            self.err_exit(f"unknown SVC op 'SVC {code2:04x}'")

    def op_SVC_IN(self, elem):
        if self._inputf is None:
            self.err_exit(f"no input source")
        start = self.get_gr(1)
        size = self.get_mem(self.get_gr(2))
        end = start + size
        self.output_debug(elem.line, f"SVC IN ({size})")
        input_existed = True
        # 入力が足りない場合、0で埋める
        for adr in range(start, end):
            adr = adr & Comet2.ADR_MAX
            if input_existed:
                instr = self._inputf.read(1)
                input_existed = instr != ""
                d = ord(instr)&0xff if input_existed else 0
            else:
                d = 0
            self.set_mem(adr, d)
            self.output_debug(elem.line, f"IN: MEM[{adr:04x}] <- {d:04x}")

    def op_SVC_OUT(self, elem):
        msg = []
        start = self.get_gr(1)
        end = start + self.get_mem(self.get_gr(2))
        for adr in range(start, end):
            adr = adr & Comet2.ADR_MAX
            msg.append(self.get_mem(adr)&0xff)
        self.output_debug(elem.line, f"SVC OUT MEM[{start:04x}]...MEM[{end:04x}]")
        self.output(Comet2.to_str(msg))

    @staticmethod
    def to_str(ilist):
        # TODO ASCIIのみ (本来対応する文字コードはJIS X 0201)
        return "".join([chr(i) for i in ilist])
# End Comet2


def base_int(nstr):
    return int(nstr, 0)

def main():
    parser = argparse.ArgumentParser(
            description=__doc__,
            formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("asmfile", help="casl2 code ('-': stdin)")
    gasm = parser.add_argument_group("assembly optional arguments")
    gasm.add_argument("--emit-bin", action="store_true", help="アセンブル後のバイナリを出力して終了する")
    grun = parser.add_argument_group("runtime optional arguments")
    grun.add_argument("-p", "--print-regs", action="store_true", help="実行前後にレジスタの内容を表示する")
    grun.add_argument("--virtual-call", action="store_true", help="実行前にENDのアドレスをスタックに積む")
    grun.add_argument("--input-src", help="実行時の入力元 (default: stdin)", metavar="file")
    grun.add_argument("--output", help="実行時の出力先 (default: stdout)", metavar="file")
    grun.add_argument("--output-debug", help="実行時のデバッグ出力先 (default: stdout)", metavar="file")
    grun.add_argument("--set-gr0", type=base_int, default=0, help="GR0の初期値", metavar="n")
    grun.add_argument("--set-gr1", type=base_int, default=0, help="GR1の初期値", metavar="n")
    grun.add_argument("--set-gr2", type=base_int, default=0, help="GR2の初期値", metavar="n")
    grun.add_argument("--set-gr3", type=base_int, default=0, help="GR3の初期値", metavar="n")
    grun.add_argument("--set-gr4", type=base_int, default=0, help="GR4の初期値", metavar="n")
    grun.add_argument("--set-gr5", type=base_int, default=0, help="GR5の初期値", metavar="n")
    grun.add_argument("--set-gr6", type=base_int, default=0, help="GR6の初期値", metavar="n")
    grun.add_argument("--set-gr7", type=base_int, default=0, help="GR7の初期値", metavar="n")
    grun.add_argument("--set-sp", type=base_int, default=0, help="SPの初期値", metavar="n")
    grun.add_argument("--set-zf", type=base_int, default=0, help="FR(zero flag)の初期値", metavar="n")
    grun.add_argument("--set-sf", type=base_int, default=0, help="FR(sign flag)の初期値", metavar="n")
    grun.add_argument("--set-of", type=base_int, default=0, help="FR(overflow flag)の初期値", metavar="n")

    # レジスタ、メモリの値はデフォルトでは0
    # --virtual-call: RETで終了するような、STARTのラベル呼び出しを前提としたコードを正常終了させる

    args = parser.parse_args()

    p = Parser()
    with contextlib.ExitStack() as stack:
        if args.asmfile == "-":
            f = sys.stdin
        else:
            f = stack.enter_context(open(args.asmfile))
        used_stdin = f == sys.stdin
        p.parse(f)
    mem = p.get_mem()
    start = p.get_start()
    end = p.get_end()

    if args.emit_bin:
        width = 8
        for i in range(0, len(mem), width):
            line = " ".join([f"{m.value:04x}" for m in mem[i:i+width]])
            print(f"[{i:04x}]: {line}")
        return

    c = Comet2(mem, args.print_regs)
    grlist = [args.set_gr0, args.set_gr1, args.set_gr2, args.set_gr3,
            args.set_gr4, args.set_gr5, args.set_gr6, args.set_gr7]
    c.init_regs(grlist, 0, args.set_sp, args.set_zf, args.set_sf, args.set_of)
    with contextlib.ExitStack() as stack:
        fo = sys.stdout
        if args.output == "":
            fo = None
        elif args.output:
            fo = stack.enter_context(open(args.output, "w"))
        fd = sys.stdout
        if args.output_debug == args.output:
            fd = fo
        elif args.output_debug == "":
            fd = None
        elif args.output_debug:
            fd = stack.enter_context(open(args.output_debug, "w"))
        fi = sys.stdin
        if args.input_src == "":
            fi = None
        elif args.input_src:
            fi = stack.enter_context(open(args.input_src))
        elif used_stdin:
            print("System Warning: both asmfile and input-src are stdin", file=sys.stderr)
        c.run(start, end, fo, fd, fi, args.virtual_call)

if __name__ == "__main__":
    main()
