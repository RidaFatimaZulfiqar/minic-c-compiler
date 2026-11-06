#!/usr/bin/env python3
"""MiniC: a small C compiler written from scratch in Python.

Pipeline:  source -> lex -> parse (AST) -> semantic check -> x86-64 assembly -> gcc (assemble + link)
Also has an AST interpreter (--run) so programs run on any machine, even without gcc.

Supported language: int variables and functions (up to 6 parameters), arithmetic
(+ - * / %), comparisons, && || !, assignment, if/else, while, for, return,
recursion, and the built-in print(expr) which prints an integer and a newline.
"""
import argparse
import os
import pprint
import re
import shutil
import subprocess
import sys
import tempfile


class CompileError(Exception):
    pass


# ----------------------------------------------------------------- 1. LEXER
KEYWORDS = {"int", "if", "else", "while", "for", "return"}
TOKEN_RE = re.compile(r"""
    (?P<ws>\s+|//[^\n]*|/\*.*?\*/)
   |(?P<num>\d+)
   |(?P<id>[A-Za-z_]\w*)
   |(?P<op>==|!=|<=|>=|&&|\|\||[-+*/%<>=!(){};,])
""", re.X | re.S)


def lex(src):
    """Turn source text into a list of (kind, text, line) tokens."""
    tokens, pos, line = [], 0, 1
    while pos < len(src):
        m = TOKEN_RE.match(src, pos)
        if not m:
            raise CompileError(f"line {line}: unexpected character {src[pos]!r}")
        kind, text = m.lastgroup, m.group()
        if kind == "ws":
            line += text.count("\n")
        elif kind == "id" and text in KEYWORDS:
            tokens.append(("kw", text, line))
        else:
            tokens.append((kind, text, line))
        pos = m.end()
    tokens.append(("eof", "", line))
    return tokens


# ---------------------------------------------------------------- 2. PARSER
# AST nodes are tuples.
#   expr: ("num",v) ("var",name,line) ("assign",name,e,line) ("un",op,e)
#         ("bin",op,l,r) ("call",name,args,line)
#   stmt: ("block",[..]) ("decl",name,init) ("expr",e) ("if",c,t,e)
#         ("while",c,b) ("for",init,cond,post,b) ("ret",e)
#   function: (name, params, body)
LEVELS = [["||"], ["&&"], ["==", "!="], ["<", ">", "<=", ">="], ["+", "-"], ["*", "/", "%"]]


