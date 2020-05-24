#!/usr/bin/env python3
# coding:utf-8
"""
CASL2シミュレータ

STARTの位置から開始し、ENDの位置に来た時終了する
"""
import argparse
import contextlib
import operator
import re
import sys


LABEL = r"[A-Za-z][A-Z0-9a-z]*" # 本来は小文字は不可
RE_LABEL_LINE = re.compile(fr"({LABEL})(.*)")
RE_OP_LINE = re.compile(r"\s+[A-Z].*")
RE_COMMENT = re.compile(r";.*")
RE_DC = re.compile(r"\s+DC\s+")
RE_DC_ARGS = re.compile(fr"('(''|[^'])+'|[0-9]+|#[0-9A-Fa-f]+|{LABEL})(.*)")

class Element:
    """
    メモリの1要素分のデータ構造
    """
    def __init__(self, v, l, vlabel=None, label=None):
        # int この要素の値
        self.value = v
        # int (debug用) asmでの行番号を格納する asmと無関係または値が実行時に書き換えられた場合は0
        self.line = l
        # str (debug用) 値がラベル由来の場合のラベル名 それ以外はNone 値が実行時に書き換えられた場合はNone
        self.vlabel = vlabel
        # str (debug用) ラベルが指定された番地の場合のラベル名 それ以外はNone 実行時に変更されない
        self.label = label
# End Element

