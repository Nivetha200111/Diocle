"""The verified subset of embedded SQL (EXEC SQL): parsing, classification and exact refusal reasons.

Deterministic, no database needed. The verifier's precompiler (services/verifier/diocle_verifier/sqlpre.py) uses the
same parse, so what the analyzer accepts is exactly what can be rewritten and run.

Subset `db2-subset-1`:
  INCLUDE SQLCA; INCLUDE <copybook>; DECLARE t TABLE (...); WHENEVER ... CONTINUE;
  SELECT cols|COUNT(*)|SUM/MIN/MAX(col) INTO :h [:ind] FROM t [WHERE cond] [ORDER BY cols];
  INSERT INTO t [(cols)] VALUES (:h | literal | NULL, ...);   every column must be supplied
  UPDATE t SET col = :h | literal | NULL | col +/- :h|literal [, ...] [WHERE cond];
  DELETE FROM t [WHERE cond];
  DECLARE c CURSOR FOR SELECT cols FROM t [WHERE cond] ORDER BY cols;  OPEN c; FETCH c INTO :h [:ind], ...; CLOSE c;
  COMMIT [WORK]; ROLLBACK [WORK];
  cond := col (= <> < > <= >=) :h|literal | col IS [NOT] NULL, joined by AND / OR, parentheses allowed.
  Column types: CHAR(n), VARCHAR(n), SMALLINT, INTEGER, BIGINT, DECIMAL(p,s) with p <= 18.
Everything else is refused with the exact reason (dynamic SQL, joins, subselects, functions, FETCH FIRST, WITH UR,
FOR UPDATE, WHERE CURRENT OF, special registers, LOBs, multi-row, SQLDA, ...). CICS and IMS are out of scope.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .cobol import _PIC, _entries, _expand, _usage, source_lines

SUBSET_VERSION = "db2-subset-1"

_START = re.compile(r"\bEXEC\s+SQL\b", re.I)
_END = re.compile(r"\bEND-EXEC\b", re.I)
_TOKEN = re.compile(r"'(?:[^']|'')*'|:[A-Z][A-Z0-9-]*|[0-9]+(?:\.[0-9]+)?|[A-Z_][A-Z0-9_#@$]*|<>|<=|>=|\|\||[(),.=<>+\-*/]|\S", re.I)
_TYPE_NAMES = {"CHAR": "CHAR", "CHARACTER": "CHAR", "VARCHAR": "VARCHAR", "SMALLINT": "SMALLINT", "INTEGER": "INTEGER",
               "INT": "INTEGER", "BIGINT": "BIGINT", "DECIMAL": "DECIMAL", "DEC": "DECIMAL", "NUMERIC": "DECIMAL"}
_INT_DIGITS = {"SMALLINT": 5, "INTEGER": 10, "BIGINT": 18}
WORK_DIGITS = 18  # numeric work items hold 18 digits in all: wide enough that the column check, not a MOVE, rejects overflow
MAX_HOSTS = 20


class Refused(Exception):
    """A statement outside the subset; the message is the exact reason shown to the user."""


@dataclass
class Col:
    name: str
    type: str
    length: int = 0
    precision: int = 0
    scale: int = 0
    nullable: bool = True

    def as_dict(self) -> dict:
        d: dict = {"name": self.name, "type": self.type, "nullable": self.nullable}
        if self.type in ("CHAR", "VARCHAR"):
            d["length"] = self.length
        if self.type == "DECIMAL":
            d.update(precision=self.precision, scale=self.scale)
        return d

    @property
    def is_text(self) -> bool:
        return self.type in ("CHAR", "VARCHAR")


@dataclass
class Table:
    name: str
    columns: list[Col]
    source: str = "declare"  # declare | dclgen | ddl
    path: str | None = None
    primary_key: list[str] = field(default_factory=list)

    def col(self, name: str) -> Col:
        for c in self.columns:
            if c.name == name:
                return c
        raise Refused(f"column {name} is not in table {self.name}")

    def as_dict(self) -> dict:
        return {"name": self.name, "source": self.source, "path": self.path, "primaryKey": self.primary_key,
                "columns": [c.as_dict() for c in self.columns]}

    @staticmethod
    def from_dict(d: dict) -> "Table":
        return Table(d["name"], [Col(c["name"], c["type"], c.get("length", 0), c.get("precision", 0), c.get("scale", 0),
                                     c.get("nullable", True)) for c in d["columns"]],
                     d.get("source", "declare"), d.get("path"), d.get("primaryKey", []))


@dataclass
class Bind:
    """One host variable passed to or from the engine, with the work item the precompiler moves it through."""
    host: str
    indicator: str | None
    kind: str  # X (alphanumeric) or N (numeric)
    length: int  # X: bytes of the host variable; N: integer digits of the work item
    scale: int  # N: decimal digits (the column's scale)
    direction: str  # I or O

    def spec(self, no_indicator: bool = False) -> str:
        body = f"{self.direction}X{self.length}" if self.kind == "X" else f"{self.direction}N{self.length}.{self.scale}"
        return body + ("!" if no_indicator and self.direction == "O" and not self.indicator else "")


@dataclass
class Stmt:
    kind: str
    line: int
    tables: list[str] = field(default_factory=list)
    sql: str = ""  # physical SQL for the stand-in engine, host variables as ?
    inputs: list[Bind] = field(default_factory=list)
    outputs: list[Bind] = field(default_factory=list)
    cursor: str | None = None
    reason: str | None = None
    out_cols: list[Col] = field(default_factory=list)  # select list / cursor columns, for typing FETCH targets

    def as_dict(self) -> dict:
        d = {"kind": self.kind, "line": self.line, "inSubset": self.reason is None}
        if self.tables:
            d["tables"] = self.tables
        if self.reason:
            d["reason"] = self.reason
        return d


# --- source handling -----------------------------------------------------------------------------------------

@dataclass
class Block:
    first: int  # physical line index (0-based) of the line with EXEC SQL
    last: int  # physical line index of the line with END-EXEC
    text: str  # the statement between EXEC SQL and END-EXEC, one line
    prefix: str  # code before EXEC SQL on its first line
    suffix: str  # code after END-EXEC on its last line (usually the period)

    @property
    def line(self) -> int:
        return self.first + 1


def find_blocks(lines: list[str]) -> list[Block]:
    blocks, i = [], 0
    while i < len(lines):
        line = lines[i]
        code = line[7:72] if len(line) > 6 and line[6] not in "*/" else ""
        m = _START.search(code)
        if not m:
            i += 1
            continue
        parts, prefix, j = [], code[: m.start()], i
        rest = code[m.end():]
        while True:
            e = _END.search(rest)
            if e:
                parts.append(rest[: e.start()])
                suffix = rest[e.end():]
                break
            parts.append(rest)
            j += 1
            if j >= len(lines):
                suffix = ""
                break
            nxt = lines[j]
            rest = nxt[7:72] if len(nxt) > 6 and nxt[6] not in "*/" else ""
        blocks.append(Block(i, j, " ".join(p.strip() for p in parts).strip(), prefix.rstrip(), suffix.strip()))
        i = j + 1
    return blocks


def expand_includes(text: str, lookup, depth: int = 0) -> str:
    """Inline `EXEC SQL INCLUDE member END-EXEC` (not SQLCA) with the member's text; lookup(name) -> text | None."""
    lines = text.splitlines()
    out, last = [], 0
    for b in find_blocks(lines):
        m = re.fullmatch(r"INCLUDE\s+([A-Z0-9-]+)", b.text.upper())
        if not m or m.group(1) == "SQLCA":
            continue
        member = lookup(m.group(1)) if depth < 3 else None
        if member is None:
            continue
        out += lines[last:b.first] + expand_includes(member, lookup, depth + 1).splitlines()
        last = b.last + 1
    return "\n".join(out + lines[last:]) + "\n"