class Parser:
    def __init__(self, tokens):
        self.t, self.i = tokens, 0

    def peek(self):
        return self.t[self.i]

    def at(self, text):
        kind, value, _ = self.peek()
        return value == text and kind in ("op", "kw")

    def eat(self, text=None, kind=None):
        k, v, line = self.peek()
        if text is not None and not (v == text and k in ("op", "kw")):
            raise CompileError(f"line {line}: expected '{text}' but found '{v or 'end of file'}'")
        if kind is not None and k != kind:
            raise CompileError(f"line {line}: expected {kind} but found '{v or 'end of file'}'")
        self.i += 1
        return v

    def program(self):
        funcs = []
        while self.peek()[0] != "eof":
            funcs.append(self.function())
        return funcs

    def function(self):
        self.eat("int")
        name = self.eat(kind="id")
        self.eat("(")
        params = []
        if not self.at(")"):
            while True:
                self.eat("int")
                params.append(self.eat(kind="id"))
                if not self.at(","):
                    break
                self.eat(",")
        self.eat(")")
        return (name, params, self.block())

    def block(self):
        self.eat("{")
        stmts = []
        while not self.at("}"):
            stmts.append(self.statement())
        self.eat("}")
        return ("block", stmts)

    def declaration(self):
        self.eat("int")
        name = self.eat(kind="id")
        init = None
        if self.at("="):
            self.eat("=")
            init = self.expression()
        self.eat(";")
        return ("decl", name, init)

    def statement(self):
        if self.at("int"):
            return self.declaration()
        if self.at("{"):
            return self.block()
        if self.at("if"):
            self.eat("if"); self.eat("(")
            cond = self.expression()
            self.eat(")")
            then = self.statement()
            other = None
            if self.at("else"):
                self.eat("else")
                other = self.statement()
            return ("if", cond, then, other)
        if self.at("while"):
            self.eat("while"); self.eat("(")
            cond = self.expression()
            self.eat(")")
            return ("while", cond, self.statement())
        if self.at("for"):
            self.eat("for"); self.eat("(")
            if self.at("int"):
                init = self.declaration()
            elif self.at(";"):
                self.eat(";"); init = None
            else:
                init = ("expr", self.expression()); self.eat(";")
            cond = None if self.at(";") else self.expression()
            self.eat(";")
            post = None if self.at(")") else self.expression()
            self.eat(")")
            return ("for", init, cond, post, self.statement())
        if self.at("return"):
            self.eat("return")
            value = self.expression()
            self.eat(";")
            return ("ret", value)
        value = self.expression()
        self.eat(";")
        return ("expr", value)

    def expression(self):
        left = self.binary(0)
        if self.at("="):
            line = self.peek()[2]
            if left[0] != "var":
                raise CompileError(f"line {line}: left side of '=' must be a variable")
            self.eat("=")
            return ("assign", left[1], self.expression(), line)
        return left

    def binary(self, level):
        if level == len(LEVELS):
            return self.unary()
        left = self.binary(level + 1)
        while self.peek()[0] == "op" and self.peek()[1] in LEVELS[level]:
            op = self.eat()
            left = ("bin", op, left, self.binary(level + 1))
        return left

    def unary(self):
        if self.at("-") or self.at("!"):
            return ("un", self.eat(), self.unary())
        return self.primary()

    def primary(self):
        kind, value, line = self.peek()
        if kind == "num":
            self.i += 1
            return ("num", int(value))
        if kind == "id":
            self.i += 1
            if self.at("("):
                self.eat("(")
                args = []
                if not self.at(")"):
                    args.append(self.expression())
                    while self.at(","):
                        self.eat(",")
                        args.append(self.expression())
                self.eat(")")
                return ("call", value, args, line)
            return ("var", value, line)
        if self.at("("):
            self.eat("(")
            e = self.expression()
            self.eat(")")
            return e
        raise CompileError(f"line {line}: unexpected '{value or 'end of file'}'")


# --------------------------------------------------------- 3. SEMANTIC CHECK
def check(prog):
    funcs = {"print": 1}
    for name, params, _ in prog:
        if name in funcs:
            raise CompileError(f"function '{name}' is defined twice")
        if len(params) > 6:
            raise CompileError(f"function '{name}': at most 6 parameters are supported")
        if len(set(params)) != len(params):
            raise CompileError(f"function '{name}': duplicate parameter name")
        funcs[name] = len(params)
    if "main" not in funcs:
        raise CompileError("no 'main' function")

    def expr(e, scopes):
        k = e[0]
        if k in ("var", "assign"):
            if not any(e[1] in s for s in scopes):
                raise CompileError(f"line {e[-1]}: '{e[1]}' is not declared")
            if k == "assign":
                expr(e[2], scopes)
        elif k == "un":
            expr(e[2], scopes)
        elif k == "bin":
            expr(e[2], scopes); expr(e[3], scopes)
        elif k == "call":
            if e[1] not in funcs:
                raise CompileError(f"line {e[3]}: function '{e[1]}' is not defined")
            if len(e[2]) != funcs[e[1]]:
                raise CompileError(f"line {e[3]}: '{e[1]}' expects {funcs[e[1]]} argument(s), got {len(e[2])}")
            for a in e[2]:
                expr(a, scopes)

    def stmt(s, scopes):
        k = s[0]
        if k == "block":
            scopes.append(set())
            for x in s[1]:
                stmt(x, scopes)
            scopes.pop()
        elif k == "decl":
            if s[2]:
                expr(s[2], scopes)
            if s[1] in scopes[-1]:
                raise CompileError(f"'{s[1]}' is declared twice in the same scope")
            scopes[-1].add(s[1])
        elif k in ("expr", "ret"):
            expr(s[1], scopes)
        elif k == "if":
            expr(s[1], scopes); stmt(s[2], scopes)
            if s[3]:
                stmt(s[3], scopes)
        elif k == "while":
            expr(s[1], scopes); stmt(s[2], scopes)
        elif k == "for":
            scopes.append(set())
            if s[1]:
                stmt(s[1], scopes)
            if s[2]:
                expr(s[2], scopes)
            if s[3]:
                expr(s[3], scopes)
            stmt(s[4], scopes)
            scopes.pop()

    for _, params, body in prog:
        stmt(body, [set(params)])