class Parser:
    REG_NAME_LIST = ("GR0", "GR1", "GR2", "GR3", "GR4", "GR5", "GR6", "GR7")

    def __init__(self, start_offset=0):
        self._start_offset = start_offset
        self._mem = [Element(0, 0) for _ in range(start_offset)]
        # 未解決のラベルを格納する要素を保持する {ラベル名(str):[格納先の要素(Element), ...]}
        # keyが重複した場合、リストに追加していく
        self._unresolved_labels = {}
        # 定義されたラベルの値を保持する {ラベル名(str):実際の番地(int)}
        # keyが重複した場合、エラー
        self._defined_labels = {}
        # 予約語 レジスタ名
        for r in self.REG_NAME_LIST:
            self._defined_labels[r] = None
        # 未割当の定数を格納する要素を保持する {定数(int): [格納先の要素(Element), ...]}
        self._unallocated_consts = {}
        # 開始位置 (START疑似命令の指定先)
        self._start = -1
        self._start_label = None
        # 終了位置 (END疑似命令の位置)
        self._end = -1
        # 解析中の行番号
        self._line_num = 0

    def parse(self, fin):
        for line in fin:
            self._line_num += 1
            self._mem.extend(self.parse_line(line))
        if self._end < 0:
            self.err_exit("syntax error [not found 'END']")
        if len(self._mem) > self._end:
            self.err_exit("syntax error ['END' must be last]")
        self.resolve_labels()
        self.allocate_consts()
        if self._start < 0:
            self.err_exit("syntax error [not found 'START']")
        self.set_labelinfo()

    def load_data(self, f, offset):
        adr = offset
        while True:
            while len(self._mem) <= adr:
                self._mem.append(Element(0, 0))
            b = f.read(1)
            if b == b'':
                break
            self._mem[adr].value = int.from_bytes(b, byteorder=sys.byteorder)
            adr += 1

    def err_exit(self, msg):
        print(f"Assemble Error: {msg}", file=sys.stderr)
        sys.exit(1)

    def get_mem(self):
        return self._mem

    def get_start(self):
        return self._start

    def get_end(self):
        return self._end

    def get_labels(self):
        return self._defined_labels

    def add_unresolved_label(self, label, elem):
        if label not in self._unresolved_labels:
            self._unresolved_labels[label] = []
        elem.vlabel = label
        self._unresolved_labels[label].append(elem)

    def define_label(self, label, adr):
        if label in self._defined_labels:
            msg = "defined label" if self._defined_labels[label] else "reserved label"
            self.err_exit(f"{msg} (L{self._line_num}: {label})")
        self._defined_labels[label] = adr

    def add_unallocated_const(self, const, elem):
        if const not in self._unallocated_consts:
            self._unallocated_consts[const] = []
        elem.vlabel=f"={const}"
        self._unallocated_consts[const].append(elem)

    def resolve_labels(self):
        if self._start_label is not None:
            if self._start_label not in self._defined_labels:
                self.err_exit(f"undefined start label ({self._start_label})")
            self._start = self._defined_labels[self._start_label]
        for label, elemlist in self._unresolved_labels.items():
            if label not in self._defined_labels:
                linemsgs = self.get_linemsgs(elemlist)
                self.err_exit(f"undefined label ({linemsgs}: {label})")
            addr = self._defined_labels[label]
            if addr is None:
                linemsgs = self.get_linemsgs(elemlist)
                self.err_exit(f"reserved label ({linemsgs}: {label})")
            for elem in elemlist:
                elem.value = addr & 0xffff

    def get_linemsgs(self, elemlist):
        linemsgs = []
        for elem in elemlist:
            linemsgs.append(f"L{elem.line}")
        return ", ".join(linemsgs)

    def allocate_consts(self):
        for const, elemlist in self._unallocated_consts.items():
            self._mem.append(Element(const & 0xffff, 0))
            addr = (len(self._mem) - 1) & 0xffff
            for elem in elemlist:
                elem.value = addr

    def set_labelinfo(self):
        for label, adr in self._defined_labels.items():
            if adr is None:
                continue
            while len(self._mem) <= adr:
                self._mem.append(Element(0, 0))
            self._mem[adr].label = label

    def parse_line(self, line):
        """
        lineを解析する
        解析の結果追加されるメモリのリストを返す
        """
        line_ = re.sub(RE_COMMENT, "", line)[:-1]
        if len(line_.strip()) == 0:
            return []
        m = re.match(RE_LABEL_LINE, line_)
        if m is not None:
            self.define_label(m.group(1), len(self._mem))
            line_ = m.group(2)
        if re.match(RE_OP_LINE, line_) is None:
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

    def parse_DC(self, line):
        args = re.sub(RE_DC, "", line)
        m = re.match(RE_DC_ARGS, args)
        if m is None:
            self.err_exit(f"syntax error [DC bad format] (L{self._line_num})")
        arg, _, args = m.groups()
        mem_part = self.parse_DC_arg(arg)
        while len(args) != 0:
            if args[0] != ",":
                self.err_exit(f"syntax error [DC ','] (L{self._line_num})")
            args = args[1:].strip()
            m = re.match(RE_DC_ARGS, args)
            arg, _, args = m.groups()
            mem_part.extend(self.parse_DC_arg(arg))
        return mem_part

    def parse_DC_arg(self, arg):
        mem_part = []
        if arg[0] == "'": # string
            st = arg[1:-1].replace("''", "'")
            for s in st:
                mem_part.append(Element(ord(s)&0xff, self._line_num))
        elif arg[0] == "#": # hexadecimal
            mem_part.append(Element(int(arg[1:], 16), self._line_num))
        elif arg.isdecimal(): # decimal
            mem_part.append(Element(int(arg), self._line_num))
        else: # label
            elem = Element(0, self._line_num)
            self.add_unresolved_label(arg, elem)
            mem_part.append(elem)
        return mem_part

    def parse_macro(self, op, args):
        if op == "IN":
            if len(args) != 2:
                self.err_exit(f"bad args (L{self._line_num})")
            return self.mk_macro((("PUSH", "0", "GR1"), ("PUSH", "0", "GR2"),
                ("LAD", "GR1", args[0]), ("LAD", "GR2", args[1]),
                ("SVC", str(Comet2.SVC_OP_IN)), ("POP", "GR2"), ("POP", "GR1")))
        elif op == "OUT":
            if len(args) != 2:
                self.err_exit(f"bad args (L{self._line_num})")
            return self.mk_macro((("PUSH", "0", "GR1"), ("PUSH", "0", "GR2"),
                ("LAD", "GR1", args[0]), ("LAD", "GR2", args[1]),
                ("SVC", str(Comet2.SVC_OP_OUT)), ("POP", "GR2"), ("POP", "GR1")))
        elif op == "RPUSH":
            if len(args) != 0:
                self.err_exit(f"bad args (L{self._line_num})")
            return self.mk_macro([("PUSH", "0", "{reg}") for reg in
                    ["GR1", "GR2", "GR3", "GR4", "GR5", "GR6", "GR7"]])
        elif op == "RPOP":
            if len(args) != 0:
                self.err_exit(f"bad args (L{self._line_num})")
            return self.mk_macro([("POP", "0", "{reg}") for reg in
                    ["GR7", "GR6", "GR5", "GR4", "GR3", "GR2", "GR1"]])
        return None

    def mk_macro(self, asms):
        mem_part = []
        for asm in asms:
            mem_part.extend(self.parse_op(asm[0], asm[1:]))
        return mem_part

    def parse_op(self, op, args):
        if op == "NOP":
            return self.encode_1word(0x00, 0, 0)
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
            return self.encode_1word(0x71, self.reg(args[0]), 0)
        elif op == "CALL":
            return self.op_2word(0x80, args, True)
        elif op == "RET":
            return self.encode_1word(0x81, 0, 0)
        elif op == "SVC":
            return self.encode_2word(0xf0, 0, args[0], 0)
        elif op == "START":
            if len(self._mem) != self._start_offset:
                self.err_exit("syntax error ['START' must be first]")
            if len(args) == 0:
                self._start = len(self._mem)
            else:
                self._start_label = args[0]
            return []
        elif op == "END":
            self._end = len(self._mem)
            return []
        elif op == "DS":
            return [Element(0, self._line_num) for _ in range(int(args[0]))]
        elif op == "DC": # not reached
            self.err_exit(f"internal error DC (L{self._line_num})")
        self.err_exit(f"unknown operation (L{self._line_num}: {op})")

    def op_1or2word(self, op1word, op2word, args):
        """
        argsから1word命令か2word命令かを判断して命令を生成する
        1word命令の場合op1wordを使用し、2word命令の場合op2wordを使用する
        """
        opr1 = self.reg(args[0])
        if args[1] in self.REG_NAME_LIST:
            opr2 = self.reg(args[1])
            return self.encode_1word(op1word, opr1, opr2)
        opr2 = args[1]
        if len(args) <= 2:
            opr3 = 0
        else:
            opr3 = self.reg(args[2])
        return self.encode_2word(op2word, opr1, opr2, opr3)

    def op_2word(self, op, args, without_opr1=False):
        opr1 = 0
        opr2 = "0"
        opr3 = 0
        opr3_arg = None
        if args[0] in self.REG_NAME_LIST:
            if without_opr1:
                self.err_exit(f"syntax error [bad register arg] (L{self._line_num})")
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
        return self.encode_2word(op, opr1, opr2, opr3)

    def reg(self, regname):
        if regname not in self.REG_NAME_LIST:
            self.err_exit(f"bad register name (L{self._line_num}: {regname})")
        return ord(regname[2]) - ord("0")

    def encode_1word(self, opcode, operand1, operand2):
        word = ((opcode & 0xff) << 8) | ((operand1 & 0xf) << 4) | (operand2 & 0xf)
        return [Element(word, self._line_num)]

    def encode_2word(self, opcode, operand1, operand2, operand3):
        """
        opcode:   int
        operand1: int
        operand2: str
        operand3: int
        """
        word1 = ((opcode & 0xff) << 8) | ((operand1 & 0xf) << 4) | (operand3 & 0xf)
        elem1 = Element(word1, self._line_num)
        elem2 = Element(0, self._line_num)
        if operand2[0] == "=":
            self.add_unallocated_const(int(operand2[1:]), elem2)
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

    def __init__(self, mem, print_regs=False, simple_output=False):
        self._print_regs = print_regs
        self._simple_output = simple_output
        self._gr = [0] * Comet2.REG_NUM
        self._pr = 0
        self._sp = 0
        self._zf = 0
        self._sf = 0
        self._of = 0
        self._fin = None
        self._fout = None
        self._fdbg = None
        self._input_all = None
        self.init_mem(mem)
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

    def get_allmem(self):
        return self._mem

    def run(self, start, end, fout=None, fdbg=None, fin=None, virtual_call=False, input_all=False):
        self._fout = fout
        self._fdbg = fdbg
        self._fin = fin
        self._pr = start & 0xffff
        end = end & 0xffff
        self._input_all = input_all
        self.output_regs()
        if virtual_call:
            self._sp = (self._sp - 1) & 0xffff
            self._mem[self._sp].value = end
            if self._fdbg is not None:
                self._fdbg.write("VCALL: [----] " +
                        f"MEM[{self._sp:04x}] <- {end:04x} (SP <- {self._sp:04x})\n")
        while self._pr != end:
            self.run_once()
        self.output_regs()

    def run_once(self):
        self._inst_adr = self._pr
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

    def output_debug(self, elem, msg, print_flags=True):
        if self._fdbg is None:
            return
        lstr = "--:" if elem.line == 0 else f"L{elem.line}:"
        flags = f" (ZF <- {self._zf}, SF <- {self._sf}, OF <- {self._of})" if print_flags else ""
        label = self._mem[self._inst_adr].label
        labelmsg = ""
        if label is not None:
            labelmsg = f"'{label}'="
        self._fdbg.write(f"{lstr:>6} [{labelmsg}{self._inst_adr:04x}] {msg}{flags}\n")

    def output(self, msg):
        if self._fout is None:
            return
        if self._simple_output:
            self._fout.write(f"{msg}")
        else:
            self._fout.write(f"  OUT: {msg}\n")

    def output_regs(self):
        if not self._print_regs or self._fdbg is None:
            return
        grlist = " ".join([f"GR{i}={gr:04x}" for i, gr in enumerate(self._gr)])
        self._fdbg.write(f"\n-REGS: {grlist}\n")
        self._fdbg.write(f"-REGS: PR={self._pr:04x} SP={self._sp:04x} ")
        self._fdbg.write(f"ZF={self._zf} SF={self._sf} OF={self._of}\n\n")

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
        self._mem[adr].vlabel = None

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
        elem2 = self.fetch()
        code2 = elem2.value
        _, opr1, opr2, opr3 = Comet2.decode_2word(code1, code2)
        if opr3 == 0:
            adr = opr2
            if elem2.vlabel is not None:
                adr_str = f"'{elem2.vlabel}'={adr:04x}"
            else:
                adr_str = f"{adr:04x}"
        else:
            offset = self.get_gr(opr3)
            adr = opr2 + offset
            if elem2.vlabel is None:
                adr_str = f"{adr:04x} <{opr2:04x} + GR{opr3}={offset:04x}>"
            else:
                adr_str = f"{adr:04x} <'{elem2.vlabel}'={opr2:04x} + GR{opr3}={offset:04x}>"
        adr = opr2 if opr3 == 0 else opr2 + self.get_gr(opr3)
        return (opr1, adr&0xffff, adr_str)

    def op_NOP(self, elem):
        self.output_debug(elem, "NOP", False)

    def op_LD(self, elem):
        reg, adr, adr_str = self.get_reg_adr(elem)
        val = self.get_mem(adr)
        self._zf = int(val == 0)
        self._sf = (val&0x8000) >> 15
        self._of = 0
        self.set_gr(reg, val)
        self.output_debug(elem, f"GR{reg} <- MEM[{adr_str}]={val:04x}")

    def op_ST(self, elem):
        reg, adr, adr_str = self.get_reg_adr(elem)
        val = self.get_gr(reg)
        self.set_mem(adr, val)
        self.output_debug(elem, f"MEM[{adr_str}] <- GR{reg}={val:04x}", False)

    def op_LAD(self, elem):
        reg, adr, adr_str = self.get_reg_adr(elem)
        self.set_gr(reg, adr)
        self.output_debug(elem, f"GR{reg} <- {adr_str}", False)

    def op_LD_REG(self, elem):
        _, reg1, reg2 = Comet2.decode_1word(elem.value)
        val = self.get_gr(reg2)
        self._zf = int(val == 0)
        self._sf = (val&0x8000) >> 15
        self._of = 0
        self.set_gr(reg1, val)
        self.output_debug(elem, f"GR{reg1} <- GR{reg2}={val:04x}")

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
        reg, adr, adr_str = self.get_reg_adr(elem)
        v1 = self.get_gr(reg)
        v2 = self.get_mem(adr)
        r = self.add_flag(v1, v2)
        self.set_gr(reg, r)
        self.output_debug(elem, f"GR{reg} <- {r:04x} <GR{reg}={v1:04x} + MEM[{adr_str}]={v2:04x}>")

    def op_SUBA(self, elem):
        reg, adr, adr_str = self.get_reg_adr(elem)
        v1 = self.get_gr(reg)
        v2 = self.get_mem(adr)
        r = self.sub_flag(v1, v2)
        self.set_gr(reg, r)
        self.output_debug(elem, f"GR{reg} <- {r:04x} <GR{reg}={v1:04x} - MEM[{adr_str}]={v2:04x}>")

    def op_ADDL(self, elem):
        reg, adr, adr_str = self.get_reg_adr(elem)
        v1 = self.get_gr(reg)
        v2 = self.get_mem(adr)
        r = self.add_flag(v1, v2, False)
        self.set_gr(reg, r)
        self.output_debug(elem, f"GR{reg} <- {r:04x} <GR{reg}={v1:04x} +L MEM[{adr_str}]={v2:04x}>")

    def op_SUBL(self, elem):
        reg, adr, adr_str = self.get_reg_adr(elem)
        v1 = self.get_gr(reg)
        v2 = self.get_mem(adr)
        r = self.sub_flag(v1, v2, False)
        self.set_gr(reg, r)
        self.output_debug(elem, f"GR{reg} <- {r:04x} <GR{reg}={v1:04x} -L MEM[{adr_str}]={v2:04x}>")

    def op_ADDA_REG(self, elem):
        _, reg1, reg2 = Comet2.decode_1word(elem.value)
        v1 = self.get_gr(reg1)
        v2 = self.get_gr(reg2)
        r = self.add_flag(v1, v2)
        self.set_gr(reg1, r)
        self.output_debug(elem, f"GR{reg1} <- {r:04x} <GR{reg1}={v1:04x} + GR{reg2}={v2:04x}>")

    def op_SUBA_REG(self, elem):
        _, reg1, reg2 = Comet2.decode_1word(elem.value)
        v1 = self.get_gr(reg1)
        v2 = self.get_gr(reg2)
        r = self.sub_flag(v1, v2)
        self.set_gr(reg1, r)
        self.output_debug(elem, f"GR{reg1} <- {r:04x} <GR{reg1}={v1:04x} - GR{reg2}={v2:04x}>")

    def op_ADDL_REG(self, elem):
        _, reg1, reg2 = Comet2.decode_1word(elem.value)
        v1 = self.get_gr(reg1)
        v2 = self.get_gr(reg2)
        r = self.add_flag(v1, v2, False)
        self.set_gr(reg1, r)
        self.output_debug(elem, f"GR{reg1} <- {r:04x} <GR{reg1}={v1:04x} +L GR{reg2}={v2:04x}>")

    def op_SUBL_REG(self, elem):
        _, reg1, reg2 = Comet2.decode_1word(elem.value)
        v1 = self.get_gr(reg1)
        v2 = self.get_gr(reg2)
        r = self.sub_flag(v1, v2, False)
        self.set_gr(reg1, r)
        self.output_debug(elem, f"GR{reg1} <- {r:04x} <GR{reg1}={v1:04x} -L GR{reg2}={v2:04x}> ")

    def bit_flag(self, op, v1, v2):
        r = op(v1, v2)
        self._zf = int(r == 0)
        self._sf = 0
        self._of = 0
        return r & 0xffff

    def op_AND(self, elem):
        reg, adr, adr_str = self.get_reg_adr(elem)
        v1 = self.get_gr(reg)
        v2 = self.get_mem(adr)
        r = self.bit_flag(operator.and_, v1, v2)
        self.set_gr(reg, r)
        self.output_debug(elem, f"GR{reg} <- {r:04x} <GR{reg}={v1:04x} & MEM[{adr_str}]={v2:04x}>")

    def op_OR(self, elem):
        reg, adr, adr_str = self.get_reg_adr(elem)
        v1 = self.get_gr(reg)
        v2 = self.get_mem(adr)
        r = self.bit_flag(operator.or_, v1, v2)
        self.set_gr(reg, r)
        self.output_debug(elem, f"GR{reg} <- {r:04x} <GR{reg}={v1:04x} | MEM[{adr_str}]={v2:04x}>")

    def op_XOR(self, elem):
        reg, adr, adr_str = self.get_reg_adr(elem)
        v1 = self.get_gr(reg)
        v2 = self.get_mem(adr)
        r = self.bit_flag(operator.xor, v1, v2)
        self.set_gr(reg, r)
        self.output_debug(elem, f"GR{reg} <- {r:04x} <GR{reg}={v1:04x} ^ MEM[{adr_str}]={v2:04x}>")

    def op_AND_REG(self, elem):
        _, reg1, reg2 = Comet2.decode_1word(elem.value)
        v1 = self.get_gr(reg1)
        v2 = self.get_gr(reg2)
        r = self.bit_flag(operator.and_, v1, v2)
        self.set_gr(reg1, r)
        self.output_debug(elem, f"GR{reg1} <- {r:04x} <GR{reg1}={v1:04x} & GR{reg2}={v2:04x}>")

    def op_OR_REG(self, elem):
        _, reg1, reg2 = Comet2.decode_1word(elem.value)
        v1 = self.get_gr(reg1)
        v2 = self.get_gr(reg2)
        r = self.bit_flag(operator.or_, v1, v2)
        self.set_gr(reg1, r)
        self.output_debug(elem, f"GR{reg1} <- {r:04x} <GR{reg1}={v1:04x} | GR{reg2}={v2:04x}>")

    def op_XOR_REG(self, elem):
        _, reg1, reg2 = Comet2.decode_1word(elem.value)
        v1 = self.get_gr(reg1)
        v2 = self.get_gr(reg2)
        r = self.bit_flag(operator.xor, v1, v2)
        self.set_gr(reg1, r)
        self.output_debug(elem, f"GR{reg1} <- {r:04x} <GR{reg1}={v1:04x} ^ GR{reg2}={v2:04x}>")

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
        reg, adr, adr_str = self.get_reg_adr(elem)
        v1 = self.get_gr(reg)
        v2 = self.get_mem(adr)
        self.cmp_flag(v1, v2)
        self.output_debug(elem, f"<GR{reg}={v1:04x} - MEM[{adr_str}]={v2:04x}>")

    def op_CPL(self, elem):
        reg, adr, adr_str = self.get_reg_adr(elem)
        v1 = self.get_gr(reg)
        v2 = self.get_mem(adr)
        self.cmp_flag(v1, v2, False)
        self.output_debug(elem, f"<GR{reg}={v1:04x} -L MEM[{adr_str}]={v2:04x}>")

    def op_CPA_REG(self, elem):
        _, reg1, reg2 = Comet2.decode_1word(elem.value)
        v1 = self.get_gr(reg1)
        v2 = self.get_gr(reg2)
        self.cmp_flag(v1, v2)
        self.output_debug(elem, f"<GR{reg1}={v1:04x} - GR{reg2}={v2:04x}>")

    def op_CPL_REG(self, elem):
        _, reg1, reg2 = Comet2.decode_1word(elem.value)
        v1 = self.get_gr(reg1)
        v2 = self.get_gr(reg2)
        self.cmp_flag(v1, v2, False)
        self.output_debug(elem, f"<GR{reg1}={v1:04x} -L GR{reg2}={v2:04x}>")

    def op_SLA(self, elem):
        reg, adr, adr_str = self.get_reg_adr(elem)
        v1 = self.get_gr(reg)
        v2 = self.get_mem(adr)
        shift = v2 if v2 < self.REG_BITS else self.REG_BITS
        r = v1
        for _ in range(shift):
            self._of = (r & 0x4000) >> 14
            r = (((r << 1) & 0x7fff) | (v1 & 0x8000))
        self._zf = int(r == 0)
        self._sf = (v1 & 0x8000) >> 15
        self.set_gr(reg, r)
        self.output_debug(elem, f"GR{reg} <- {r:04x} <GR{reg}={v1:04x} << MEM[{adr_str}]={v2:04x}>")

    def op_SRA(self, elem):
        reg, adr, adr_str = self.get_reg_adr(elem)
        v1 = self.get_gr(reg)
        v2 = self.get_mem(adr)
        shift = v2 if v2 < self.REG_BITS else self.REG_BITS
        r = v1
        for _ in range(shift):
            self._of = r & 0x0001
            r = (((r >> 1) & 0x7fff) | (v1 & 0x8000))
        self._zf = int(r == 0)
        self._sf = (v1 & 0x8000) >> 15
        self.set_gr(reg, r)
        self.output_debug(elem, f"GR{reg} <- {r:04x} <GR{reg}={v1:04x} >> MEM[{adr_str}]={v2:04x}>")

    def op_SLL(self, elem):
        reg, adr, adr_str = self.get_reg_adr(elem)
        v1 = self.get_gr(reg)
        v2 = self.get_mem(adr)
        shift = v2 if v2 < self.REG_BITS + 1 else self.REG_BITS + 1
        r = v1
        for _ in range(shift):
            self._of = (r & 0x8000) >> 15
            r = (r << 1) & 0xffff
        self._zf = int(r == 0)
        self._sf = 0
        self.set_gr(reg, r)
        self.output_debug(elem, f"GR{reg} <- {r:04x} <GR{reg}={v1:04x} <<L MEM[{adr_str}]={v2:04x}>")

    def op_SRL(self, elem):
        reg, adr, adr_str = self.get_reg_adr(elem)
        v1 = self.get_gr(reg)
        v2 = self.get_mem(adr)
        shift = v2 if v2 < self.REG_BITS + 1 else self.REG_BITS + 1
        r = v1
        for _ in range(shift):
            self._of = r & 0x0001
            r = r >> 1
        self._zf = int(r == 0)
        self._sf = 0
        self.set_gr(reg, r)
        self.output_debug(elem, f"GR{reg} <- {r:04x} <GR{reg}={v1:04x} >>L MEM[{adr_str}]={v2:04x}>")

    def op_JMI(self, elem):
        _, adr, adr_str = self.get_reg_adr(elem)
        msg = ""
        if self._sf != 0:
            self._pr = adr
            msg = f"PR <- {adr_str} "
        self.output_debug(elem, msg + "<if SF == 1>", False)

    def op_JNZ(self, elem):
        _, adr, adr_str = self.get_reg_adr(elem)
        msg = ""
        if self._zf == 0:
            self._pr = adr
            msg = f"PR <- {adr_str} "
        self.output_debug(elem, msg + "<if ZF == 0>", False)

    def op_JZE(self, elem):
        _, adr, adr_str = self.get_reg_adr(elem)
        msg = ""
        if self._zf != 0:
            self._pr = adr
            msg = f"PR <- {adr_str} "
        self.output_debug(elem, msg + "<if ZF == 1>", False)

    def op_JUMP(self, elem):
        _, adr, adr_str = self.get_reg_adr(elem)
        self._pr = adr
        self.output_debug(elem, f"PR <- {adr_str}", False)

    def op_JPL(self, elem):
        _, adr, adr_str = self.get_reg_adr(elem)
        msg = ""
        if self._sf == 0 and self._zf == 0:
            self._pr = adr
            msg = f"PR <- {adr_str} "
        self.output_debug(elem, msg + "<if SF == 0 and ZF == 0>", False)

    def op_JOV(self, elem):
        _, adr, adr_str = self.get_reg_adr(elem)
        msg = ""
        if self._of != 0:
            self._pr = adr
            msg = f"PR <- {adr_str} "
        self.output_debug(elem, msg + "<if OF == 1>", False)

    def op_PUSH(self, elem):
        _, adr, adr_str = self.get_reg_adr(elem)
        self._sp = (self._sp - 1) & 0xffff
        self.set_mem(self._sp, adr)
        self.output_debug(elem,
                f"MEM[SP={self._sp:04x}] <- {adr_str} (SP <- {self._sp:04x})", False)

    def op_POP(self, elem):
        _, reg, _ = Comet2.decode_1word(elem.value)
        adr = self._sp
        val = self.get_mem(adr)
        self.set_gr(reg, val)
        self._sp = (self._sp + 1) & 0xffff
        self.output_debug(elem,
                f"GR{reg} <- {val:04x} <MEM[SP={adr:04x}]> (SP <- {self._sp:04x})", False)

    def op_CALL(self, elem):
        _, adr, adr_str = self.get_reg_adr(elem)
        self._sp = (self._sp - 1) & 0xffff
        val = self._pr
        self.set_mem(self._sp, val)
        self._pr = adr
        self.output_debug(elem,
                f"PR <- {adr_str}, MEM[SP={self._sp:04x}] <- PR={val:04x} " +
                f"(SP <- {self._sp:04x})", False)

    def op_RET(self, elem):
        self._pr = self.get_mem(self._sp)
        self._sp = (self._sp + 1) & 0xffff
        self.output_debug(elem, f"PR <- {self._pr:04x} (SP <- {self._sp:04x})", False)

    def op_SVC(self, elem):
        code2 = self.fetch().value
        if code2 == Comet2.SVC_OP_IN:
            self.op_SVC_IN(elem)
        elif code2 == Comet2.SVC_OP_OUT:
            self.op_SVC_OUT(elem)
        else:
            self.err_exit(f"unknown SVC op 'SVC {code2:04x}'")

    def op_SVC_IN(self, elem):
        # IN: GR1(保存先アドレス) GR2(サイズ格納先アドレス)
        # self._finがNoneの場合、サイズ0の入力とみなす
        start = self.get_gr(1)
        self.output_debug(elem, "SVC IN", False)
        size = 0
        for _ in range(256):
            save_adr = (start + size) & Comet2.ADR_MAX
            instr = ""
            if self._fin is not None:
                while True:
                    instr = self._fin.read(1)
                    if instr == "" or self._input_all or Comet2.is_printable(instr):
                        break
            if instr == "":
                break
            d = ord(instr)&0xff
            self.set_mem(save_adr, d)
            self.output_debug(elem, f"IN: MEM[{save_adr:04x}] <- {d:04x} <input>", False)
            size += 1
        size_adr = self.get_gr(2)
        self.set_mem(size_adr, size)
        self.output_debug(elem, f"IN: MEM[{size_adr:04x}] <- {size:04x} <input size>", False)

    @staticmethod
    def is_printable(s):
        # JIS X 0201での印字可能文字
        c = ord(s)
        return (0x21 <= c and c <= 0x7e) or (0xa1 <= c and c <= 0xdf)

    def op_SVC_OUT(self, elem):
        # OUT: GR1(出力元アドレス) GR2(サイズ格納先アドレス)
        msg = []
        start = self.get_gr(1)
        end = start + self.get_mem(self.get_gr(2))
        adr = start
        for adr in range(start, end):
            adr = adr & Comet2.ADR_MAX
            msg.append(self.get_mem(adr)&0xff)
        self.output_debug(elem, f"SVC OUT MEM[{start:04x}]...MEM[{adr:04x}]", False)
        self.output(Comet2.to_str(msg))

    @staticmethod
    def to_str(ilist):
        # TODO ASCIIのみ (本来対応する文字コードはJIS X 0201)
        return "".join([chr(i) for i in ilist])