# --- host variables ------------------------------------------------------------------------------------------

def host_defs(text: str) -> dict[str, tuple]:
    """Data items by name: ("X", length) | ("N", digits, scale, signed) | ("group",) | ("other", why)."""
    defs: dict[str, tuple] = {}
    for entry in _entries(text):
        m = re.match(r"(\d\d)\s+([A-Z][A-Z0-9-]*)\b(.*)", entry, re.S)
        if not m or m.group(1) in ("66", "88"):
            continue
        name, rest = m.group(2), m.group(3)
        pic = _PIC.search(rest)
        if not pic:
            defs[name] = ("group",)
            continue
        usage = _usage(rest) or "display"
        p = _expand(pic.group(1))
        if usage in ("float4", "float8", "national", "unsupported") or "N" in p:
            defs[name] = ("other", f"{name}: floating-point or national data cannot be a host variable here")
        elif re.fullmatch(r"[XA]+", p):
            defs[name] = ("X", len(p))
        else:
            n = re.fullmatch(r"(S?)(9*)(?:V(9*))?", p)
            if not n or not (n.group(2) or n.group(3)):
                defs[name] = ("other", f"{name}: PIC {pic.group(1)} (edited or scaled) cannot be a host variable here")
            else:
                defs[name] = ("N", len(n.group(2)), len(n.group(3) or ""), n.group(1) == "S")
    return defs