# ---------------------------------------------------- 4. CODE GENERATOR (x86-64)
ARG_REGS = ["%rdi", "%rsi", "%rdx", "%rcx", "%r8", "%r9"]
SETCC = {"<": "l", ">": "g", "<=": "le", ">=": "ge", "==": "e", "!=": "ne"}


def count_decls(s):
    if s is None:
        return 0
    k = s[0]
    if k == "decl":
        return 1
    if k == "block":
        return sum(count_decls(x) for x in s[1])
    if k == "if":
        return count_decls(s[2]) + count_decls(s[3])
    if k == "while":
        return count_decls(s[2])
    if k == "for":
        return count_decls(s[1]) + count_decls(s[4])
    return 0


class CodeGen:
    """Stack-machine style generator: every expression leaves its value in %rax."""

    def __init__(self):
        self.out, self.n = [], 0

    def emit(self, line):
        self.out.append(line if line.endswith(":") else "    " + line)

    def label(self):
        self.n += 1
        return f".L{self.n}"

    def push(self):
        self.emit("pushq %rax"); self.depth += 1

    def pop(self, reg):
        self.emit(f"popq {reg}"); self.depth -= 1

    def program(self, prog):
        self.emit(".section .rodata")
        self.emit(".Lfmt:")
        self.emit('.string "%d\\n"')
        self.emit(".text")
        for f in prog:
            self.function(f)
        self.emit('.section .note.GNU-stack,"",@progbits')
        return "\n".join(self.out) + "\n"

    def function(self, f):
        name, params, body = f
        slots = len(params) + count_decls(body)
        frame = (slots * 8 + 15) // 16 * 16
        self.scopes, self.next_slot, self.depth, self.ret = [{}], 0, 0, f".Lret_{name}"
        self.emit(f".globl {name}")
        self.emit(f"{name}:")
        self.emit("pushq %rbp"); self.emit("movq %rsp, %rbp")
        if frame:
            self.emit(f"subq ${frame}, %rsp")
        for reg, p in zip(ARG_REGS, params):
            off = self.alloc(p)
            self.emit(f"movq {reg}, {off}(%rbp)")
        self.stmt(body)
        self.emit("movq $0, %rax")  # falling off the end returns 0
        self.emit(f"{self.ret}:")
        self.emit("leave"); self.emit("ret")

    def alloc(self, name):
        self.next_slot += 1
        off = -8 * self.next_slot
        self.scopes[-1][name] = off
        return off

    def find(self, name):
        for s in reversed(self.scopes):
            if name in s:
                return s[name]

    def stmt(self, s):
        k = s[0]
        if k == "block":
            self.scopes.append({})
            for x in s[1]:
                self.stmt(x)
            self.scopes.pop()
        elif k == "decl":
            if s[2]:
                self.expr(s[2])
            off = self.alloc(s[1])
            self.emit(f"movq %rax, {off}(%rbp)" if s[2] else f"movq $0, {off}(%rbp)")
        elif k == "expr":
            self.expr(s[1])
        elif k == "ret":
            self.expr(s[1]); self.emit(f"jmp {self.ret}")
        elif k == "if":
            other, end = self.label(), self.label()
            self.expr(s[1]); self.emit("cmpq $0, %rax"); self.emit(f"je {other}")
            self.stmt(s[2]); self.emit(f"jmp {end}")
            self.emit(f"{other}:")
            if s[3]:
                self.stmt(s[3])
            self.emit(f"{end}:")
        elif k == "while":
            top, end = self.label(), self.label()
            self.emit(f"{top}:")
            self.expr(s[1]); self.emit("cmpq $0, %rax"); self.emit(f"je {end}")
            self.stmt(s[2]); self.emit(f"jmp {top}")
            self.emit(f"{end}:")
        elif k == "for":
            top, end = self.label(), self.label()
            self.scopes.append({})
            if s[1]:
                self.stmt(s[1])
            self.emit(f"{top}:")
            if s[2]:
                self.expr(s[2]); self.emit("cmpq $0, %rax"); self.emit(f"je {end}")
            self.stmt(s[4])
            if s[3]:
                self.expr(s[3])
            self.emit(f"jmp {top}")
            self.emit(f"{end}:")
            self.scopes.pop()

    def expr(self, e):
        k = e[0]
        if k == "num":
            self.emit(f"movq ${e[1]}, %rax" if abs(e[1]) < 2**31 else f"movabsq ${e[1]}, %rax")
        elif k == "var":
            self.emit(f"movq {self.find(e[1])}(%rbp), %rax")
        elif k == "assign":
            self.expr(e[2]); self.emit(f"movq %rax, {self.find(e[1])}(%rbp)")
        elif k == "un":
            self.expr(e[2])
            if e[1] == "-":
                self.emit("negq %rax")
            else:
                self.emit("cmpq $0, %rax"); self.emit("sete %al"); self.emit("movzbq %al, %rax")
        elif k == "bin":
            self.binary(e)
        elif k == "call":
            self.call(e)

    def binary(self, e):
        op = e[1]
        if op in ("&&", "||"):
            short, end = self.label(), self.label()
            jump = "je" if op == "&&" else "jne"
            for side in (e[2], e[3]):
                self.expr(side); self.emit("cmpq $0, %rax"); self.emit(f"{jump} {short}")
            self.emit(f"movq ${1 if op == '&&' else 0}, %rax"); self.emit(f"jmp {end}")
            self.emit(f"{short}:")
            self.emit(f"movq ${0 if op == '&&' else 1}, %rax")
            self.emit(f"{end}:")
            return
        self.expr(e[2]); self.push()
        self.expr(e[3]); self.emit("movq %rax, %rcx"); self.pop("%rax")
        if op == "+":
            self.emit("addq %rcx, %rax")
        elif op == "-":
            self.emit("subq %rcx, %rax")
        elif op == "*":
            self.emit("imulq %rcx, %rax")
        elif op in ("/", "%"):
            self.emit("cqto"); self.emit("idivq %rcx")
            if op == "%":
                self.emit("movq %rdx, %rax")
        else:
            self.emit("cmpq %rcx, %rax"); self.emit(f"set{SETCC[op]} %al"); self.emit("movzbq %al, %rax")

    def call(self, e):
        name, args = e[1], e[2]
        for a in args:
            self.expr(a); self.push()
        for i in reversed(range(len(args))):
            self.pop(ARG_REGS[i])
        pad = self.depth % 2  # keep %rsp 16-byte aligned at the call
        if pad:
            self.emit("subq $8, %rsp")
        if name == "print":
            self.emit("movq %rdi, %rsi"); self.emit("leaq .Lfmt(%rip), %rdi")
            self.emit("xorl %eax, %eax"); self.emit("call printf@PLT")
        else:
            self.emit(f"call {name}")
        if pad:
            self.emit("addq $8, %rsp")


