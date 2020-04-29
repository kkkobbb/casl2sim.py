#!/usr/bin/env python3
# coding:utf-8
"""
CASL2シミュレータ
"""
import argparse
import collections
import re
import sys


RE_LABEL = re.compile(r"\([A-Z]+\):\(.*\)")
RE_OP = re.compile(r"\s+[A-Z].*")
RE_COMMENT = re.compile(r";.*")
RE_DC = re.compile(r"\s+DC\s")
RE_DC_ARG = re.compile(r"('(''|[^'])+'|[0-9]+|#[0-9A-Fa-f]+|[A-Z][0-9A-Z]*)(.*)")

class Element:
    """
    メモリの1要素分のデータ構造

    value: int  この要素の値
    line:  int  (debug用) asmでの行番号を格納する asmと無関係または実行時に書き換えられた場合は0
    """
    def __init__(self, v, l):
        self.value = v
        self.line = l

    def __str__(self):
        return f"(value={self.value:04x}, line={self.line})"

def err_exit(msg):
    print(msg)
    sys.exit(1)

class Parser:
    REG_NAME_LIST = ["GR0", "GR1", "GR2", "GR3", "GR4", "GR5", "GR6", "GR7"]
    SVC_OP_IN = 1
    SVC_OP_OUT = 2

    def __init__(self, input_):
        self._input = input_
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
        # 終了位置
        self._end = -1
        # 解析中の行番号
        self._line_num = 0

    def parse(self):
        pass

    def get_mem(self):
        return self._mem[:]

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
        line_ = re.sub(RE_COMMENT, "", line)
        if len(line_.strip()) == 0:
            return []
        m = re.match(RE_LABEL, line_)
        if m is not None:
            self.set_actual_label(m.group(1), len(self._mem))
            line_ = m.group(2)
        m = re.match(RE_OP, line_)
        if m is None:
            err_exit(f"syntax error ({self._line_num})")
        tokens = line_.strip().split()
        if tokens[0] == "DS":
            return self.parse_DC(line_)
        macro = self.parse_macro(tokens)
        if macro is not None:
            return macro
        return self.parse_op(tokens)

    def parse_macro(self, tokens):
        op = tokens[0]
        args = tokens[1:]
        if op == "IN":
            if len(args) != 2:
                err_exit(f"bad args ({self._line_num})")
            mem_part = self.parse_op(["PUSH", "0", "GR1"])
            mem_part.extend(self.parse_op(["PUSH", "0", "GR2"]))
            mem_part.extend(self.parse_op(["LAD", "GR1", args[0]]))
            mem_part.extend(self.parse_op(["LAD", "GR2", args[1]]))
            mem_part.extend(self.parse_op(["SVC", str(self.SVC_OP_IN)]))
            mem_part.extend(self.parse_op(["POP", "GR2"]))
            mem_part.extend(self.parse_op(["POP", "GR1"]))
            return mem_part
        elif op == "OUT":
            if len(args) != 2:
                err_exit(f"bad args ({self._line_num})")
            mem_part = self.parse_op(["PUSH", "0", "GR1"])
            mem_part.extend(self.parse_op(["PUSH", "0", "GR2"]))
            mem_part.extend(self.parse_op(["LAD", "GR1", args[0]]))
            mem_part.extend(self.parse_op(["LAD", "GR2", args[1]]))
            mem_part.extend(self.parse_op(["SVC", str(self.SVC_OP_OUT)]))
            mem_part.extend(self.parse_op(["POP", "GR2"]))
            mem_part.extend(self.parse_op(["POP", "GR1"]))
            return mem_part
        elif op == "RPUSH":
            if len(args) != 0:
                err_exit(f"bad args ({self._line_num})")
            mem_part = self.parse_op(["PUSH", "0", "GR1"])
            mem_part = self.parse_op(["PUSH", "0", "GR2"])
            mem_part = self.parse_op(["PUSH", "0", "GR3"])
            mem_part = self.parse_op(["PUSH", "0", "GR4"])
            mem_part = self.parse_op(["PUSH", "0", "GR5"])
            mem_part = self.parse_op(["PUSH", "0", "GR6"])
            mem_part = self.parse_op(["PUSH", "0", "GR7"])
            return mem_part
        elif op == "RPOP":
            if len(args) != 0:
                err_exit(f"bad args ({self._line_num})")
            mem_part.extend(self.parse_op(["POP", "GR7"]))
            mem_part.extend(self.parse_op(["POP", "GR6"]))
            mem_part.extend(self.parse_op(["POP", "GR5"]))
            mem_part.extend(self.parse_op(["POP", "GR4"]))
            mem_part.extend(self.parse_op(["POP", "GR3"]))
            mem_part.extend(self.parse_op(["POP", "GR2"]))
            mem_part.extend(self.parse_op(["POP", "GR1"]))
            return mem_part
        return None

    def parse_op(self, tokens):
        op = tokens[0]
        args = tokens[1:]
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
            # adr == self.SVC_OP_IN:  IN GR1 GR2
            # adr == self.SVC_OP_OUT:  OUT GR1 GR2
            adr = int(args[0])
            return self.mk_2word(0xf0, adr, 0, 0)
        elif op == "START":
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
            err_exit("internal error")
        err_exit(f"unkown operation ({self._line_num}: {op})")

    def parse_DC(self, line):
        args = re.sub(RE_DC, "", line)
        m = re.match(RE_DC_ARG, args)
        # 最低1つは引数がある前提
        arg = m.group(1)
        args = m.group(3).strip()
        mem_part = self.parse_DC_arg(arg)
        while len(args) != 0:
            if args[0] != ",":
                err_exit(f"syntax error ',' ({self._line_num})")
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
            # 文字列
            st = arg[1:-1].replace("''", "'")
            for s in st:
                mem_part.append(Element(ord(s)&0xff, ln))
        elif arg[0] == "#":
            # 16進数
            mem_part.append(Element(int(arg[1:], 16), ln))
        elif arg[0].isdecimal():
            # 10進数
            mem_part.append(Element(int(arg), ln))
        else:
            # ラベル
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
                err_exit(f"syntax error (many reg arg) ({self._line_num})")
            opr1 = self.reg(args[0])
            opr2 = args[1]
            if len(args) >3:
                opr3_arg = args[2]
        else:
            if not without_opr1:
                err_exit(f"syntax error (few reg arg) ({self._line_num})")
            opr2 = args[0]
            if len(args) >= 2:
                opr3_arg = args[1]
        if opr3_arg is not None:
            opr3 = self.reg(opr3_arg)
        return self.mk_2word(op, opr1, opr2, opr3)

    zero = ord("0")
    def reg(self, regname):
        if regname not in self.REG_NAME_LIST:
            err_exit(f"no register name ({self._line_num}: {regname}")
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
    MEM_SIZE = 0xFFFF
    REG_NUM = 8

    def __init__(self):
        self._gr = [0] * Comet2.REG_NUM
        self._pr = 0
        self._sp = 0
        self._zf = 0
        self._sf = 0
        self._of = 0
        self._mem = [Element(0, 0) for i in range(Comet2.MEM_SIZE)]

    def get_gr(self, n):
        if n < 0 or Comet2.REG_NUM <= n:
            err_exit("GR index out of range")
        return self._gr[n]

    def set_gr(self, n, val):
        if n < 0 or Comet2.REG_NUM <= n:
            err_exit("GR index out of range")
        self._gr[n] = val & 0xffff

    def get_pr(self):
        return self._pr

    def set_pr(self, val):
        self._pr = val & 0xffff

    def get_sp(self):
        return self._sp

    def set_sp(self, val):
        self._sp = val & 0xffff

    def get_zf(self):
        return self._zf

    def set_zf(self, val):
        self._zf = val & 1

    def get_sf(self):
        return self._sf

    def set_sf(self, val):
        self._sf = val & 1

    def get_of(self):
        return self._of

    def set_of(self, val):
        self._of = val & 1

    def get_mem(self, adr):
        if adr < 0 or Comet2.MEM_SIZE <= adr:
            err_exit("MEM address out of range")
        return self._mem[adr].value

    def set_mem(self, adr, val):
        if adr < 0 or Comet2.MEM_SIZE <= adr:
            err_exit("MEM address out of range")
        self._mem[adr].value = val & 0xffff