# --- schema --------------------------------------------------------------------------------------------------

def _coltype(tokens: list[str], i: int, where: str) -> tuple[Col, int]:
    name = tokens[i]
    if not re.fullmatch(r"[A-Z][A-Z0-9_]*", name):
        raise Refused(f"{where}: column name {name} is outside the subset (letters, digits and underscores)")
    t = _TYPE_NAMES.get(tokens[i + 1] if i + 1 < len(tokens) else "")
    if t is None:
        raise Refused(f"{where}: column {name} has type {tokens[i + 1] if i + 1 < len(tokens) else '?'}, outside the subset "
                      "(CHAR, VARCHAR, SMALLINT, INTEGER, BIGINT, DECIMAL; no dates, timestamps, floats or LOBs)")
    i += 2
    col = Col(name, t)
    if t in ("CHAR", "VARCHAR", "DECIMAL"):
        if tokens[i:i + 1] != ["("] and t != "CHAR":
            raise Refused(f"{where}: {name} needs a length")
        if tokens[i:i + 1] == ["("]:
            j = tokens.index(")", i)
            nums = [x for x in tokens[i + 1:j] if x != ","]
            if not all(x.isdigit() for x in nums):
                raise Refused(f"{where}: {name} has an unreadable length")
            i = j + 1
            if t == "DECIMAL":
                col.precision, col.scale = int(nums[0]), int(nums[1]) if len(nums) > 1 else 0
                if not 1 <= col.precision <= 18 or col.scale > col.precision:
                    raise Refused(f"{where}: {name} DECIMAL({col.precision},{col.scale}) is outside the subset (precision 1 to 18)")
            else:
                col.length = int(nums[0])
        elif t == "CHAR":
            col.length = 1
        else:
            raise Refused(f"{where}: {name} DECIMAL needs a precision")
    elif t in _INT_DIGITS:
        col.precision = _INT_DIGITS[t]
    else:
        raise Refused(f"{where}: {name}: unsupported type")
    col.nullable = True
    return col, i


def parse_columns(tokens: list[str], where: str) -> tuple[list[Col], list[str]]:
    """Column definitions between the parentheses: NAME TYPE [NOT NULL] [PRIMARY KEY], ..., [PRIMARY KEY (a, b)]."""
    cols, pk, i = [], [], 0
    while i < len(tokens):
        if tokens[i] == "PRIMARY" and tokens[i + 1:i + 3] == ["KEY", "("]:
            j = tokens.index(")", i)
            pk = [x for x in tokens[i + 3:j] if x != ","]
            i = j + 1
        else:
            if tokens[i] in ("UNIQUE", "CONSTRAINT", "FOREIGN", "CHECK"):
                raise Refused(f"{where}: {tokens[i]} constraints are outside the subset")
            col, i = _coltype(tokens, i, where)
            while i < len(tokens) and tokens[i] != ",":
                if tokens[i:i + 2] == ["NOT", "NULL"]:
                    col.nullable = False
                    i += 2
                elif tokens[i:i + 2] == ["PRIMARY", "KEY"]:
                    col.nullable, pk, i = False, pk + [col.name], i + 2
                elif tokens[i:i + 2] == ["WITH", "DEFAULT"] or tokens[i] == "DEFAULT":
                    raise Refused(f"{where}: {col.name} has a DEFAULT; defaults are not modelled, so INSERT must supply every column")
                else:
                    raise Refused(f"{where}: unsupported clause {tokens[i]} in the definition of {col.name}")
            cols.append(col)
        if i < len(tokens) and tokens[i] == ",":
            i += 1
    if not cols:
        raise Refused(f"{where}: no columns")
    return cols, pk


def tokenize(text: str) -> list[str]:
    return [t if t.startswith("'") else t.upper() for t in _TOKEN.findall(text)]