# ------------------------------------------------------------ 5. INTERPRETER
class _Return(Exception):
    def __init__(self, value):
        self.value = value


def interpret(prog, out=print, max_steps=20_000_000):
    """Run the AST directly. Same results as the compiled program."""
    funcs = {f[0]: f for f in prog}
    steps = [0]
    sys.setrecursionlimit(50_000)

    def lookup(env, name):
        for scope in reversed(env):
            if name in scope:
                return scope

    def ev(e, env, depth):
        k = e[0]
        if k == "num":
            return e[1]
        if k == "var":
            return lookup(env, e[1])[e[1]]
        if k == "assign":
            v = ev(e[2], env, depth)
            lookup(env, e[1])[e[1]] = v
            return v
        if k == "un":
            v = ev(e[2], env, depth)
            return -v if e[1] == "-" else int(v == 0)
        if k == "bin":
            op = e[1]
            if op == "&&":
                return int(ev(e[2], env, depth) != 0 and ev(e[3], env, depth) != 0)
            if op == "||":
                return int(ev(e[2], env, depth) != 0 or ev(e[3], env, depth) != 0)
            a, b = ev(e[2], env, depth), ev(e[3], env, depth)
            if op in ("/", "%"):
                if b == 0:
                    raise RuntimeError("division by zero")
                q = abs(a) // abs(b)
                q = -q if (a < 0) != (b < 0) else q  # C truncates toward zero
                return q if op == "/" else a - q * b
            return {"+": a + b, "-": a - b, "*": a * b, "<": int(a < b), ">": int(a > b),
                    "<=": int(a <= b), ">=": int(a >= b), "==": int(a == b), "!=": int(a != b)}[op]
        args = [ev(a, env, depth) for a in e[2]]
        if e[1] == "print":
            out(str(args[0]))
            return 0
        if depth > 1000:
            raise RuntimeError("stack overflow (recursion too deep)")
        _, params, body = funcs[e[1]]
        try:
            ex(body, [dict(zip(params, args))], depth + 1)
        except _Return as r:
            return r.value
        return 0

    def ex(s, env, depth):
        steps[0] += 1
        if steps[0] > max_steps:
            raise RuntimeError("step limit exceeded (infinite loop?)")
        k = s[0]
        if k == "block":
            env.append({})
            try:
                for x in s[1]:
                    ex(x, env, depth)
            finally:
                env.pop()
        elif k == "decl":
            env[-1][s[1]] = ev(s[2], env, depth) if s[2] else 0
        elif k == "expr":
            ev(s[1], env, depth)
        elif k == "ret":
            raise _Return(ev(s[1], env, depth))
        elif k == "if":
            if ev(s[1], env, depth):
                ex(s[2], env, depth)
            elif s[3]:
                ex(s[3], env, depth)
        elif k == "while":
            while ev(s[1], env, depth):
                ex(s[2], env, depth)
        elif k == "for":
            env.append({})
            try:
                if s[1]:
                    ex(s[1], env, depth)
                while s[2] is None or ev(s[2], env, depth):
                    ex(s[4], env, depth)
                    if s[3]:
                        ev(s[3], env, depth)
            finally:
                env.pop()

    try:
        ex(funcs["main"][2], [{}], 0)
    except _Return as r:
        return r.value
    return 0


