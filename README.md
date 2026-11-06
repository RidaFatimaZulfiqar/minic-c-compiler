# MiniC: a C compiler written from scratch

**A small C compiler in pure Python. It reads C source code, builds a syntax tree, checks it for errors and generates real x86-64 assembly that gcc turns into a native executable. It also includes an interpreter, so programs run on any machine.**

Repository: https://github.com/ridafatimazulfiqar/minic-compiler

**Live demo (runs in your browser):** https://ridafatimazulfiqar.github.io/minic-compiler/

**What I built:** a working compiler for a C subset, with every classic stage written by hand and no parser generators or compiler libraries. Output was verified: all example programs give identical results when interpreted and when compiled to native code (10 automated tests).

| Compiler stage | Where | What it does |
|---|---|---|
| Lexer | `lex()` | regular-expression tokenizer, tracks line numbers, skips comments |
| Parser | `Parser` | recursive descent, correct operator precedence, builds an AST |
| Semantic analysis | `check()` | undeclared variables, redeclarations, undefined functions, wrong argument counts, missing `main` |
| Code generator | `CodeGen` | x86-64 assembly, System V calling convention, stack frames, 16-byte stack alignment, short-circuit `&&` and `||` |
| Interpreter | `interpret()` | runs the AST directly, C-style division, step and recursion limits |
| Driver | `main()` | `--tokens`, `--ast`, `--asm`, `--run`, `-o` |

**Skills shown:** compiler design, algorithms and data structures, assembly and calling conventions, error handling with line numbers, unit testing, clear documentation.

**Try it in 30 seconds:** open the live demo, pick an example and press Run to see tokens, syntax tree, assembly and output. Or from the command line:
```bash
python3 minic.py examples/factorial.c          # run with the interpreter
python3 minic.py examples/factorial.c --asm    # see the generated assembly
python3 minic.py examples/primes.c -o primes   # build a native executable (Linux x86-64 + gcc)
./primes
```

## The language
```c
int factorial(int n) {
    if (n <= 1) return 1;
    return n * factorial(n - 1);
}
int main() {
    for (int i = 1; i <= 5; i = i + 1) print(factorial(i));
    return 0;
}
```
Supported: `int` variables and functions (up to 6 parameters), `+ - * / %`, `< > <= >= == !=`, `&& || !`, unary `-`, assignment, `if/else`, `while`, `for`, `return`, recursion, block scopes, `//` and `/* */` comments, and the built-in `print(expr)`.

## Usage
| Command | Result |
|---|---|
| `python3 minic.py file.c` | run with the interpreter |
| `python3 minic.py file.c --tokens` | show tokens |
| `python3 minic.py file.c --ast` | show the syntax tree |
| `python3 minic.py file.c --asm` | print x86-64 assembly |
| `python3 minic.py file.c -o out` | build a native executable (needs gcc) |

Example error message: `error: line 4: 'x' is not declared`

## Tests
```bash
python3 -m unittest discover -s tests -v
```
Covers examples, C division rules, short-circuiting, precedence, five kinds of compile errors, and native output matching the interpreter (skipped automatically when gcc or x86-64 Linux is not available).

## Project structure
```
minic-compiler/
├── index.html            browser demo: JavaScript port of the compiler (GitHub Pages)
├── minic.py              the whole compiler in Python
├── examples/             hello, factorial, fibonacci, primes, gcd
├── tests/test_minic.py
├── docs/DOCUMENTATION.md architecture, grammar, design decisions, report outline
├── LICENSE
└── README.md
```

## Limitations
Only `int` (64-bit), no pointers, arrays, strings or structs, no optimizer. The native backend targets Linux x86-64 and needs gcc only to assemble and link. On Windows use WSL, or use the interpreter.

## Roadmap
Arrays and pointers, `char` and strings, `printf`, a simple optimizer (constant folding), `break` and `continue`, a type checker, an ARM64 backend.

## License
MIT