def _table_from_tokens(tokens: list[str], source: str, path: str | None, where: str) -> Table:
    """tokens: NAME TABLE ( ... ) after DECLARE, or NAME ( ... ) after CREATE TABLE."""
    name = tokens[0]
    if not re.fullmatch(r"[A-Z][A-Z0-9_]*", name):
        raise Refused(f"{where}: table name {name} is outside the subset (letters, digits and underscores)")
    if tokens[1:2] == ["."]:
        raise Refused(f"{where}: schema-qualified table name {name}.{tokens[2]}; use an unqualified name")
    start = tokens.index("(")
    end = len(tokens) - 1 - tokens[::-1].index(")")
    cols, pk = parse_columns(tokens[start + 1:end], where)
    for k in pk:
        if k not in {c.name for c in cols}:
            raise Refused(f"{where}: PRIMARY KEY names unknown column {k}")
        next(c for c in cols if c.name == k).nullable = False
    return Table(name, cols, source, path, pk)


def parse_ddl(text: str, path: str) -> list[Table]:
    """CREATE TABLE statements of a *.sql file; a table outside the subset is skipped (and so never referenced)."""
    tables = []
    clean = re.sub(r"--[^\n]*", "", text)
    for stmt in clean.split(";"):
        tokens = tokenize(stmt)
        if tokens[:2] == ["CREATE", "TABLE"]:
            try:
                tables.append(_table_from_tokens(tokens[2:], "ddl", path, f"{path}"))
            except (Refused, ValueError, IndexError):
                continue
    return tables


# --- statements ----------------------------------------------------------------------------------------------

class _Ctx:
    def __init__(self, tables: dict[str, Table], hosts: dict[str, tuple]):
        self.tables, self.hosts = tables, hosts
        self.cursors: dict[str, Stmt] = {}
        self.open: set[str] = set()