# ----------------------------------------------------------------------- CLI
def compile_source(src):
    tokens = lex(src)
    prog = Parser(tokens).program()
    check(prog)
    return tokens, prog


def main(argv=None):
    ap = argparse.ArgumentParser(description="MiniC: a small C compiler written in Python")
    ap.add_argument("file", help="MiniC source file (.c)")
    ap.add_argument("--tokens", action="store_true", help="print the token list")
    ap.add_argument("--ast", action="store_true", help="print the syntax tree")
    ap.add_argument("--asm", action="store_true", help="print x86-64 assembly")
    ap.add_argument("--run", action="store_true", help="run with the built-in interpreter (default)")
    ap.add_argument("-o", metavar="OUT", help="build a native executable with gcc (Linux x86-64)")
    args = ap.parse_args(argv)
    try:
        with open(args.file, encoding="utf-8") as f:
            tokens, prog = compile_source(f.read())
        if args.tokens:
            for t in tokens:
                print(t)
        if args.ast:
            pprint.pprint(prog, width=100)
        if args.asm or args.o:
            asm = CodeGen().program(prog)
            if args.asm:
                print(asm)
            if args.o:
                if not shutil.which("gcc"):
                    raise CompileError("gcc not found: needed to assemble and link (use --run instead)")
                with tempfile.NamedTemporaryFile("w", suffix=".s", delete=False) as tmp:
                    tmp.write(asm)
                try:
                    subprocess.run(["gcc", tmp.name, "-o", args.o], check=True)
                finally:
                    os.unlink(tmp.name)
                print(f"built {args.o}")
        if args.run or not (args.tokens or args.ast or args.asm or args.o):
            return interpret(prog)
    except CompileError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    except RuntimeError as e:
        print(f"runtime error: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