# End Comet2

def run(machine, outputf):
    """
    machineの状態から実行する
    結果はoutputに出力する
    実行失敗の場合、エラー終了
    """
    pass


def base_int(nstr):
    return int(nstr, 0)

def main():
    parser = argparse.ArgumentParser(
            description=__doc__,
            formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("asmfile", help="casl2 code")
    parser.add_argument("--zero-all", action="store_true", help="全てのレジスタ、メモリを0で初期化する")
    parser.add_argument("--zero-reg", action="store_true", help="全てのレジスタを0で初期化する")
    parser.add_argument("--zero-mem", action="store_true", help="全てのメモリを0で初期化する")
    parser.add_argument("--rand-mem", action="store_true", help="全てのメモリを乱数で初期化する")
    parser.add_argument("--set-gr0", type=base_int, help="GR0を指定した値で初期化する", metavar="n")
    parser.add_argument("--set-gr1", type=base_int, help="GR1を指定した値で初期化する", metavar="n")
    parser.add_argument("--set-gr2", type=base_int, help="GR2を指定した値で初期化する", metavar="n")
    parser.add_argument("--set-gr3", type=base_int, help="GR3を指定した値で初期化する", metavar="n")
    parser.add_argument("--set-gr4", type=base_int, help="GR4を指定した値で初期化する", metavar="n")
    parser.add_argument("--set-gr5", type=base_int, help="GR5を指定した値で初期化する", metavar="n")
    parser.add_argument("--set-gr6", type=base_int, help="GR6を指定した値で初期化する", metavar="n")
    parser.add_argument("--set-gr7", type=base_int, help="GR7を指定した値で初期化する", metavar="n")
    parser.add_argument("--set-pr", type=base_int, help="PRを指定した値で初期化する", metavar="n")
    parser.add_argument("--set-sp", type=base_int, help="SPを指定した値で初期化する", metavar="n")
    parser.add_argument("--set-zf", type=base_int,
            help="FR(zero flag)を指定した値で初期化する", metavar="n")
    parser.add_argument("--set-sf", type=base_int,
            help="FR(sign flag)を指定した値で初期化する", metavar="n")
    parser.add_argument("--set-of", type=base_int,
            help="FR(overflow flag)を指定した値で初期化する", metavar="n")
    parser.add_argument("--pre-exec", help="asmfile開始前に実行するcasl2 code", metavar="prefile")
    parser.add_argument("--post-exec", help="asmfile終了後に実行するcasl2 code", metavar="postfile")

    args = parser.parse_args()

    # TODO

if __name__ == "__main__":
    main()