class _P:
    """Token cursor for one statement."""

    def __init__(self, tokens: list[str], ctx: _Ctx):
        self.t, self.i, self.ctx = tokens, 0, ctx

    def peek(self, n: int = 0) -> str:
        return self.t[self.i + n] if self.i + n < len(self.t) else ""

    def take(self) -> str:
        v = self.peek()
        self.i += 1
        return v

    def accept(self, *words: str) -> bool:
        if self.t[self.i:self.i + len(words)] == list(words):
            self.i += len(words)
            return True
        return False

    def expect(self, *words: str) -> None:
        if not self.accept(*words):
            raise Refused(f"expected {' '.join(words)} near {self.peek() or 'end of statement'}; outside the verified subset")

    def done(self) -> None:
        if self.i < len(self.t):
            raise Refused(f"{self._why(self.peek())} is outside the verified subset ({SUBSET_VERSION})")

    @staticmethod
    def _why(tok: str) -> str:
        notes = {"JOIN": "JOIN", "GROUP": "GROUP BY", "HAVING": "HAVING", "DISTINCT": "DISTINCT", "UNION": "UNION",
                 "FETCH": "FETCH FIRST", "WITH": "WITH (isolation or HOLD)", "FOR": "FOR UPDATE / FOR READ ONLY",
                 "CURRENT": "CURRENT (special register or WHERE CURRENT OF)", "LIKE": "LIKE", "IN": "IN", "BETWEEN": "BETWEEN",
                 "EXISTS": "a subselect", "SELECT": "a subselect", "CASE": "CASE", "COALESCE": "COALESCE",
                 "VALUE": "VALUE", "OPTIMIZE": "OPTIMIZE FOR", "SKIP": "SKIP LOCKED DATA", "LOCK": "LOCK TABLE"}
        return notes.get(tok, f"'{tok}'")

    def table(self) -> Table:
        name = self.take()
        if self.peek() == ".":
            raise Refused(f"schema-qualified table name {name}.{self.peek(1)}; use an unqualified name")
        t = self.ctx.tables.get(name)
        if t is None:
            raise Refused(f"table {name} has no DECLARE TABLE, DCLGEN copybook or CREATE TABLE in a *.sql file of the "
                          "repository; the schema is never guessed")
        return t

    def column(self, table: Table) -> Col:
        name = self.take()
        if self.peek() == "." or self.peek() == "(":
            raise Refused(f"{self._why(name)} is outside the verified subset ({SUBSET_VERSION})")
        return table.col(name)

    # host variable with optional indicator -> Bind typed by the column it meets
    def host(self, direction: str, col: Col) -> Bind:
        token = self.take()
        name = token[1:]
        indicator = None
        if self.peek() == "INDICATOR" and self.peek(1).startswith(":"):
            self.take()
            indicator = self.take()[1:]
        elif self.peek().startswith(":"):
            indicator = self.take()[1:]
        d = self.ctx.hosts.get(name)
        if d is None:
            raise Refused(f"host variable {name} is not defined in the program or its copybooks")
        for ref in (name, indicator):
            if ref and self.ctx.hosts.get(ref) is None:
                raise Refused(f"host variable {ref} is not defined in the program or its copybooks")
        if indicator and self.ctx.hosts[indicator][0] != "N":
            raise Refused(f"null indicator {indicator} must be a numeric item")
        if d[0] == "group":
            raise Refused(f"host variable {name} is a group item; use elementary items")
        if d[0] == "other":
            raise Refused(d[1])
        if col.is_text:
            if d[0] != "X":
                raise Refused(f"host variable {name} is numeric but meets character column {col.name}")
            return Bind(name, indicator, "X", d[1], 0, direction)
        if d[0] != "N":
            raise Refused(f"host variable {name} is alphanumeric but meets numeric column {col.name}")
        scale = col.scale if col.type == "DECIMAL" else 0
        if d[1] + d[2] > WORK_DIGITS:
            raise Refused(f"host variable {name} has more than {WORK_DIGITS} digits")
        return Bind(name, indicator, "N", WORK_DIGITS - scale, scale, direction)

    def literal(self, col: Col) -> str:
        neg = self.accept("-")
        tok = self.take()
        if tok.startswith("'"):
            if neg or not col.is_text:
                raise Refused(f"string literal meets non-character column {col.name}")
            if len(tok) > 2 and tok[-2] == " ":
                raise Refused(f"literal {tok} ends with a blank; CHAR comparison semantics are not modelled for that")
            return tok
        if not re.fullmatch(r"[0-9]+(?:\.[0-9]+)?", tok) or col.is_text:
            raise Refused(f"{self._why(tok)} is outside the verified subset ({SUBSET_VERSION})")
        whole, _, frac = tok.partition(".")
        scale = col.scale if col.type == "DECIMAL" else 0
        if len(frac) > scale:
            raise Refused(f"numeric literal {tok} has more decimals than column {col.name} (scale {scale})")
        value = int(whole + frac.ljust(scale, "0"))
        return str(-value if neg else value)

    def operand(self, col: Col, direction: str, binds: list[Bind]) -> str:
        if self.peek().startswith(":"):
            binds.append(self.host(direction, col))
            return "?"
        return self.literal(col)

    def cond(self, table: Table, binds: list[Bind]) -> str:
        parts = [self.cond_term(table, binds)]
        while self.peek() in ("AND", "OR"):
            parts.append(self.take())
            parts.append(self.cond_term(table, binds))
        return " ".join(parts)

    def cond_term(self, table: Table, binds: list[Bind]) -> str:
        if self.accept("("):
            inner = self.cond(table, binds)
            self.expect(")")
            return f"({inner})"
        if self.peek() == "NOT":
            raise Refused("NOT in a WHERE clause is outside the verified subset; use <>")
        col = self.column(table)
        if self.accept("IS"):
            neg = self.accept("NOT")
            self.expect("NULL")
            return f"{col.name} IS {'NOT ' if neg else ''}NULL"
        op = self.take()
        if op not in ("=", "<>", "<", ">", "<=", ">="):
            raise Refused(f"{self._why(op)} is outside the verified subset ({SUBSET_VERSION})")
        return f"{col.name} {op} {self.operand(col, 'I', binds)}"

    def order_by(self, table: Table) -> str:
        if not self.accept("ORDER", "BY"):
            return ""
        items = []
        while True:
            col = self.column(table)
            direction = self.take() if self.peek() in ("ASC", "DESC") else ""
            items.append(f"{col.name} {direction}".strip())
            if not self.accept(","):
                break
        return " ORDER BY " + ", ".join(items)

    def select_list(self, table: Table) -> tuple[list[str], list[Col]]:
        exprs, cols = [], []
        while True:
            if self.peek() in ("COUNT", "SUM", "MIN", "MAX") and self.peek(1) == "(":
                fn = self.take()
                self.take()
                if fn == "COUNT":
                    self.expect("*")
                    cols.append(Col("COUNT", "INTEGER", precision=10, nullable=False))
                    exprs.append("COUNT(*)")
                else:
                    c = self.column(table)
                    if fn == "SUM" and c.is_text:
                        raise Refused("SUM of a character column")
                    cols.append(Col(f"{fn}_{c.name}", c.type, c.length, c.precision, c.scale, True))
                    exprs.append(f"{fn}({c.name})")
                self.expect(")")
            elif self.peek() == "*":
                raise Refused("SELECT * is outside the verified subset; name the columns")
            else:
                c = self.column(table)
                cols.append(c)
                exprs.append(c.name)
            if not self.accept(","):
                return exprs, cols

    def into(self, cols: list[Col]) -> list[Bind]:
        binds = []
        for k, col in enumerate(cols):
            if not self.peek().startswith(":"):
                raise Refused("INTO needs one host variable per selected column")
            binds.append(self.host("O", col))
            if k < len(cols) - 1:
                self.expect(",")
        return binds


