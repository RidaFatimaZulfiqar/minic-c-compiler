# MiniC: Technical Documentation

## 1. Overview
MiniC compiles a subset of C to x86-64 assembly. Everything is hand-written in `minic.py` (about 600 lines): no parser generators and no compiler libraries. gcc is used only as an assembler and linker.

## 1b. Web demo
`index.html` is a JavaScript port of the compiler that runs in the browser (host it free with GitHub Pages). It was checked against the Python version: the generated assembly is identical for every example, and the program output matches.

## 2. Pipeline
```
 source.c ─▶ LEXER ─▶ tokens ─▶ PARSER ─▶ AST ─▶ SEMANTIC CHECK ─┬▶ CODE GENERATOR ─▶ .s ─▶ gcc ─▶ executable
                                                                 └▶ INTERPRETER ─▶ output
```

## 3. Grammar
```
program     = function*
function    = "int" ID "(" [ "int" ID { "," "int" ID } ] ")" block
block       = "{" statement* "}"
statement   = "int" ID [ "=" expr ] ";"
            | "if" "(" expr ")" statement [ "else" statement ]
            | "while" "(" expr ")" statement
            | "for" "(" ( declaration | [expr] ";" ) [expr] ";" [expr] ")" statement
            | "return" expr ";"
            | block
            | expr ";"
expr        = ID "=" expr | or
or          = and { "||" and }
and         = equality { "&&" equality }
equality    = relational { ("==" | "!=") relational }
relational  = additive { ("<" | ">" | "<=" | ">=") additive }
additive    = term { ("+" | "-") term }
term        = unary { ("*" | "/" | "%") unary }
unary       = ("-" | "!") unary | primary
primary     = NUM | ID | ID "(" [args] ")" | "(" expr ")"
```
Each precedence level is one row of the `LEVELS` table, so adding an operator is a one-line change.

## 4. Stages in detail

### 4.1 Lexer
One compiled regular expression with named groups (whitespace and comments, numbers, identifiers, operators). Keywords are identifiers found in the `KEYWORDS` set. Each token stores its line number for error messages. Unknown characters raise `CompileError`.

### 4.2 Parser
Recursive descent: one method per grammar rule. `binary(level)` handles all left-associative binary operators, so `10 - 4 - 3` is `(10 - 4) - 3`. Assignment is right-associative and its left side must be a variable.

AST nodes are plain tuples, for example `("bin", "+", ("num", 1), ("var", "x", 3))`. Inspect one with `--ast`.

### 4.3 Semantic check
Walks the AST with a stack of scopes. It reports: undeclared variable, variable declared twice in one scope, undefined function, wrong number of arguments, duplicate parameter, more than 6 parameters, missing `main`. Messages include the line number.

### 4.4 Code generator
A stack-machine design: every expression leaves its result in `%rax`.

- **Binary operators:** evaluate left, `push`, evaluate right, move to `%rcx`, `pop` left into `%rax`, then apply the instruction. Division uses `cqto` and `idivq`; `%` takes the remainder from `%rdx`. Comparisons use `cmpq` and `setcc`.
- **Variables:** every local lives in a stack slot at a negative offset from `%rbp`. The frame size is computed before the function body (parameters plus declarations) and rounded up to a multiple of 16.
- **Calls (System V AMD64):** arguments are pushed, then popped into `%rdi, %rsi, %rdx, %rcx, %r8, %r9`. The generator tracks push depth, and when it is odd it adds 8 bytes of padding so `%rsp` is 16-byte aligned at every `call`.
- **Short-circuit:** `&&` and `||` use conditional jumps, so the right side runs only when needed.
- **Control flow:** `if`, `while` and `for` are compiled to labels and jumps (`.L1`, `.L2`, ...). `return` jumps to the function's epilogue (`leave; ret`). Falling off the end returns 0.
- **print:** calls `printf("%d\n", value)`.

### 4.5 Interpreter
Executes the AST directly with a stack of environments. It copies C behaviour: integer division truncates toward zero, `&&` and `||` short-circuit. Limits protect against infinite loops (20 million steps) and runaway recursion (depth 1000).

## 5. Design decisions
| Decision | Reason |
|---|---|
| Tuples for the AST | short, easy to print and test |
| Stack-machine codegen | simplest correct approach; no register allocator needed |
| Interpreter as well as native backend | runs anywhere and acts as a reference to test the compiler against |
| gcc only for assemble and link | writing an assembler and linker is a separate project |
| Left operand evaluated first, everywhere | interpreter and compiler give identical results |

## 6. Testing
`tests/test_minic.py` has 10 tests: example outputs, division rounding (`-7/2 = -3`, `-7%2 = -1`), short-circuit evaluation, precedence, 5 error cases, and a native-versus-interpreter comparison for every example. Run: `python3 -m unittest discover -s tests -v`.

## 7. Limitations and future work
No pointers, arrays, strings, structs or floating point. `int` is 64-bit rather than 32-bit. No optimizer. Linux x86-64 only for native output. Next steps: constant folding, `break`/`continue`, arrays and pointers, `char` and strings, a type checker, an ARM64 backend, register allocation.

## 8. Report and presentation outline
1. Introduction: what a compiler is and why build one
2. Language specification (grammar, section 3)
3. Architecture diagram (section 2)
4. Lexer, parser, semantic analysis, code generation (section 4)
5. Example walkthrough: `gcd.c` from source to `--tokens`, `--ast`, `--asm`
6. Testing and results (section 6)
7. Limitations and future work
8. Conclusion

## 9. Repository details
**Name:** `minic-compiler`
**Description:** A C compiler written from scratch in Python: lexer, parser, semantic checks and x86-64 code generation, plus an interpreter.
**Topics:** `compiler`, `c`, `python`, `lexer`, `parser`, `x86-64`, `assembly`, `code-generation`, `interpreter`, `computer-science`

## 10. Sample LinkedIn post
> I built MiniC, a C compiler written from scratch in Python. It has a lexer, a recursive-descent parser, semantic checks and an x86-64 code generator that produces real native executables, plus an interpreter I use to verify the compiler's output. 10 automated tests pass. Code and docs: https://github.com/ridafatimazulfiqar/minic-compiler #Compilers #Python #ComputerScience #OpenSource
