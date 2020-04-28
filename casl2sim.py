#!/usr/bin/env python3
# coding:utf-8
"""
CASL2シミュレータ
"""
import argparse
import collections
import re
import sys


RE_LABEL_OP = re.compile(r"\([A-Z]+\):\(.*\)")
RE_OP = re.compile(r"\s+[A-Z].*")
RE_COMMENT = re.compile(r";.*")
RE_DC = re.compile(r"\s+DC\s")
RE_DC_ARG = re.compile(r"('(''|[^'])+'|[0-9]+|#[0-9A-Fa-f]+|[A-Z][0-9A-Z]*)(.*)")

"""
  メモリの1要素分のデータ構造

  value: int  この要素の値
  line:  int  (debug用) asmでの行番号を格納する asmと無関係または実行時に書き換えられた場合は0
"""
Element = collections.namedtuple("Element", ["value", "line"])

def err_exit(msg):
    print(msg)
    sys.exit(1)

class Parser:
    def __init__(self, input_):
        self._input = input_
        self._mem = []
        # 未解決のラベルを格納する要素を保持する {ラベル名(str):[格納先の要素(Element), ...]}
        # keyが重複した場合、リストに追加していく
        self._unresolved_labels = {}
        # ラベルの実際の値を保持する {ラベル名(str):実際の番地(int)}
        # keyが重複した場合、エラー
        self._actual_labels = {}
        # 開始位置 (START疑似命令の指定先)
        self._start = -1
        # 終了位置
        self._end = -1
        # 解析中の行番号
        self._line_num = 0

    def add_unresolved_label(self, label, elem):
        if label not in self._unresolved_labels:
            self._unresolved_labels[label] = []
        self._unresolved_labels[label].append(elem)

    def set_actual_label(self, label, line_num):
        if self._actual_labels[label] is not None:
            err_exit("duplicate label ({label})")
        self._actual_labels[label] = line_num

    def resolve_label(self):
        pass

    def get_mem(self):
        return self._mem[:]

    def parse(self):
        pass

    def parse_line(self, line):
        """
        lineを解析する
        解析の結果追加されるメモリのリストを返す
        """
        line_ = re.sub(RE_COMMENT, "", line)
        if len(line_.strip()) == 0:
            return []
        label = None
        m = re.match(RE_LABEL_OP, line_)
        if m is not None:
            label = m.group(1)
            line_ = m.group(2)
        m = re.match(RE_OP, line_)
        if m is None:
            err_exit(f"syntax error ({line})")
        tokens = line_.strip().split()

    def parse_DC(self, line):
        args = re.sub(RE_DC, "", line)
        m = re.match(RE_DC_ARG, args)
        # 最低1つは引数がある前提
        arg = m.group(1)
        args = m.group(3).strip()
        mem = self.parse_DC_arg(arg)
        while len(args) != 0:
            if args[0] != ",":
                err_exit("syntax error ',' ({line})")
            args = args[1:].strip()
            m = re.match(RE_DC_ARG, args)
            arg = m.group(1)
            args = m.group(3)
            mem.extend(self.parse_DC_arg(arg))
        return mem

    def parse_DC_arg(self, arg):
        ln = self._line_num
        mem = []
        if arg[0] == "'":
            # 文字列
            st = arg[1:-1].replace("''", "'")
            for s in st:
                mem.append(Element(ord(s)&0xff, ln))
        elif arg[0] == "#":
            # 16進数
            mem.append(Element(int(arg[1:], 16), ln))
        elif arg[0].isdecimal():
            # 10進数
            mem.append(Element(int(arg), ln))
        else:
            # ラベル
            elem = Element(0, ln)
            self.add_unresolved_label(arg, elem)
            mem.append(elem)
        return mem

    def op_1word(self, label, opcode, operand1, operand2):
        pass

    def op_2word(self, label, opcode, operand1, operand2, operand3):
        pass
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

    print("test")
    p = Parser(None)
    a = p.parse_DC(" DC 12, #000f, LAB, 'abcd''e'''")
    print(a)
    c = Comet2()

if __name__ == "__main__":
    main()