def _parse_select(p: _P, stmt: Stmt, *, into: bool, cursor: bool) -> None:
    p.expect("SELECT")
    # the select list comes before the table, so find FROM first to type the columns
    depth, j = 0, p.i
    while j < len(p.t) and not (p.t[j] == "FROM" and depth == 0):
        depth += (p.t[j] == "(") - (p.t[j] == ")")
        j += 1
    if j >= len(p.t):
        raise Refused("SELECT without FROM is outside the verified subset")
    save = p.i
    p.i = j + 1
    table = p.table()
    p.i = save
    exprs, cols = p.select_list(table)
    stmt.out_cols = cols
    if into:
        p.expect("INTO")
        stmt.outputs = p.into(cols)
    p.expect("FROM")
    p.table()
    where = ""
    if p.accept("WHERE"):
        where = " WHERE " + p.cond(table, stmt.inputs)
    order = p.order_by(table)
    if cursor and not order:
        raise Refused("cursor SELECT without ORDER BY: the row order is not defined, so the two sides could differ")
    if cursor and any(e.endswith(")") for e in exprs):
        raise Refused("aggregates in a cursor are outside the verified subset")
    stmt.tables = [table.name]
    stmt.sql = f"SELECT {', '.join(exprs)} FROM {table.name}{where}{order}"