# End Comet2

def print_mem(mem):
        width = 8
        for i in range(0, len(mem), width):
            line = " ".join([f"{m.value:04x}" for m in mem[i:i+width]])
            print(f"# [{i:04x}]: {line}")
        print("")

def base_int(nstr):
    return int(nstr, 0)


def main():
    parser = argparse.ArgumentParser(
            description=__doc__,
            formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("asmfile", help="casl2 code ('-': stdin)")
    gasm = parser.add_argument_group("assembly optional arguments")
    gasm.add_argument("--start-offset", type=base_int, default=0,
            help="プログラムを配置するアドレス", metavar="n")
    gasm.add_argument("-l", "--print-labels", action="store_true",
            help="ラベルのアドレス一覧を出力する")
    gasm.add_argument("-b", "--print-bin", action="store_true", help="アセンブル後のバイナリを出力する")
    gasm.add_argument("-a", "--parse-only", action="store_true", help="実行せずに終了する")
    gasm.add_argument("--load-data",
            help="アセンブル後に0番地からfileの内容を1byteずつ書き込む", metavar="file")
    gasm.add_argument("--load-data-offset", type=base_int, default=0,
            help="--load-dataオプションの開始番地", metavar="n")
    grun = parser.add_argument_group("runtime optional arguments")
    grun.add_argument("-R", "--print-regs", action="store_true", help="実行前後にレジスタの内容を表示する")
    grun.add_argument("-M", "--print-mem", action="store_true", help="実行後にメモリの内容を表示する")
    grun.add_argument("--input-src", help="実行時の入力元 (default: stdin)", metavar="file")
    grun.add_argument("--simple-output", action="store_true", help="実行時の出力をそのまま出力する")
    grun.add_argument("--output", help="実行時の出力先 (default: stdout)", metavar="file")
    grun.add_argument("--output-debug", help="実行時のデバッグ出力先 (default: stdout)", metavar="file")
    grun.add_argument("--start", type=base_int, help="プログラム開始アドレス", metavar="n")
    grun.add_argument("--end", type=base_int, help="プログラム終了アドレス", metavar="n")
    grun.add_argument("--gr0", type=base_int, default=0, help="GR0の初期値", metavar="n")
    grun.add_argument("--gr1", type=base_int, default=0, help="GR1の初期値", metavar="n")
    grun.add_argument("--gr2", type=base_int, default=0, help="GR2の初期値", metavar="n")
    grun.add_argument("--gr3", type=base_int, default=0, help="GR3の初期値", metavar="n")
    grun.add_argument("--gr4", type=base_int, default=0, help="GR4の初期値", metavar="n")
    grun.add_argument("--gr5", type=base_int, default=0, help="GR5の初期値", metavar="n")
    grun.add_argument("--gr6", type=base_int, default=0, help="GR6の初期値", metavar="n")
    grun.add_argument("--gr7", type=base_int, default=0, help="GR7の初期値", metavar="n")
    grun.add_argument("--sp", type=base_int, default=0, help="SPの初期値", metavar="n")
    grun.add_argument("--zf", type=base_int, default=0, help="FR(zero flag)の初期値", metavar="n")
    grun.add_argument("--sf", type=base_int, default=0, help="FR(sign flag)の初期値", metavar="n")
    grun.add_argument("--of", type=base_int, default=0, help="FR(overflow flag)の初期値", metavar="n")
    gext = parser.add_argument_group("CASL2 extention optional arguments")
    gext.add_argument("-C", "--virtual-call", action="store_true",
            help="実行前にENDのアドレスをスタックに積む")
    gext.add_argument("--input-all", action="store_true", help="INでの入力は全て受け付ける")

    # レジスタ、メモリの値はデフォルトでは0
    # --virtual-call: RETで終了するような、STARTのラベル呼び出しを前提としたコードを正常終了させる

    args = parser.parse_args()

    p = Parser(args.start_offset)
    with contextlib.ExitStack() as stack:
        if args.asmfile == "-":
            f = sys.stdin
        else:
            f = stack.enter_context(open(args.asmfile))
        used_stdin = f == sys.stdin
        p.parse(f)
    if args.start is None:
        start = p.get_start()
    else:
        start = args.start
    if args.end is None:
        end = p.get_end()
    else:
        end = args.end

    if args.load_data is not None:
        with open(args.load_data, "rb") as f:
            p.load_data(f, args.load_data_offset)

    mem = p.get_mem()

    if args.print_labels:
        labeldict = p.get_labels()
        for label, adr in labeldict.items():
            if adr is None:
                continue
            print(f"# {label:10} [{adr:04x}]")
        print("")

    if args.print_bin:
        print_mem(mem)

    if args.parse_only:
        return

    c = Comet2(mem, args.print_regs, args.simple_output)
    grlist = [args.gr0, args.gr1, args.gr2, args.gr3,
            args.gr4, args.gr5, args.gr6, args.gr7]
    c.init_regs(grlist, 0, args.sp, args.zf, args.sf, args.of)
    with contextlib.ExitStack() as stack:
        fout = sys.stdout
        if args.output == "":
            fout = None
        elif args.output:
            fout = stack.enter_context(open(args.output, "w"))
        fdbg = sys.stdout
        if args.output_debug == args.output:
            fdbg = fout
        elif args.output_debug == "":
            fdbg = None
        elif args.output_debug:
            fdbg = stack.enter_context(open(args.output_debug, "w"))
        fin = sys.stdin
        if args.input_src == "":
            fin = None
        elif args.input_src:
            fin = stack.enter_context(open(args.input_src))
        elif used_stdin:
            print("System Warning: both asmfile and input-src are stdin", file=sys.stderr)
        c.run(start, end, fout, fdbg, fin, args.virtual_call, args.input_all)

    if args.print_mem:
        print_mem(c.get_allmem())

if __name__ == "__main__":
    main()