def parse_statement(text: str, line: int, ctx: _Ctx) -> Stmt:
    """Classify one EXEC SQL statement; stmt.reason is the exact refusal when it is outside the subset."""
    tokens = tokenize(text)
    stmt = Stmt("other", line)
    try:
        if not tokens:
            raise Refused("empty EXEC SQL")
        p = _P(tokens, ctx)
        head = p.peek()
        if head == "INCLUDE":
            p.take()
            name = p.take()
            stmt.kind = "include"
            if name != "SQLCA":
                raise Refused(f"INCLUDE {name}: copybook not found in the repository")
            p.done()
        elif head == "DECLARE" and p.peek(2) == "TABLE":
            stmt.kind = "declare-table"
            t = _table_from_tokens([tokens[1]] + tokens[3:], "declare", None, f"line {line}") if tokens[2] != "." else None
            if t is None:
                raise Refused("schema-qualified table name; use an unqualified name")
            ctx.tables.setdefault(t.name, t)
            stmt.tables = [t.name]
        elif head == "DECLARE" and p.peek(2) == "CURSOR":
            p.take()
            name = p.take()
            p.take()
            stmt.kind, stmt.cursor = "declare-cursor", name
            if p.peek() == "WITH":
                raise Refused("cursor WITH HOLD is outside the verified subset (COMMIT closes every cursor)")
            p.expect("FOR")
            if p.peek() != "SELECT":
                raise Refused("DECLARE CURSOR FOR a statement name (dynamic SQL) is outside the verified subset")
            _parse_select(p, stmt, into=False, cursor=True)
            p.done()
            ctx.cursors[name] = stmt
        elif head == "SELECT":
            stmt.kind = "select-into"
            _parse_select(p, stmt, into=True, cursor=False)
            p.done()
        elif head == "INSERT":
            p.take()
            p.expect("INTO")
            table = p.table()
            stmt.kind, stmt.tables = "insert", [table.name]
            cols = list(table.columns)
            if p.accept("("):
                cols = []
                while True:
                    cols.append(p.column(table))
                    if not p.accept(","):
                        break
                p.expect(")")
            if p.peek() == "SELECT":
                raise Refused("INSERT ... SELECT is outside the verified subset")
            if {c.name for c in cols} != {c.name for c in table.columns} or len(cols) != len(table.columns):
                raise Refused(f"INSERT INTO {table.name} must supply every column (defaults are not modelled)")
            p.expect("VALUES")
            p.expect("(")
            values = []
            for k, col in enumerate(cols):
                if p.accept("NULL"):
                    values.append("NULL")
                else:
                    values.append(p.operand(col, "I", stmt.inputs))
                if k < len(cols) - 1:
                    p.expect(",")
            p.expect(")")
            if p.peek() == ",":
                raise Refused("multi-row INSERT is outside the verified subset")
            p.done()
            stmt.sql = f"INSERT INTO {table.name} ({', '.join(c.name for c in cols)}) VALUES ({', '.join(values)})"
        elif head == "UPDATE":
            p.take()
            table = p.table()
            stmt.kind, stmt.tables = "update", [table.name]
            p.expect("SET")
            sets = []
            while True:
                col = p.column(table)
                p.expect("=")
                if p.accept("NULL"):
                    sets.append(f"{col.name} = NULL")
                elif p.peek() == col.name and p.peek(1) in ("+", "-") and not col.is_text:
                    p.take()
                    op = p.take()
                    sets.append(f"{col.name} = {col.name} {op} {p.operand(col, 'I', stmt.inputs)}")
                else:
                    sets.append(f"{col.name} = {p.operand(col, 'I', stmt.inputs)}")
                if not p.accept(","):
                    break
            where = " WHERE " + p.cond(table, stmt.inputs) if p.accept("WHERE") else ""
            p.done()
            stmt.sql = f"UPDATE {table.name} SET {', '.join(sets)}{where}"
        elif head == "DELETE":
            p.take()
            p.expect("FROM")
            table = p.table()
            stmt.kind, stmt.tables = "delete", [table.name]
            where = " WHERE " + p.cond(table, stmt.inputs) if p.accept("WHERE") else ""
            p.done()
            stmt.sql = f"DELETE FROM {table.name}{where}"
        elif head in ("OPEN", "CLOSE", "FETCH"):
            p.take()
            stmt.kind = head.lower()
            if head == "FETCH" and p.peek() in ("FIRST", "NEXT", "PRIOR", "LAST", "ABSOLUTE", "RELATIVE", "ROWSET"):
                raise Refused("FETCH with a position keyword (multi-row or scrollable) is outside the verified subset")
            name = p.take()
            decl = ctx.cursors.get(name)
            if decl is None:
                raise Refused(f"cursor {name} is not declared before use")
            stmt.cursor, stmt.tables = name, list(decl.tables)
            if head == "OPEN":
                stmt.sql, stmt.inputs = decl.sql, [Bind(b.host, b.indicator, b.kind, b.length, b.scale, "I") for b in decl.inputs]
                if p.peek() == "USING":
                    raise Refused("OPEN ... USING (dynamic SQL) is outside the verified subset")
            elif head == "FETCH":
                p.expect("INTO")
                stmt.out_cols = decl.out_cols
                stmt.outputs = p.into(decl.out_cols)
            p.done()
        elif head in ("COMMIT", "ROLLBACK"):
            p.take()
            stmt.kind = head.lower()
            p.accept("WORK")
            if p.peek() == "TO":
                raise Refused("ROLLBACK TO SAVEPOINT is outside the verified subset")
            p.done()
        elif head == "WHENEVER":
            p.take()
            stmt.kind = "other"
            if not tokens[-1] == "CONTINUE":
                raise Refused("WHENEVER with an action other than CONTINUE (GO TO / PERFORM) is outside the verified subset")
        elif head in ("PREPARE", "EXECUTE", "DESCRIBE"):
            raise Refused(f"dynamic SQL ({head}) is outside the verified subset: the statement is only known at run time")
        elif head == "CALL":
            raise Refused("CALL of a stored procedure is outside the verified subset")
        elif head in ("SET", "VALUES", "GET", "LOCK", "CONNECT", "RELEASE", "SAVEPOINT", "ALLOCATE", "ASSOCIATE", "GRANT", "CREATE", "DROP", "ALTER", "MERGE", "TRUNCATE"):
            raise Refused(f"{head} is DB2-specific or DDL and is outside the verified subset ({SUBSET_VERSION})")
        else:
            raise Refused(f"EXEC SQL {head} is outside the verified subset ({SUBSET_VERSION})")
        if len({b.host for b in stmt.inputs + stmt.outputs}) > MAX_HOSTS:
            raise Refused(f"more than {MAX_HOSTS} host variables in one statement")
    except Refused as e:
        stmt.reason = f"line {line}: {e}"
    except (IndexError, ValueError):
        stmt.reason = f"line {line}: statement not understood; outside the verified subset"
    return stmt


@dataclass
class SqlFacts:
    tables: list[Table]
    statements: list[Stmt]
    cursors: list[str]
    hosts: list[str]
    refusal: str | None
    includes: list[str] = field(default_factory=list)  # copybook members pulled in by EXEC SQL INCLUDE

    def as_dict(self) -> dict:
        return {"tables": [t.as_dict() for t in self.tables], "statements": [s.as_dict() for s in self.statements],
                "cursors": self.cursors, "hostVariables": self.hosts, "refusal": self.refusal}


def analyze_sql(text: str, copybooks: dict[str, tuple[str, str]], ddl_tables: list[Table]) -> SqlFacts | None:
    """EXEC SQL facts of one program. copybooks: member -> (text, repository path). None when there is no EXEC SQL."""
    lines = text.splitlines()
    if not any(_START.search(l[7:72]) for l in lines if len(l) > 6 and l[6] not in "*/"):
        return None
    source = {"dclgen": {}}  # table name -> path of the INCLUDEd copybook that declared it

    def lookup(name: str) -> str | None:
        item = copybooks.get(name)
        if item:
            source["dclgen"][name] = item[1]
        return item[0] if item else None

    expanded = expand_includes(text, lookup)
    # host variables may also live in COPY members
    full = expand_copies(expanded, {k: v[0] for k, v in copybooks.items()})
    hosts = host_defs(full)
    ctx = _Ctx({t.name: t for t in ddl_tables}, hosts)
    stmts, used_hosts, dclgen_names = [], [], set(source["dclgen"])
    blocks = find_blocks(expanded.splitlines())
    declared_here: dict[str, Table] = {}
    for b in blocks:  # DECLARE TABLE first, wherever it sits (a DCLGEN copybook is included before use anyway)
        if tokenize(b.text)[:1] == ["DECLARE"] and tokenize(b.text)[2:3] == ["TABLE"]:
            s = parse_statement(b.text, b.line, ctx)
            if s.tables and not s.reason:
                declared_here[s.tables[0]] = ctx.tables[s.tables[0]]
    for name, t in declared_here.items():
        t.source = "dclgen" if dclgen_names and not _in_main(text, name) else "declare"
        if t.source == "dclgen":
            t.path = next(iter(sorted(source["dclgen"].values())), None)
    for b in blocks:
        s = parse_statement(b.text, b.line, ctx)
        stmts.append(s)
        used_hosts += [x.host for x in s.inputs + s.outputs]
    refusal = next((s.reason for s in stmts if s.reason), None)
    if refusal is None and not any(s.kind == "include" for s in stmts):
        refusal = "EXEC SQL INCLUDE SQLCA is required: the program reads SQLCODE from it"
    touched = sorted({t for s in stmts for t in s.tables})
    tables = [ctx.tables[t] for t in touched if t in ctx.tables]
    if refusal is None:
        plain = " ".join(c for _, c in source_lines(expanded) if not _START.search(c))
        bad = re.search(r"\b(SQLSTATE|SQLERRM|SQLERRMC|SQLWARN\d?)\b", re.sub(r"EXEC\s+SQL.*?END-EXEC", " ", plain, flags=re.I), flags=re.I)
        if bad:
            refusal = (f"{bad.group(1)} is read by the program but the stand-in engine does not set it (only SQLCODE and "
                       "SQLERRD(3) are modelled)")
    return SqlFacts(tables, stmts, sorted(ctx.cursors), list(dict.fromkeys(used_hosts)), refusal, sorted(source["dclgen"]))


def _in_main(text: str, table: str) -> bool:
    return re.search(rf"DECLARE\s+{re.escape(table)}\s+TABLE", text.upper()) is not None


def expand_copies(text: str, members: dict[str, str]) -> str:
    """Inline `COPY member.` (no REPLACING) so host variables defined in copybooks are visible."""
    def sub(m):
        body = members.get(m.group(1))
        return body if body is not None else m.group(0)
    return re.sub(r"^.{6}.\s*COPY\s+([A-Z0-9-]+)\s*\.[ \t]*$", sub, text, flags=re.M)
