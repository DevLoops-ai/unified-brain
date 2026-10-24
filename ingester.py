#!/usr/bin/env python3
"""
alex
"""

import hashlib
import json
import math
import os
import re
import subprocess
import sys
import time

try:
    from tree_sitter_language_pack import get_parser
except ImportError:
    print("tree-sitter-language-pack not installed. "
          "Run: pip3 install tree-sitter-language-pack --break-system-packages",
          file=sys.stderr)
    sys.exit(1)

# ── Skip list ─────────────────────────────────────────────────────────────────
# ONLY dependency-manager trees and build caches. Vendored third-party source
# is the entire point of the product and must never be skipped.

SKIP_PATHS = [
    'node_modules/', '/venv/', '/.venv/', 'site-packages/',
    '__pycache__/', '.mypy_cache/', '.pytest_cache/', '.tox/',
    '.gradle/', 'bower_components/', '.terraform/',
]

# Explicitly NOT coverage-counted (still ingested whole-file).
TEXT_EXEMPT = {'.md', '.txt'}

# ── Language resolution ───────────────────────────────────────────────────────

LANG_BY_EXT = {
    '.py': 'python', '.pyi': 'python',
    '.ts': 'typescript', '.mts': 'typescript', '.cts': 'typescript',
    '.tsx': 'tsx',
    '.js': 'javascript', '.jsx': 'javascript',
    '.mjs': 'javascript', '.cjs': 'javascript',
    '.c': 'c',
    '.cc': 'cpp', '.cpp': 'cpp', '.cxx': 'cpp', '.c++': 'cpp',
    '.hpp': 'cpp', '.hh': 'cpp', '.hxx': 'cpp', '.h++': 'cpp',
    '.ipp': 'cpp', '.tpp': 'cpp', '.inl': 'cpp',
    # Ambiguous headers / include fragments — resolved by trial parse.
    '.h': '?c', '.inc': '?c',
    '.sh': 'bash', '.bash': 'bash', '.zsh': 'bash', '.ksh': 'bash',
    '.cmake': 'cmake',
    '.yml': 'yaml', '.yaml': 'yaml',
    '.am': 'automake', '.mk': 'make',
    # Regex-extracted, no grammar involved:
    '.m4': 'm4', '.ac': 'm4',
    '.s': 'asm',
}

LANG_BY_NAME = {
    'CMakeLists.txt': 'cmake',
    'configure': 'bash',
}

TIER1 = ('python', 'typescript', 'tsx', 'javascript', 'c', 'cpp')
TIER2 = ('bash', 'cmake', 'yaml', 'make')
NO_PARSE = ('m4', 'asm', 'automake')   # regex extractors, no tree-sitter

# Languages symbolized at whole-file (<module>) level ONLY. Make/Automake
# conditionals and variable blocks fragment badly under sub-file
# extraction (the b93a8d7631d9 false-FLAW incident: a conditional's
# members extracted as separate symbols, leaving a shell body). These
# files are small; sub-file granularity buys nothing.
MODULE_ONLY_LANGS = {'make', 'automake', 'm4'}
ALL_LANGS = TIER1 + TIER2

C_FAMILY = ('c', 'cpp')

# Grammars prefetched for offline bootstrap.
PREFETCH_LANGS = ALL_LANGS

COMMENT_STYLE = {
    'python': '#', 'bash': '#', 'cmake': '#', 'yaml': '#', 'make': '#',
    'm4': '#', 'asm': '#', 'text': '#',
    'c': '//', 'cpp': '//', 'typescript': '//', 'tsx': '//', 'javascript': '//',
    'automake': '#'
}

CLASS_SKELETON_THRESHOLD = 5000

# Bodies above this are stored truncated. A sha256 of the FULL body is embedded
# in the stored text so changed_symbols still diffs edits inside the elided
# region — you lose readability, never change detection.
MAX_BODY_CHARS = 240_000
TRUNC_HEAD_LINES = 10_000
TRUNC_TAIL_LINES = 3_000

# Parse-quality gate: above this ERROR ratio the file is demoted to Tier 3.
MAX_ERROR_RATIO = 0.25

BINARY_MAGIC = {
    b'\xfd7zXZ\x00':      'xz container',
    b'\x5d\x00\x00':      'lzma compressed (alone)',
    b'\x1f\x8b':          'gzip compressed',
    b'PK\x03\x04':        'zip archive',
    b'\x7fELF':           'ELF binary',
    b'\x89PNG':           'PNG image',
    b'BZh':               'bzip2 compressed',
    b'\x04\x22\x4d\x18':  'lz4 compressed',
    b'(\xb5/\xfd':        'zstd compressed',
    b'LZIP':              'lzip compressed',
    b'7z\xbc\xaf\x27\x1c': '7z archive',
}

_PARSERS = {}


def log_phase(phase, status, **extra):
    print(json.dumps({'ts': int(time.time() * 1000), 'phase': phase,
                      'status': status, **extra}), file=sys.stderr)


def _parser(lang):
    if lang not in _PARSERS:
        _PARSERS[lang] = get_parser(lang)
    return _PARSERS[lang]


def _text(node, src):
    return src[node.start_byte:node.end_byte].decode('utf-8', 'replace')


def _line(node):
    return node.start_point[0] + 1


def _end_line(node):
    # Nodes that consume their trailing newline (tree-sitter preproc
    # directives) end at col 0 of the NEXT line; counting that line into
    # the span swallowed following #elif/#else/#endif lines from <module>.
    row, col = node.end_point
    if col == 0 and row > node.start_point[0]:
        return row
    return row + 1


def _walk(node):
    stack = [node]
    while stack:
        n = stack.pop()
        yield n
        stack.extend(n.children)


def _error_ratio(tree):
    total = errors = 0
    for n in _walk(tree.root_node):
        total += 1
        if n.type == 'ERROR' or n.is_missing:
            errors += 1
    return (errors / total) if total else 1.0


def _truncate_body(code, lang):
    """Elide the middle of an oversized body, embedding a sha256 of the full
    text. Generated tables (crc64_table_le.h and friends) are tens of thousands
    of lines; storing them whole poisons the FT body index and the LLM context.
    The hash keeps them change-detectable."""
    if len(code) <= MAX_BODY_CHARS:
        return code
    digest = hashlib.sha256(code.encode('utf-8', 'replace')).hexdigest()
    lines = code.splitlines()
    if len(lines) <= TRUNC_HEAD_LINES + TRUNC_TAIL_LINES:
        head, tail, elided = lines, [], 0
    else:
        head = lines[:TRUNC_HEAD_LINES]
        tail = lines[-TRUNC_TAIL_LINES:]
        elided = len(lines) - TRUNC_HEAD_LINES - TRUNC_TAIL_LINES
    c = COMMENT_STYLE.get(lang, '#')
    marker = (f'{c} … {elided} lines elided by DevLoops ingester '
              f'(full body sha256: {digest}) …')
    return '\n'.join(head + [marker] + tail)


def _norm_name(name):
    """Canonical symbol name. Colons are structural in def_keys
    (`path:symbol:line:type`, parsed with rsplit(':', 3)), so a C++
    qualified name must never carry them: lzma::Coder::run -> lzma.Coder.run.
    Template arguments are stripped so specialisations don't inject commas
    into the RediSearch TAG field; file+line still disambiguate them."""
    name = name.strip()
    if 'operator' not in name:
        name = _strip_template_args(name)
    name = name.replace('::', '.')
    return name.replace(':', '.')          # final guard


def _strip_template_args(s):
    out, depth = [], 0
    for ch in s:
        if ch == '<':
            depth += 1
        elif ch == '>':
            depth = max(0, depth - 1)
        elif depth == 0:
            out.append(ch)
    return ''.join(out)


# ── Python extraction ─────────────────────────────────────────────────────────
# Parity with python_extractor.py: structureType values 'FunctionDef',
# 'AsyncFunctionDef', 'ClassDef', 'constant', 'variable'; line = `def`/`class`
# line (decorators excluded from code); class methods one level deep;
# top-level assignments; class skeleton for classes > 5000 chars.

def _py_is_async(fn_node):
    return any(c.type == 'async' for c in fn_node.children)


def _py_unwrap(node):
    """decorated_definition -> inner function/class definition."""
    if node.type == 'decorated_definition':
        for c in node.children:
            if c.type in ('function_definition', 'class_definition'):
                return c
    return node


def _py_assign_names(node):
    """assignment node -> target nodes with a value. Covers:
    simple (`x = 1`), annotated (`x: int = 1`), tuple/list targets
    (`a, b = ...`, incl. `*rest`), chained (`x = y = 1`), and attribute
    targets (`cfg.DEBUG = True` — emitted under the full dotted name).
    Bare annotations (`x: int`) and subscript targets (`d['k'] = ...`)
    are deliberately skipped."""
    left = node.child_by_field_name('left')
    right = node.child_by_field_name('right')
    if left is None or right is None:
        return []
    names = []

    def collect(t):
        if t.type in ('identifier', 'attribute'):
            names.append(t)
        elif t.type in ('pattern_list', 'tuple_pattern', 'list_pattern',
                        'list_splat_pattern'):
            for c in t.children:
                collect(c)

    collect(left)
    # chained: `x = y = 1` parses as assignment(right=assignment(...))
    if right.type == 'assignment':
        names.extend(_py_assign_names(right))
    return names


def _py_extract_class_skeleton(node, lines, wrapper):
    """Class signature + decorators, docstring, __init__ full, other method
    signatures only, class-level assignments. Mirrors old _extract_class_skeleton."""
    out = []
    start = _line(wrapper)              # includes decorators if present
    for ln in range(start, _line(node) + 1):
        out.append(lines[ln - 1])

    body = node.child_by_field_name('body')
    if body is None:
        return '\n'.join(out)

    for item in body.children:
        inner = _py_unwrap(item)
        if inner.type == 'function_definition':
            name_node = inner.child_by_field_name('name')
            name = name_node.text.decode() if name_node is not None else ''
            if name == '__init__':
                for ln in range(_line(inner), _end_line(inner) + 1):
                    out.append(lines[ln - 1])
            else:
                if item.type == 'decorated_definition':
                    for c in item.children:
                        if c.type == 'decorator':
                            out.append(lines[_line(c) - 1])
                out.append(lines[_line(inner) - 1])
                out.append('        ...')
        elif item.type == 'expression_statement':
            # docstring OR class attribute — the old catch-all swallowed
            # expression_statement first, making the assignment branch dead.
            child = item.children[0] if item.children else None
            if child is not None and child.type in ('string', 'assignment'):
                for ln in range(_line(item), _end_line(item) + 1):
                    out.append(lines[ln - 1])
        elif item.type in ('string', 'assignment'):
            for ln in range(_line(item), _end_line(item) + 1):
                out.append(lines[ln - 1])

    return '\n'.join(out)


def _py_symbols(src, source_text, lines, tree):
    symbols = []

    def def_symbol(node, wrapper):
        """node: function/class definition (decorators excluded — ast parity)."""
        name_node = node.child_by_field_name('name')
        if name_node is None:
            return None
        if node.type == 'class_definition':
            struct = 'ClassDef'
        else:
            struct = 'AsyncFunctionDef' if _py_is_async(node) else 'FunctionDef'
        code = _text(node, src)
        if struct == 'ClassDef' and len(code) > CLASS_SKELETON_THRESHOLD:
            code = _py_extract_class_skeleton(node, lines, wrapper)
        return {'name': name_node.text.decode(), 'line': _line(node),
                'structureType': struct, 'code': code, '_end': _end_line(node)}

    def assign_symbol(node):
        out = []
        for name_node in _py_assign_names(node):
            name = name_node.text.decode()
            leaf = name.rsplit('.', 1)[-1]
            out.append({
                'name': name, 'line': _line(node),
                'structureType': 'constant' if leaf.isupper() else 'variable',
                'code': _text(node, src), '_end': _end_line(node),
            })
        return out

    for top in tree.root_node.children:
        inner = _py_unwrap(top)
        t = inner.type
        if t == 'function_definition':
            s = def_symbol(inner, top)
            if s:
                symbols.append(s)
        elif t == 'class_definition':
            s = def_symbol(inner, top)
            if s:
                symbols.append(s)
            body = inner.child_by_field_name('body')
            if body is not None:
                for item in body.children:
                    m = _py_unwrap(item)
                    if m.type == 'function_definition':
                        ms = def_symbol(m, item)
                        if ms:
                            symbols.append(ms)
                    elif m.type == 'assignment':
                        symbols.extend(assign_symbol(m))
                    elif m.type == 'expression_statement':
                        for c in m.children:
                            if c.type == 'assignment':
                                symbols.extend(assign_symbol(c))
        elif t == 'assignment':
            symbols.extend(assign_symbol(inner))
        elif t == 'expression_statement':
            for c in inner.children:
                if c.type == 'assignment':
                    symbols.extend(assign_symbol(c))

    return symbols


# ── TS / JS extraction ────────────────────────────────────────────────────────
# structureType: 'function' | 'class' | 'method' | 'interface' | 'type' |
# 'enum' | 'component' | 'constant' | 'variable'.
# line = inner declaration line; code includes the export wrapper.

_TS_FN_VALUES = {'arrow_function', 'function_expression', 'function',
                 'generator_function'}


def _ts_symbols(src, lang, lines, tree):
    symbols = []
    jsx_capable = lang in ('tsx', 'javascript')

    def add(name, node, struct, code_node=None):
        symbols.append({'name': name, 'line': _line(node),
                        'structureType': struct,
                        'code': _text(code_node or node, src),
                        '_end': _end_line(node)})

    def class_methods(class_node):
        body = class_node.child_by_field_name('body')
        if body is None:
            return
        for item in body.children:
            if item.type == 'method_definition':
                name_node = item.child_by_field_name('name')
                if name_node is not None:
                    add(name_node.text.decode(), item, 'method')

    def handle_decl(decl, wrapper):
        t = decl.type
        name_node = decl.child_by_field_name('name')
        if t in ('function_declaration', 'generator_function_declaration'):
            if name_node is not None:
                add(name_node.text.decode(), decl, 'function', wrapper)
        elif t in ('class_declaration', 'abstract_class_declaration'):
            if name_node is not None:
                add(name_node.text.decode(), decl, 'class', wrapper)
            class_methods(decl)
        elif t == 'interface_declaration':
            if name_node is not None:
                add(name_node.text.decode(), decl, 'interface', wrapper)
        elif t == 'type_alias_declaration':
            if name_node is not None:
                add(name_node.text.decode(), decl, 'type', wrapper)
        elif t == 'enum_declaration':
            if name_node is not None:
                add(name_node.text.decode(), decl, 'enum', wrapper)
        elif t in ('lexical_declaration', 'variable_declaration'):
            for c in decl.children:
                if c.type != 'variable_declarator':
                    continue
                n = c.child_by_field_name('name')
                v = c.child_by_field_name('value')
                if n is None:
                    continue
                if n.type == 'identifier':
                    name = n.text.decode()
                    if v is not None and v.type in _TS_FN_VALUES:
                        struct = 'component' if jsx_capable and name[:1].isupper() \
                            else 'function'
                    else:
                        struct = 'constant' if name.isupper() else 'variable'
                    add(name, c, struct, wrapper)
                elif n.type in ('object_pattern', 'array_pattern'):
                    idents = []
                    _ts_pattern_identifiers(n, idents)
                    for id_node in idents:
                        name = id_node.text.decode()
                        struct = 'constant' if name.isupper() else 'variable'
                        add(name, c, struct, wrapper)

    def _ts_pattern_identifiers(pat, acc):
        """object/array pattern -> identifier nodes bound by it."""
        t = pat.type
        if t in ('identifier', 'shorthand_property_identifier_pattern'):
            acc.append(pat)
        elif t == 'pair_pattern':                 # { key: alias }
            v = pat.child_by_field_name('value')
            if v is not None:
                _ts_pattern_identifiers(v, acc)
        elif t == 'assignment_pattern':           # { a = default }
            l = pat.child_by_field_name('left')
            if l is not None:
                _ts_pattern_identifiers(l, acc)
        elif t in ('object_pattern', 'array_pattern', 'rest_pattern'):
            for c in pat.children:
                _ts_pattern_identifiers(c, acc)

    for top in tree.root_node.children:
        if top.type == 'export_statement':
            for c in top.children:
                if c.type not in ('export', 'default', ';'):
                    handle_decl(c, top)
        else:
            handle_decl(top, top)

    return symbols


# ── C / C++ extraction ────────────────────────────────────────────────────────
# structureType: 'function' | 'prototype' | 'method' | 'macro' | 'struct' |
# 'union' | 'enum' | 'typedef' | 'class' | 'namespace' | 'field' | 'variable' |
# 'constant'.
#
# Design notes that matter for supply-chain review:
#
# * Preprocessor conditionals are FLATTENED, not evaluated. tree-sitter parses
#   every #ifdef branch, so code that never compiles on this host is still
#   extracted. A compiler-based tool sees one branch; this sees all of them.
# * Prototypes are emitted separately from definitions. A silently altered
#   signature in a header is a semantic event and must diff.
# * Struct/class data members are emitted as symbols ONLY when they are
#   function pointers. Those are dispatch surfaces. Plain scalar fields stay inside the parent's body text instead of
#   flooding the skill graph with `uint32_t crc;`.
# * __attribute__((constructor)) / ((ifunc(...))) / ((alias(...))) are captured
#   on the symbol, because "runs at dlopen" and "resolves indirectly at load
#   time" are exactly the properties an auditor needs surfaced.

_C_DECLARATOR_WRAPPERS = {
    'function_declarator', 'pointer_declarator', 'array_declarator',
    'parenthesized_declarator', 'reference_declarator', 'init_declarator',
    'attributed_declarator',
}
_C_NAME_NODES = {
    'identifier', 'field_identifier', 'type_identifier',
    'qualified_identifier', 'operator_name', 'destructor_name',
}
# Preprocessor containers whose children are themselves top-level constructs.
_C_PREPROC_CONTAINERS = {
    'preproc_ifdef', 'preproc_if', 'preproc_else', 'preproc_elif',
    'preproc_elifdef', 'linkage_specification', 'declaration_list',
}
_C_ATTR_STRING_KINDS = {
    'ifunc': 'ifunc', '__ifunc__': 'ifunc',
    'alias': 'alias', '__alias__': 'alias',
    'section': 'section', '__section__': 'section',
}
_C_ATTR_FLAGS = {
    'constructor', '__constructor__', 'destructor', '__destructor__',
    'used', '__used__', 'weak', '__weak__', 'visibility', '__visibility__',
}

_C_KEYWORDS = {'void', 'int', 'char', 'long', 'short', 'float', 'double',
               'signed', 'unsigned', 'bool', 'const', 'auto', 'register'}


def _c_declarator_name(node):
    """Descend a declarator chain to the declared name node."""
    seen = 0
    cur = node
    while cur is not None and seen < 24:
        seen += 1
        if cur.type in _C_NAME_NODES:
            return cur
        nxt = cur.child_by_field_name('declarator')
        if nxt is None:
            nxt = cur.child_by_field_name('name')
        if nxt is None and cur.type in _C_DECLARATOR_WRAPPERS:
            # parenthesized_declarator has no named field: `void (*fn)(int)`
            for c in cur.children:
                if c.type in _C_NAME_NODES or c.type in _C_DECLARATOR_WRAPPERS:
                    nxt = c
                    break
        if nxt is None:
            return None
        cur = nxt
    return None


def _c_is_function_declarator(node):
    """True when the declarator chain contains a function_declarator that is
    NOT merely a function-pointer wrapper."""
    cur = node
    seen = 0
    while cur is not None and seen < 24:
        seen += 1
        if cur.type == 'function_declarator':
            return True
        nxt = cur.child_by_field_name('declarator')
        if nxt is None and cur.type in _C_DECLARATOR_WRAPPERS:
            for c in cur.children:
                if c.type in _C_DECLARATOR_WRAPPERS or c.type in _C_NAME_NODES:
                    nxt = c
                    break
        cur = nxt
    return False


def _c_is_function_pointer(node):
    """`void (*fn)(int)` — a parenthesized pointer declarator inside a
    function declarator. These are indirect-dispatch surfaces."""
    for n in _walk(node):
        if n.type == 'parenthesized_declarator':
            for c in _walk(n):
                if c.type == 'pointer_declarator':
                    return True
    return False


def _c_attributes(node, src):
    """-> (flags, refs) from any __attribute__/[[…]] on this node.
    refs are (kind, target) where target came from a string argument."""
    flags, refs = [], []
    for n in _walk(node):
        if n.type not in ('attribute_specifier', 'attribute_declaration',
                          'attribute'):
            continue
        for c in _walk(n):
            if c.type == 'identifier':
                ident = c.text.decode()
                if ident in _C_ATTR_FLAGS:
                    flags.append(ident.strip('_'))
            if c.type == 'call_expression':
                fn = c.child_by_field_name('function')
                if fn is None or fn.type != 'identifier':
                    continue
                kind = _C_ATTR_STRING_KINDS.get(fn.text.decode())
                if kind is None:
                    continue
                for s in _walk(c):
                    if s.type == 'string_content':
                        refs.append((kind, s.text.decode()))
                        break
    return sorted(set(flags)), refs


_C_PREPROC_BRANCHES = {'preproc_ifdef', 'preproc_if', 'preproc_elif',
                       'preproc_elifdef', 'preproc_else'}


def _c_guard_head(n, src):
    """'#if <cond>' / '#ifdef NAME' / '#else' for one preprocessor branch node."""
    tok = n.children[0] if n.children else None
    head = _text(tok, src).strip() if tok is not None else n.type
    cond = n.child_by_field_name('condition') or n.child_by_field_name('name')
    if cond is not None:
        head += ' ' + ' '.join(_text(cond, src).split())
    return head


def _c_toplevel(root, src=None):
    """Yield (node, guard) for top-level constructs, descending through
    preprocessor conditionals and `extern "C"` blocks so nothing hides in
    a branch. guard is the tuple of enclosing preprocessor branch heads,
    outermost first — e.g. ('#if defined(__GNUC__)', '#else')."""
    stack = [(c, ()) for c in reversed(root.children)]
    while stack:
        n, guard = stack.pop()
        if n.type in _C_PREPROC_CONTAINERS:
            g = guard
            if n.type in _C_PREPROC_BRANCHES and src is not None:
                g = guard + (_c_guard_head(n, src),)
            stack.extend((c, g) for c in reversed(n.children))
            continue
        yield n, guard


def _c_symbols(src, lang, lines, tree):
    symbols = []
    cur_guard = [()]          # enclosing preprocessor branches of the node being handled
    c = COMMENT_STYLE.get(lang, '//')

    def add(name, node, struct, code_node=None, prefix='', extra=None):
        if not name:
            return None
        full = _norm_name(f'{prefix}.{name}' if prefix else name)
        if not full:
            return None
        code = _text(code_node or node, src)
        if cur_guard[0]:
            # A #if/#elif/#else variant stored alone is ambiguous — six
            # `#define X` bodies are byte-identical without their guards.
            code = (f'{c} [preproc context: {" → ".join(cur_guard[0])}]\n'
                    + code)
        flags, attr_refs = _c_attributes(code_node or node, src)
        sym = {
            'name': full,
            'line': _line(node),
            'structureType': struct,
            'code': _truncate_body(code, lang),
            '_end': _end_line(code_node or node),
        }
        if flags:
            sym['attrs'] = flags
        if attr_refs:
            sym['_attr_refs'] = attr_refs
        if extra:
            sym.update(extra)
        symbols.append(sym)
        return sym

    def unwrap_template(node):
        """template_declaration -> the declaration it parameterises."""
        while node is not None and node.type == 'template_declaration':
            inner = None
            for c in node.children:
                if c.type in ('function_definition', 'class_specifier',
                              'struct_specifier', 'declaration',
                              'alias_declaration', 'union_specifier'):
                    inner = c
                    break
            if inner is None:
                return node
            node = inner
        return node

    def record_class_body(body, prefix, lang_):
        """Methods always; data members only when they are function pointers."""
        if body is None:
            return
        for item in body.children:
            t = item.type
            inner = unwrap_template(item)
            t = inner.type
            if t == 'function_definition':
                d = inner.child_by_field_name('declarator')
                nm = _c_declarator_name(d) if d is not None else None
                if nm is not None:
                    add(_text(nm, src), inner, 'method', prefix=prefix)
            elif t in ('field_declaration', 'declaration'):
                d = inner.child_by_field_name('declarator')
                if d is None:
                    # `struct { … } anon;` or a bare nested specifier
                    handle_type_specifier(inner, prefix)
                    continue
                nm = _c_declarator_name(d)
                if nm is None:
                    continue
                nm_text = _text(nm, src)
                if _c_is_function_pointer(d):
                    add(nm_text, inner, 'field', prefix=prefix,
                        extra={'_fnptr': True})
                elif _c_is_function_declarator(d):
                    add(nm_text, inner, 'method', prefix=prefix)
                # plain data members: intentionally not emitted
            elif t in ('class_specifier', 'struct_specifier', 'union_specifier',
                       'enum_specifier'):
                handle_type_specifier(inner, prefix)

    def handle_type_specifier(node, prefix=''):
        t = node.type
        kind = {'class_specifier': 'class', 'struct_specifier': 'struct',
                'union_specifier': 'union', 'enum_specifier': 'enum'}.get(t)
        if kind is None:
            return
        name_node = node.child_by_field_name('name')
        body = node.child_by_field_name('body')
        if name_node is None:
            return
        name = _text(name_node, src)
        add(name, node, kind, prefix=prefix)
        if body is not None and kind in ('class', 'struct', 'union'):
            record_class_body(body, _norm_name(f'{prefix}.{name}' if prefix
                                               else name), lang)

    def handle(node, prefix=''):
        node = unwrap_template(node)
        t = node.type

        if t == 'namespace_definition':
            name_node = node.child_by_field_name('name')
            nm = _text(name_node, src) if name_node is not None else '(anonymous)'
            add(nm, node, 'namespace', prefix=prefix)
            body = node.child_by_field_name('body')
            new_prefix = _norm_name(f'{prefix}.{nm}' if prefix else nm)
            if body is not None:
                outer = cur_guard[0]
                for c_node, g in _c_toplevel(body, src):
                    cur_guard[0] = outer + g
                    handle(c_node, new_prefix)
                cur_guard[0] = outer
            return

        if t == 'function_definition':
            d = node.child_by_field_name('declarator')
            nm = _c_declarator_name(d) if d is not None else None
            name = _text(nm, src) if nm is not None else None
            if name is None or name in _C_KEYWORDS:
                # Macro-displaced pattern: a bare attribute macro above the
                # return type pushes the function name into the `type` slot
                # and the declarator degenerates to `(void)`.
                ty = node.child_by_field_name('type')
                if ty is not None and ty.type == 'type_identifier':
                    name = _text(ty, src)
            if name and name not in _C_KEYWORDS:
                add(name, node, 'function', prefix=prefix)
            return

        if t in ('preproc_def', 'preproc_function_def'):
            name_node = node.child_by_field_name('name')
            if name_node is not None:
                add(_text(name_node, src), node, 'macro', prefix='')
            return

        if t == 'type_definition':
            emitted = False
            for c in node.children:
                if c.type == 'type_identifier':
                    add(_text(c, src), node, 'typedef', prefix=prefix)
                    emitted = True
            if not emitted:
                d = node.child_by_field_name('declarator')
                nm = _c_declarator_name(d) if d is not None else None
                if nm is not None:
                    add(_text(nm, src), node, 'typedef', prefix=prefix)
            # typedef struct { … } foo; — also record the inner shape
            for c in node.children:
                if c.type in ('struct_specifier', 'union_specifier',
                              'enum_specifier', 'class_specifier'):
                    body = c.child_by_field_name('body')
                    if body is not None and c.child_by_field_name('name') is None:
                        nm2 = node.child_by_field_name('declarator')
                        base = _c_declarator_name(nm2) if nm2 is not None else None
                        base_txt = _text(base, src) if base is not None else ''
                        if base_txt:
                            record_class_body(
                                body,
                                _norm_name(f'{prefix}.{base_txt}' if prefix
                                           else base_txt),
                                lang)
                    else:
                        handle_type_specifier(c, prefix)
            return

        if t == 'alias_declaration':                      # C++ `using X = Y;`
            name_node = node.child_by_field_name('name')
            if name_node is not None:
                add(_text(name_node, src), node, 'typedef', prefix=prefix)
            return

        if t in ('class_specifier', 'struct_specifier', 'union_specifier',
                 'enum_specifier'):
            handle_type_specifier(node, prefix)
            return

        if t == 'declaration':
            if any(c.is_missing for c in node.children):
                # tree-sitter error-recovery artifact: a bare attribute
                # macro (`lzma_resolver_attributes`) absorbed into a
                # synthetic declaration with an invented `;` — never
                # mint symbols from it.
                return
            declarators = [c for c in node.children
                           if c.type in _C_DECLARATOR_WRAPPERS
                           or c.type in _C_NAME_NODES]
            if not declarators:
                for c in node.children:
                    if c.type in ('struct_specifier', 'union_specifier',
                                  'enum_specifier', 'class_specifier'):
                        handle_type_specifier(c, prefix)
                return
            for d in declarators:
                nm = _c_declarator_name(d)
                if nm is None:
                    continue
                nm_text = _text(nm, src)
                if _c_is_function_pointer(d):
                    struct = 'variable'
                elif _c_is_function_declarator(d):
                    struct = 'prototype'
                else:
                    leaf = nm_text.rsplit('::', 1)[-1]
                    struct = 'constant' if leaf.isupper() else 'variable'
                add(nm_text, node, struct, prefix=prefix)
            # `struct foo { … } instance;` — record the shape too
            for c in node.children:
                if c.type in ('struct_specifier', 'union_specifier',
                              'enum_specifier', 'class_specifier'):
                    if c.child_by_field_name('body') is not None:
                        handle_type_specifier(c, prefix)
            return

    for top, g in _c_toplevel(tree.root_node, src):
        cur_guard[0] = g
        handle(top, '')
    cur_guard[0] = ()

    return symbols


# ── Bash extraction (Tier 2) ─────────────────────────────────────────────────

def _bash_symbols(src, lang, lines, tree):
    # Functions only. Assignments are NOT symbols: <module> coverage is
    # line-based, so cutting `X=...` out of the script removed the values
    # (and, for `cmd || X=1`, the command) from the body the reader sees.
    symbols = []
    for n in _walk(tree.root_node):
        if n.type == 'function_definition':
            name_node = n.child_by_field_name('name')
            if name_node is not None:
                symbols.append({
                    'name': _norm_name(_text(name_node, src)),
                    'line': _line(n), 'structureType': 'function',
                    'code': _truncate_body(_text(n, src), lang),
                    '_end': _end_line(n),
                })
    return symbols


# ── CMake extraction (Tier 2) ────────────────────────────────────────────────

def _cmake_symbols(src, lang, lines, tree):
    symbols = []
    for n in _walk(tree.root_node):
        if n.type in ('function_def', 'macro_def'):
            struct = 'function' if n.type == 'function_def' else 'macro'
            name = None
            # _walk visits nodes back to front: take the earliest in the file.
            cmds = [c for c in _walk(n)
                    if c.type in ('function_command', 'macro_command')]
            if cmds:
                cmd = min(cmds, key=lambda c: c.start_byte)
                args = [a for a in _walk(cmd)
                        if a.type in ('argument', 'unquoted_argument')]
                if args:
                    name = _text(min(args, key=lambda a: a.start_byte), src)
            if name:
                symbols.append({
                    'name': _norm_name(name), 'line': _line(n),
                    'structureType': struct,
                    'code': _truncate_body(_text(n, src), lang),
                    '_end': _end_line(n),
                })
        # set()/option() are NOT symbols. Each one was stored as a single
        # command, cut out of <module>, and so separated from the if()/else()
        # that decides it: `set(ASM_I386_DEFAULT OFF)` alone reads as "the
        # default is OFF" when it is only the else() branch. They stay in
        # <module>, in order, like shell assignments.
    return symbols


# ── Make / Automake extraction ────────────────────────────────────────────────

def _make_symbols(src, lang, lines, tree):
    symbols = []
    for n in _walk(tree.root_node):
        if n.type == 'rule':
            tgt = next((c for c in n.children if c.type == 'targets'), None)
            name = _text(tgt, src).split()[0] if tgt is not None else ''
            if name:
                symbols.append({'name': _norm_name(name), 'line': _line(n),
                                'structureType': 'function',
                                'code': _truncate_body(_text(n, src), lang),
                                '_end': _end_line(n)})
        elif n.type == 'variable_assignment':
            nm_node = n.child_by_field_name('name')
            if nm_node is not None:
                nm = _text(nm_node, src)
                symbols.append({
                    'name': _norm_name(nm), 'line': _line(n),
                    'structureType': 'constant' if nm.isupper() else 'variable',
                    'code': _truncate_body(_text(n, src), lang),
                    '_end': _end_line(n)})
    return symbols


# ── YAML extraction (CI workflows: top-level keys + per-job) ─────────────────

def _yaml_symbols(src, lang, lines, tree):
    symbols = []

    def add(name, node):
        symbols.append({'name': _norm_name(name), 'line': _line(node),
                        'structureType': 'variable',
                        'code': _truncate_body(_text(node, src), lang),
                        '_end': _end_line(node)})

    def top_mapping(node):
        cur = node
        for _ in range(4):
            if cur is None:
                return None
            if cur.type == 'block_mapping':
                return cur
            cur = next((c for c in cur.children
                        if c.type in ('block_node', 'block_mapping')), None)
        return None

    for doc in tree.root_node.children:
        m = top_mapping(doc)
        if m is None:
            continue
        for pair in m.children:
            if pair.type != 'block_mapping_pair':
                continue
            k = pair.child_by_field_name('key')
            if k is None:
                continue
            name = _text(k, src).strip().strip('"\'')
            if not name:
                continue
            add(name, pair)
            vm = top_mapping(pair.child_by_field_name('value'))
            if vm is not None:
                for sub in vm.children:
                    if sub.type != 'block_mapping_pair':
                        continue
                    sk = sub.child_by_field_name('key')
                    if sk is not None:
                        sname = _text(sk, src).strip().strip('"\'')
                        if sname:
                            add(f'{name}.{sname}', sub)
    return symbols


# ── m4 / autoconf extraction (regex, no grammar) ─────────────────────────────
# One symbol per AC_DEFUN block — build-to-host.m4-class injections diff at
# macro granularity. Files without DEFUNs (configure.ac) land in <module>.

_M4_DEFUN_RE = re.compile(r'^(?:AC|AU|AM)_DEFUN(?:_ONCE)?\(\[?([\w+-]+)\]?',
                          re.M)


def _m4_symbols(content, lines):
    symbols = []
    for m in _M4_DEFUN_RE.finditer(content):
        start = m.start()
        depth, end = 0, len(content)
        for i in range(content.index('(', start), len(content)):
            ch = content[i]
            if ch == '(':
                depth += 1
            elif ch == ')':
                depth -= 1
                if depth == 0:
                    end = i + 1
                    break
        symbols.append({
            'name': _norm_name(m.group(1)),
            'line': content.count('\n', 0, start) + 1,
            'structureType': 'macro',
            'code': _truncate_body(content[start:end], 'm4'),
            '_end': content.count('\n', 0, end) + 1,
        })
    return symbols


# ── Assembly extraction (regex, no grammar) ──────────────────────────────────
# Label-delimited: each label owns the lines up to the next label. Directives
# before the first label go to <module>.

_ASM_LABEL_RE = re.compile(r'^[ \t]*([A-Za-z_.$][\w.$]*):', re.M)


def _asm_symbols(content, lines):
    symbols = []
    matches = list(_ASM_LABEL_RE.finditer(content))
    for i, m in enumerate(matches):
        start_line = content.count('\n', 0, m.start()) + 1
        end_line = (content.count('\n', 0, matches[i + 1].start())
                    if i + 1 < len(matches) else len(lines))
        symbols.append({
            'name': _norm_name(m.group(1)), 'line': start_line,
            'structureType': 'function',
            'code': _truncate_body('\n'.join(lines[start_line - 1:end_line]),
                                   'asm'),
            '_end': end_line,
        })
    return symbols


# ── Automake extraction (regex — the make grammar mis-parses if/endif) ───────
# Repeated `VAR += …` occurrences are distinct symbols disambiguated by line,
# exactly the match_occurrences case.

_AM_ASSIGN_RE = re.compile(r'^([A-Za-z_@][\w@.+-]*)\s*[:+?]?=', re.M)
_AM_RULE_RE = re.compile(r'^([^\s:#=][^:=\n]*):(?!=)', re.M)


def _automake_symbols(content, lines):
    symbols = []

    def cont_end(start_line):
        i = start_line
        while i <= len(lines) and lines[i - 1].rstrip().endswith('\\'):
            i += 1
        return i

    seen = set()
    for m in _AM_ASSIGN_RE.finditer(content):
        line = content.count('\n', 0, m.start()) + 1
        end = cont_end(line)
        name = m.group(1)
        symbols.append({'name': _norm_name(name), 'line': line,
                        'structureType': 'constant' if name.isupper()
                        else 'variable',
                        'code': '\n'.join(lines[line - 1:end]), '_end': end})
        seen.add(line)
    for m in _AM_RULE_RE.finditer(content):
        line = content.count('\n', 0, m.start()) + 1
        if line in seen:
            continue
        end = cont_end(line)
        while end < len(lines) and (lines[end].startswith('\t')
                                    or not lines[end].strip()):
            end += 1
        symbols.append({'name': _norm_name(m.group(1).split()[0]),
                        'line': line, 'structureType': 'function',
                        'code': '\n'.join(lines[line - 1:end]), '_end': end})
    return symbols


# ── Call-site extraction ──────────────────────────────────────────────────────
# Emits per-symbol outgoing calls: [{"name","line","snippet"}], consumed by
# skills_lib.write_call_edges (calls:/called_by:/commit_calls: schema).
# Callee name = rightmost identifier (self.helper -> helper, svc.deep.m -> m,
# lzma::detail::helper -> helper).

_CALL_TYPES = {
    'python':     {'call'},
    'typescript': {'call_expression', 'new_expression'},
    'tsx':        {'call_expression', 'new_expression'},
    'javascript': {'call_expression', 'new_expression'},
    'c':          {'call_expression'},
    'cpp':        {'call_expression', 'new_expression'},
    'bash':       {'command'},
    'cmake':      {'normal_command'},
}


def _rightmost_identifier(node, src, depth=0):
    """Resolve a callee expression down to a bare name."""
    if node is None or depth > 12:
        return None
    t = node.type
    if t in ('identifier', 'field_identifier', 'type_identifier',
             'operator_name', 'primitive_type'):
        return _text(node, src)
    if t == 'qualified_identifier':
        return _rightmost_identifier(node.child_by_field_name('name'), src,
                                     depth + 1)
    if t in ('field_expression', 'attribute'):
        return _rightmost_identifier(
            node.child_by_field_name('field')
            or node.child_by_field_name('attribute')
            or node.child_by_field_name('property'), src, depth + 1)
    if t == 'member_expression':
        return _rightmost_identifier(node.child_by_field_name('property'), src,
                                     depth + 1)
    if t in ('parenthesized_expression', 'pointer_expression',
             'unary_expression', 'cast_expression'):
        for c in node.named_children:
            r = _rightmost_identifier(c, src, depth + 1)
            if r:
                return r
        return None
    if t in ('template_function', 'template_method'):
        return _rightmost_identifier(node.child_by_field_name('name'), src,
                                     depth + 1)
    if t == 'subscript_expression':
        return _rightmost_identifier(node.child_by_field_name('argument'), src,
                                     depth + 1)
    return None


def _extract_calls(tree, src, lang, lines):
    """[(line, callee_name, snippet)] for every call site in the file."""
    call_types = _CALL_TYPES.get(lang, {'call_expression'})
    out = []
    for node in _walk(tree.root_node):
        if node.type not in call_types:
            continue
        name = None
        if lang == 'bash':
            cn = node.child_by_field_name('name')
            if cn is None:
                cn = next((c for c in node.children if c.type == 'command_name'),
                          None)
            if cn is not None:
                name = _text(cn, src).strip().strip('"\'')
                name = os.path.basename(name) if '/' in name else name
        elif lang == 'cmake':
            ident = next((c for c in node.children if c.type == 'identifier'),
                         None)
            if ident is not None:
                name = _text(ident, src)
        else:
            fn = node.child_by_field_name('function') \
                or node.child_by_field_name('constructor')
            name = _rightmost_identifier(fn, src)
        if not name or not re.match(r'^[A-Za-z_][\w.\-]*$', name):
            continue
        line = _line(node)
        snippet = lines[line - 1].strip()[:200] if line <= len(lines) else ''
        out.append((line, name, snippet))
    return out


# ── Reference (indirect-dispatch) extraction ─────────────────────────────────
# A call graph answers "who calls X". It does NOT answer "whose address was
# taken", which in C is where control flow actually goes: function-pointer
# tables, designated initialisers, ifunc resolvers, weak aliases. 

def _extract_refs(tree, src, lang, lines):
    """[(line, target_name, snippet, kind)] for indirect-dispatch references."""
    if lang not in C_FAMILY:
        return []
    out = []

    def emit(line, name, kind):
        if not name or not re.match(r'^[A-Za-z_]\w*$', name):
            return
        snippet = lines[line - 1].strip()[:200] if line <= len(lines) else ''
        out.append((line, name, snippet, kind))

    for node in _walk(tree.root_node):
        t = node.type
        if t == 'pointer_expression':
            op = node.child_by_field_name('operator')
            is_addr = (op is not None and _text(op, src) == '&') or \
                      (node.children and node.children[0].type == '&')
            if is_addr:
                arg = node.child_by_field_name('argument')
                nm = _rightmost_identifier(arg, src)
                emit(_line(node), nm, 'address_of')
        elif t == 'initializer_pair':
            # `.decode = lzma_raw_decode,` — function tables
            val = node.child_by_field_name('value')
            if val is not None and val.type in ('identifier',
                                                'qualified_identifier'):
                emit(_line(node), _rightmost_identifier(val, src), 'initializer')
        elif t == 'init_declarator':
            val = node.child_by_field_name('value')
            d = node.child_by_field_name('declarator')
            if val is not None and d is not None and _c_is_function_pointer(d) \
                    and val.type in ('identifier', 'qualified_identifier'):
                emit(_line(node), _rightmost_identifier(val, src), 'initializer')
    return out


def _attach_refs(symbols, refs):
    """Assign refs to the innermost enclosing symbol; carry attribute-derived
    refs (ifunc/alias/section) straight onto their own symbol."""
    for s in symbols:
        s.setdefault('refs', [])
    module_sym = next((s for s in symbols if s['name'] == '<module>'), None)
    spans = sorted(
        [s for s in symbols if '_end' in s and s['name'] != '<module>'],
        key=lambda s: s['_end'] - s['line'],
    )
    for line, name, snippet, kind in refs:
        entry = {'name': name, 'line': line, 'snippet': snippet, 'kind': kind}
        for s in spans:
            if s['line'] <= line <= s['_end']:
                s['refs'].append(entry)
                break
        else:
            if module_sym is not None:
                module_sym['refs'].append(entry)

    for s in symbols:
        for kind, target in s.pop('_attr_refs', []):
            s['refs'].append({'name': target, 'line': s['line'],
                              'snippet': f'__attribute__(({kind}("{target}")))',
                              'kind': kind})
    return symbols


def local_def_key(file_path, sym):
    """`<path>:<name>:<line>:<structureType>` — the identity used everywhere
    downstream (Redis `symbol:`/`code:` keys, skill.def_key, change_types).
    The LINE is part of identity: it is what distinguishes six #ifdef variants
    of one macro from each other."""
    return f"{file_path}:{sym['name']}:{sym['line']}:{sym['structureType']}"


def match_occurrences(before_syms, after_syms):
    """Pair up before/after symbols that share (name, structureType).

    Returns (pairs, added, deleted) where pairs is [(old, new)].

    Within a group the pairing is:
      1. exact body match first — an untouched variant keeps its identity even
         if siblings above it were edited and shifted the line numbers;
      2. then positional order (both sides sorted by line) for the remainder,
         which is correct as long as branches aren't reordered wholesale;
      3. leftovers are genuinely added / deleted.

    Same algorithm the reconciler uses to migrate `symbol:` keys, so the
    ingester's diff and the index migration can never disagree about which
    occurrence is which.
    """
    def group(syms):
        g = {}
        for s in syms:
            g.setdefault((s['name'], s['structureType']), []).append(s)
        for v in g.values():
            v.sort(key=lambda s: s['line'])
        return g

    gb, ga = group(before_syms), group(after_syms)
    pairs, added, deleted = [], [], []

    for key in set(gb) | set(ga):
        olds = list(gb.get(key, []))
        news = list(ga.get(key, []))

        # 1. exact body match
        by_code = {}
        for o in olds:
            by_code.setdefault(o['code'], []).append(o)
        matched_old, matched_new = set(), set()
        for n in news:
            bucket = by_code.get(n['code'])
            if bucket:
                o = bucket.pop(0)
                pairs.append((o, n))
                matched_old.add(id(o))
                matched_new.add(id(n))

        # 2. positional pairing of what remains
        rest_old = [o for o in olds if id(o) not in matched_old]
        rest_new = [n for n in news if id(n) not in matched_new]
        for o, n in zip(rest_old, rest_new):
            pairs.append((o, n))

        # 3. leftovers
        deleted.extend(rest_old[len(rest_new):])
        added.extend(rest_new[len(rest_old):])

    return pairs, added, deleted


def _module_symbol(symbols, lines, lang='text'):
    """Synthetic <module> symbol: code = all lines NOT covered by any
    top-level symbol span (imports, top-level statements, decorators).
    Import-time changes therefore diff like any other symbol. Stable
    defkey: <path>:<module>:1:module — line 1 forever, never drifts."""
    covered = set()
    for s in symbols:
        if '_end' in s:
            covered.update(range(s['line'], s['_end'] + 1))
    c = COMMENT_STYLE.get(lang, '#')

    spans = sorted((s['line'], s['_end'], s['name'], s['structureType'])
                   for s in symbols if '_end' in s)

    def _gap_symbols(lo, hi, cap=8):
        """Names of extracted symbols whose span intersects [lo, hi]."""
        names = [f"{n} [{t}] @{a}" for a, b, n, t in spans
                 if a <= hi and b >= lo]
        if len(names) > cap:
            names = names[:cap] + [f'+{len(names) - cap} more']
        return ', '.join(names)

    def _elision_marker(lo, hi):
        inside = _gap_symbols(lo, hi)
        detail = f'extracted as separate symbols: {inside}' if inside \
            else 'blank'
        return (f'{c} … lines {lo}-{hi} elided by DevLoops '
                f'({detail}) …')

    module_lines, prev = [], 0
    for i, ln in enumerate(lines, 1):
        if i in covered or not ln.strip():
            continue
        if i > prev + 1:
            # Marker for EVERY gap, including a leading blank-only one:
            # each marker's "lines LO-HI" range re-anchors file-line
            # mapping, so every kept line after any marker resolves to an
            # EXACT file coordinate (server-side _body_file_lines).
            module_lines.append(_elision_marker(prev + 1, i - 1))
        module_lines.append(ln)
        prev = i
    if prev and prev < len(lines) and _gap_symbols(prev + 1, len(lines)):
        module_lines.append(_elision_marker(prev + 1, len(lines)))
    if not module_lines:
        return None
    return {'name': '<module>', 'line': 1, 'structureType': 'module',
            'code': '\n'.join(module_lines), '_end': 0}


def _attach_calls(symbols, calls):
    """Assign each call site to the innermost symbol span containing it.
    NEVER drops a call: sites outside every symbol span (import-time code —
    the classic supply-chain vector) go to the synthetic <module> symbol."""
    for s in symbols:
        s['calls'] = []
    module_sym = next((s for s in symbols if s['name'] == '<module>'), None)
    # smallest span first = innermost wins; <module> excluded from span match
    spans = sorted(
        [s for s in symbols if '_end' in s and s['name'] != '<module>'],
        key=lambda s: s['_end'] - s['line'],
    )
    for line, name, snippet in calls:
        entry = {'name': name, 'line': line, 'snippet': snippet}
        for s in spans:
            if s['line'] <= line <= s['_end']:
                s['calls'].append(entry)
                break
        else:
            if module_sym is not None:
                module_sym['calls'].append(entry)
    return symbols


# ── Embedded foreign-language detection (candidate emission) ──────────────────
# The ingester runs OFFLINE on the user's machine: no LLM, no network. It only
# COLLECTS string-literal candidates + a free-tier syntactic pre-classification
# (shebang = decisive; code-density gate = skip obvious prose). The server-side
# ingest path batch-classifies the ambiguous remainder via DeepSeek/Makora,
# re-parses confirmed regions with the guest grammar, and attaches embedded
# calls + a language tag to the enclosing symbol. This split keeps extraction
# deterministic and keeps model access where the keys already live.
#
# Security: snippet content is attacker-controlled (untrusted OSS). The ingester
# never executes or interprets it — it only records offsets and raw text. All
# judgement happens later, server-side, with the content treated as inert data.

_STRING_NODES = {
    'python':     {'string'},
    'typescript': {'string', 'template_string'},
    'tsx':        {'string', 'template_string'},
    'javascript': {'string', 'template_string'},
    'c':          {'string_literal', 'concatenated_string'},
    'cpp':        {'string_literal', 'raw_string_literal', 'concatenated_string'},
    'bash':       {'string', 'raw_string', 'heredoc_body'},
    'cmake':      {'quoted_argument', 'bracket_argument'},
}
_STRING_CONTENT_NODES = {'string_content', 'string_fragment', 'quoted_element',
                         'raw_string_content'}

# Minimum length before a literal is even a candidate. Below this, a string
# cannot plausibly carry an embedded language with extractable calls.
_EMBED_MIN_LEN = 24

# Shebang interpreter -> language HINT (passed to the LLM as lang_hint,
# never a verdict — every candidate is still classified server-side).
_SHEBANG_LANG = {
    'sh': 'bash', 'bash': 'bash', 'zsh': 'bash', 'dash': 'bash',
    'python': 'python', 'python3': 'python', 'node': 'javascript',
}


def _shebang_lang(text):
    """First line #!/... -> guest language hint, or None. Matches the
    interpreter basename exactly (env-aware, version-suffix-stripped)."""
    if not text.startswith('#!'):
        return None
    parts = text.splitlines()[0][2:].strip().split()
    if not parts:
        return None
    interp = os.path.basename(parts[0])
    if interp == 'env' and len(parts) > 1:
        interp = os.path.basename(parts[1])
    interp = re.sub(r'[\d.]+$', '', interp)   # python3.12 -> python
    return _SHEBANG_LANG.get(interp)


def _code_density(text):
    """Cheap prose-vs-code signal in [0,1]: fraction of lines containing a
    code-shaped character. Used ONLY to drop obvious prose before the server
    spends an LLM call — never to make a positive language claim."""
    lines = [l for l in text.splitlines() if l.strip()]
    if not lines:
        return 0.0
    code_markers = set('{};()=<>|&$#')
    hits = sum(1 for l in lines if any(c in code_markers for c in l))
    return hits / len(lines)


def _collect_string_literals(tree, src, lang):
    """[(start_line, content_text)] for every string literal >= _EMBED_MIN_LEN.
    Concatenates multi-fragment template strings. Skips f-string interpolation
    fragments implicitly (they parse as separate short content nodes)."""
    string_types = _STRING_NODES.get(lang, {'string'})
    out = []
    stack = [tree.root_node]
    while stack:
        node = stack.pop()
        if node.type in string_types:
            frags = []
            seen = set()
            substack = [node]
            while substack:
                n = substack.pop()
                if id(n) in seen:
                    continue
                seen.add(id(n))
                if n.type in _STRING_CONTENT_NODES:
                    frags.append(_text(n, src))
                # LIFO stack: children must be pushed reversed or fragments
                # concatenate in reverse document order — garbling exactly
                # the attacker-controlled content the classifier reads.
                substack.extend(reversed(n.children))
            content = ''.join(frags) if frags else _text(node, src)
            if len(content) >= _EMBED_MIN_LEN:
                out.append((_line(node), content))
            # Don't descend into an already-captured string.
            continue
        stack.extend(reversed(node.children))
    return out


def _extract_embedded_candidates(tree, src, lang, symbols):
    """Attach candidate embedded regions to the enclosing symbol.
    Each candidate: {content, line, host_pretag, density}.
      host_pretag: shebang-derived language HINT ('bash'|'python'|'javascript'),
      else ''. Never a verdict — the server LLM-classifies every candidate.
    Server fills in {lang, confidence, suspicious, summary, calls} after
    classification. Every literal >= _EMBED_MIN_LEN is emitted; zero-density
    gating happens server-side."""
    for s in symbols:
        s['embedded'] = []
    literals = _collect_string_literals(tree, src, lang)
    if not literals:
        return
    spans = sorted(
        [s for s in symbols if '_end' in s and s['name'] != '<module>'],
        key=lambda s: s['_end'] - s['line'],
    )
    module_sym = next((s for s in symbols if s['name'] == '<module>'), None)
    for line, content in literals:
        pretag = _shebang_lang(content) or ''
        density = round(_code_density(content), 3)
        cand = {'content': content, 'line': line,
                'host_pretag': pretag, 'density': density}
        owner = None
        for sp in spans:
            if sp['line'] <= line <= sp['_end']:
                owner = sp
                break
        target = owner or module_sym
        if target is not None:
            target['embedded'].append(cand)


# ── Tier 3 / Tier 4: whole-file and opaque ───────────────────────────────────

def _shannon_entropy(data):
    if not data:
        return 0.0
    counts = [0] * 256
    for b in data:
        counts[b] += 1
    n = len(data)
    return -sum((c / n) * math.log2(c / n) for c in counts if c)


def _magic_label(data):
    for sig, label in BINARY_MAGIC.items():
        if data.startswith(sig):
            return label
    return 'unrecognised'


_STRINGS_RE = re.compile(rb'[\x20-\x7e]{6,}')
_B64_RE = re.compile(rb'[A-Za-z0-9+/]{40,}={0,2}')
_INTERESTING_RE = re.compile(
    r'(https?://|[0-9]{1,3}(\.[0-9]{1,3}){3}|/[a-z][\w./-]{3,}'
    r'|\.so(\.|$)|\.dll$|[a-z]+_[a-z_]{4,}|[A-Z][a-z]+[A-Z]\w+)')

_ELF_MACHINE = {0x03: 'x86', 0x28: 'ARM', 0x3e: 'x86-64',
                0xb7: 'AArch64', 0xf3: 'RISC-V'}
_ELF_TYPE = {1: 'relocatable (.o)', 2: 'executable',
             3: 'shared object / PIE', 4: 'core dump'}


def _printable_strings(data, cap=40, scan_limit=1_048_576):
    """Top printable strings, interesting-first (URLs, IPs, paths,
    identifier-shaped). Deterministic, capped — never floods the body."""
    seen, interesting, plain = set(), [], []
    for m in _STRINGS_RE.finditer(data[:scan_limit]):
        s = m.group().decode('ascii', 'replace')[:120]
        if s in seen:
            continue
        seen.add(s)
        (interesting if _INTERESTING_RE.search(s) else plain).append(s)
        if len(interesting) >= cap:
            break
    out = interesting + plain[:max(0, cap - len(interesting))]
    return out, len(seen)


def _base64_findings(data, cap=5, scan_limit=1_048_576):
    """Long base64 runs + entropy of their decoded bytes. High decoded
    entropy = embedded encrypted/packed payload."""
    import base64 as _b64
    out = []
    for m in _B64_RE.finditer(data[:scan_limit]):
        run = m.group()
        try:
            dec = _b64.b64decode(run + b'=' * (-len(run) % 4), validate=False)
        except Exception:
            continue
        out.append((len(run), _shannon_entropy(dec[:4096])))
        if len(out) >= cap:
            break
    return out


def _elf_summary(data):
    """Header-only ELF facts, pure Python. None if not ELF/too short."""
    if not data.startswith(b'\x7fELF') or len(data) < 20:
        return None
    bits = {1: '32-bit', 2: '64-bit'}.get(data[4], '?')
    endian = {1: 'LE', 2: 'BE'}.get(data[5], '?')
    e_type = int.from_bytes(data[16:18], 'little' if data[5] == 1 else 'big')
    machine = int.from_bytes(data[18:20], 'little' if data[5] == 1 else 'big')
    return (f'{bits} {endian} {_ELF_TYPE.get(e_type, f"type={e_type}")} '
            f'for {_ELF_MACHINE.get(machine, f"machine=0x{machine:x}")}')


def _high_entropy_profile(data, window=256, thresh=7.2, scan_limit=1_048_576):
    """Fraction of the file that is near-random, and the largest contiguous
    near-random run (bytes). A malformed-header fixture is a small
    high-entropy region on otherwise-structured data; an encrypted/packed
    payload is high-entropy across most of the file. NOT a flag — every
    compressed fixture is high-entropy — but the SHAPE (how much of the file
    is unconstrained) is a stored fact a probe reads instead of eyeballing a
    single average. Coarse on small blobs (needs >= one 256 B window)."""
    view = data[:scan_limit]
    n = len(view)
    if n < window:
        return None
    hi = longest = cur = 0
    for off in range(0, n - window + 1, window):
        if _shannon_entropy(view[off:off + window]) >= thresh:
            hi += window
            cur += window
            longest = max(longest, cur)
        else:
            cur = 0
    return hi / n, longest


def _blob_byte_delta(before, after):
    """Common-prefix / common-suffix / changed-middle span of two blob
    versions. Describes the SHAPE of the change; the changed bytes stay
    unread. A stated regeneration/cleanup goal PERMITS any shape but does
    not PREDICT which region moved."""
    la, lb = len(before), len(after)
    m = min(la, lb)
    p = 0
    while p < m and before[p] == after[p]:
        p += 1
    s = 0
    while s < (m - p) and before[la - 1 - s] == after[lb - 1 - s]:
        s += 1
    return {'prefix': p, 'suffix': s,
            'old_changed': la - p - s, 'new_changed': lb - p - s,
            'size_delta': lb - la}


def _blob_symbols(data, file_path):
    """Tier 4. A hash manifest for opaque content. Binary test fixtures are a
    real payload channel, so they must exist in the graph as something a probe
    can reason about and diff, even though the bytes are not readable."""
    digest = hashlib.sha256(data).hexdigest()
    entropy = _shannon_entropy(data[:65536])
    body = (
        f'opaque binary artifact (machine-generated description — '
        f'the bytes themselves are not shown)\n'
        f'path:    {file_path}\n'
        f'size:    {len(data)} bytes\n'
        f'sha256:  {digest}\n'
        f'entropy: {entropy:.3f} bits/byte (of first 64 KiB)\n'
        f'magic:   {_magic_label(data)}\n'
        f'head:    {data[:48].hex()}\n'
    )
    prof = _high_entropy_profile(data)
    if prof is not None:
        frac, longest = prof
        body += (f'hi-entropy: {frac * 100:.0f}% of file near-random '
                 f'(>=7.2 bits/byte in 256 B windows); largest contiguous '
                 f'near-random run {longest} bytes\n')
    elf = _elf_summary(data)
    if elf:
        body += f'elf:     {elf}\n'
    strings, total_strings = _printable_strings(data)
    if strings:
        body += (f'strings: {total_strings} printable runs found; '
                 f'top {len(strings)} (interesting-first):\n')
        body += ''.join(f'  {s}\n' for s in strings)
    else:
        body += ('strings: NONE — no printable content ≥6 chars; '
                 'structureless data\n')
    b64 = _base64_findings(data)
    if b64:
        body += 'base64:  embedded base64 runs (len, decoded entropy):\n'
        body += ''.join(f'  {ln} chars → {e:.2f} bits/byte\n'
                        for ln, e in b64)

    # Identifier-shaped strings become ref edges (kind='blob_string'):
    # "this blob contains bytes matching this name". NOT calls — a blob
    # executes nothing; the edge records containment, and the kind field
    # keeps probes from over-reading it. Inverse index referenced_by:<name>
    # lets a probe on e.g. RSA_public_decrypt discover the blob.
    refs = []
    seen_ref = set()
    for s in strings:
        if not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]{5,63}', s):
            continue
        if s in seen_ref:
            continue
        seen_ref.add(s)
        refs.append({'name': s, 'line': 1,
                     'snippet': f'printable string in binary: "{s}"',
                     'kind': 'blob_string'})
        if len(refs) >= 15:
            break
    return [{'name': '<blob>', 'line': 1, 'structureType': 'blob',
             'code': body, '_end': 0, 'calls': [], 'refs': refs,
             'embedded': []}]


def _text_symbols(content, lang_hint=''):
    """Tier 3. One <module> symbol carrying the whole file. Coarse — any edit
    marks the file modified — but the content is fully present for semantic
    review, which is what completeness requires."""
    if not content.strip():
        return []
    sym = {'name': '<module>', 'line': 1, 'structureType': 'module',
           'code': _truncate_body(content, lang_hint or 'python'),
           '_end': 0, 'calls': [], 'refs': [], 'embedded': []}
    pretag = _shebang_lang(content) or ''
    if pretag:
        sym['embedded'] = [{'content': content[:20000], 'line': 1,
                            'host_pretag': pretag,
                            'density': round(_code_density(content), 3)}]
    return [sym]


# ── Unified extraction entrypoint ─────────────────────────────────────────────

def is_ingestable(path):
    return not any(s in f'/{path}' for s in SKIP_PATHS)


def _is_binary(data):
    if b'\x00' in data[:8192]:
        return True
    try:
        data.decode('utf-8')
        return False
    except UnicodeDecodeError:
        return True

# Mask vendor attribute-macros (lzma_attribute((__unused__))) so tree-sitter
# parses valid C — but NEVER the real __attribute__: its grammar handles it
# natively, and _c_attributes reads ifunc/alias/constructor from it.
_C_ATTR_MACRO_RE = re.compile(
    r'\b(?!__attribute(?:__)?\b)[A-Za-z_]\w*attribute\w*\s*\(\((?:[^()]|\([^()]*\))*\)\)')

def _mask_attr_macros(content):
    """Blank attribute-style macro calls (`lzma_attribute((__unused__))`)
    with equal-length spaces so tree-sitter parses valid C. Offsets are
    preserved, so slices of the original content are unaffected."""
    def _blank(m):
        # Keep every newline and the exact byte length, so line numbers and
        # byte offsets of the parsed text match the original file.
        return ''.join('\n' if ch == '\n' else ' ' * len(ch.encode('utf-8'))
                       for ch in m.group(0))
    return _C_ATTR_MACRO_RE.sub(_blank, content)

def resolve_language(file_path, content):
    """(lang, tier, tree). '?c' means ambiguous header — decided by trial
    parse. A grammar that produces an ERROR-heavy parse is rejected in
    favour of Tier 3, so a bad guess degrades to whole-file rather than to
    nonsense. The tree that scored the ratio is RETURNED and reused by
    extraction — one parse per file, not 2-4. tree is None for Tier 3."""
    base = os.path.basename(file_path)
    ext = os.path.splitext(file_path)[1].lower()
    lang = LANG_BY_NAME.get(base)
    if lang is None and ext in TEXT_EXEMPT:
        return None, 3, None
    if lang is None:
        if base.startswith('Makefile'):
            # .am/.inc are automake dialect: the make grammar mis-parses
            # if/endif as rules at an error ratio BELOW the gate (verified
            # 0.029 on liblzma/Makefile.am) — regex extraction instead.
            lang = 'automake' if ext in ('.am', '.inc') else 'make'
        else:
            lang = LANG_BY_EXT.get(ext)
    if lang is None and content.startswith('#!'):
        # .in script templates and extensionless scripts (update-po,
        # test_compress_*). @POSIX_SHELL@-style shebangs resolve to no
        # interpreter — for .in that still means shell.
        lang = _shebang_lang(content)
        if lang is None and ext == '.in':
            lang = 'bash'
    if lang is None:
        return 'text', 3, None      # covered: whole-file symbol, full diff
    if not content.strip():
        return None, 3, None
    if lang in NO_PARSE:
        return lang, 2, None

    if lang in ('c', 'cpp', '?c'):
        content = _mask_attr_macros(content)
    src = content.encode('utf-8')
    if lang == '?c':
        best, best_ratio, best_tree = None, 1.0, None
        for cand in ('c', 'cpp'):
            try:
                tree = _parser(cand).parse(src)
                ratio = _error_ratio(tree)
            except Exception:
                continue
            if ratio < best_ratio:
                best, best_ratio, best_tree = cand, ratio, tree
        if best is None or best_ratio > MAX_ERROR_RATIO:
            return 'text', 3, None
        return best, 1, best_tree

    try:
        tree = _parser(lang).parse(src)
        ratio = _error_ratio(tree)
    except Exception:
        return 'text', 3, None      # grammar missing/broken → still covered
    if ratio > MAX_ERROR_RATIO:
        log_phase('resolve', 'DEMOTE', file=os.path.basename(file_path),
                  lang=lang, error_ratio=round(ratio, 3))
        return 'text', 3, None
    return lang, (1 if lang in TIER1 else 2), tree

_TIER1_EXTRACTORS = {
    'python':     _py_symbols,
    'typescript': _ts_symbols,
    'tsx':        _ts_symbols,
    'javascript': _ts_symbols,
    'c':          _c_symbols,
    'cpp':        _c_symbols,
}

_TIER2_EXTRACTORS = {
    'bash':  _bash_symbols,
    'cmake': _cmake_symbols,
    'yaml':  _yaml_symbols,
    'make':  _make_symbols,
}

_NO_PARSE_EXTRACTORS = {
    'm4':       _m4_symbols,
    'asm':      _asm_symbols,
    'automake': _automake_symbols,
}


def extract_symbols_from_bytes(data, file_path):
    """The single entry point. Every ingestable file returns >= 1 symbol
    unless it is genuinely empty."""
    if data is None:
        return []
    if _is_binary(data):
        return _blob_symbols(data, file_path)
    content = data.decode('utf-8', 'replace')
    return extract_symbols(content, file_path)


def extract_symbols(content, file_path):
    lang, tier, tree = resolve_language(file_path, content)

    if tier == 3 or lang is None:
        return _text_symbols(content)

    if lang in MODULE_ONLY_LANGS:
        # One <module> symbol, whole-file body, def_key
        # <path>:<module>:1:module — byte-accurate code_at snapshots.
        return _text_symbols(content, lang)

    if lang in NO_PARSE:
        lines = content.splitlines()
        symbols = _NO_PARSE_EXTRACTORS[lang](content, lines)
        mod = _module_symbol(symbols, lines, lang)
        if mod is not None:
            symbols.append(mod)
        if not symbols:
            return _text_symbols(content, lang)
        for s in symbols:
            s.setdefault('calls', [])
            s.setdefault('refs', [])
            s.setdefault('embedded', [])
            s.pop('_end', None)
        return symbols

    src = content.encode('utf-8')
    lines = content.splitlines()
    start = time.time()
    try:
        # tree comes from resolve_language — no second parse. Byte offsets
        # stay valid: encode('utf-8') is deterministic, same bytes it parsed.
        if tier == 1:
            fn = _TIER1_EXTRACTORS[lang]
            symbols = fn(src, content, lines, tree) if lang == 'python' \
                else fn(src, lang, lines, tree)
        else:
            symbols = _TIER2_EXTRACTORS[lang](src, lang, lines, tree)

        mod = _module_symbol(symbols, lines, lang)
        if mod is not None:
            symbols.append(mod)

        _attach_calls(symbols, _extract_calls(tree, src, lang, lines))
        _attach_refs(symbols, _extract_refs(tree, src, lang, lines))
        _extract_embedded_candidates(tree, src, lang, symbols)

        # Coverage guarantee: a parseable file that yielded nothing still
        # enters the graph as whole text rather than vanishing.
        if not symbols:
            return _text_symbols(content, lang)

        for _s in symbols:
            _s.pop('_end', None)
            _s.pop('_fnptr', None)
            _s.pop('_attr_refs', None)
    except Exception as e:
        log_phase('extract', 'ERROR', file=os.path.basename(file_path),
                  lang=lang, error=f'{type(e).__name__}: {e}')
        return _text_symbols(content, lang)   # degrade, never drop

    dur = int((time.time() - start) * 1000)
    if dur > 2000:
        log_phase('extract', 'END', file=os.path.basename(file_path),
                  duration_ms=dur, symbols=len(symbols), slow=True)
    return symbols


# ── Ancestry (same-file references with scope context) ────────────────────────
# Replaces buildScopeMap + regex scan (TS) and python-ancestry.py (Py).
# Scope type strings preserved per language:
#   python: 'FunctionDef' | 'AsyncFunctionDef' | 'ClassDef' | 'module'
#   ts/js:  'function' | 'class' | 'module'
#   c/cpp:  'function' | 'class' | 'module'

_SCOPE_FN_TYPES = {
    'python': {'function_definition'},
    'c':      {'function_definition'},
    'cpp':    {'function_definition', 'lambda_expression'},
    'bash':   {'function_definition'},
    'cmake':  {'function_def', 'macro_def'},
}
_SCOPE_CLS_TYPES = {
    'python': {'class_definition'},
    'c':      {'struct_specifier', 'union_specifier', 'enum_specifier'},
    'cpp':    {'class_specifier', 'struct_specifier', 'union_specifier',
               'namespace_definition'},
}
_TS_SCOPE_FN = {'function_declaration', 'generator_function_declaration',
                'method_definition', 'arrow_function', 'function_expression'}
_TS_SCOPE_CLS = {'class_declaration', 'abstract_class_declaration'}


def _scope_spans(src, lang, tree=None):
    """[(start_line, end_line, name, type)] for all function/class scopes."""
    if tree is None:
        tree = _parser(lang).parse(src)
    spans = []

    if lang in ('typescript', 'tsx', 'javascript'):
        fn_types, cls_types = _TS_SCOPE_FN, _TS_SCOPE_CLS
    else:
        fn_types = _SCOPE_FN_TYPES.get(lang, set())
        cls_types = _SCOPE_CLS_TYPES.get(lang, set())

    def name_of(node):
        n = node.child_by_field_name('name')
        if n is not None:
            return _text(n, src)
        d = node.child_by_field_name('declarator')
        if d is not None:
            nm = _c_declarator_name(d)
            if nm is not None:
                return _text(nm, src)
        return None

    def visit(node, class_name):
        t = node.type
        if t in fn_types:
            name = name_of(node)
            if name is None and t == 'arrow_function' \
                    and node.parent is not None \
                    and node.parent.type == 'variable_declarator':
                pn = node.parent.child_by_field_name('name')
                name = pn.text.decode() if pn is not None else None
            if name:
                name = _norm_name(name)
                full = f'{class_name}.{name}' if class_name else name
                if lang == 'python':
                    stype = 'AsyncFunctionDef' if _py_is_async(node) else 'FunctionDef'
                else:
                    stype = 'function'
                spans.append((_line(node), _end_line(node), full, stype))
        elif t in cls_types:
            name = name_of(node)
            if name is not None:
                cn = _norm_name(name)
                stype = 'ClassDef' if lang == 'python' else 'class'
                spans.append((_line(node), _end_line(node), cn, stype))
                for c in node.children:
                    visit(c, cn)
                return
        for c in node.children:
            visit(c, class_name)

    visit(tree.root_node, None)
    return spans


def _build_scope_map(src, lang, tree=None):
    """line -> {'name','type'} of innermost containing scope."""
    scope_map = {}
    # larger spans first, smaller (inner) overwrite
    for start, end, name, stype in sorted(_scope_spans(src, lang, tree=tree), key=lambda s: s[0] - s[1]):
        for ln in range(start, end + 1):
            scope_map[ln] = {'name': name, 'type': stype}
    return scope_map


def find_references(content, symbols, file_path):
    """{symbol: [{'file','line','text','context'}]} — one parse per file.
    Matching uses the LEAF of a qualified name (lzma.Coder.run -> run),
    because that is what actually appears in the source text."""
    lang, tier, tree = resolve_language(file_path, content)
    results = {s: [] for s in symbols}
    if lang is None or tier == 3 or not symbols:
        return results

    lines = content.splitlines()
    leaf_of = {}
    patterns = {}
    for s in symbols:
        if s.startswith('<'):
            continue
        leaf = s.rsplit('.', 1)[-1]
        if not re.match(r'^[A-Za-z_]\w*$', leaf):
            continue
        leaf_of[s] = leaf
        patterns[s] = re.compile(r'\b' + re.escape(leaf) + r'\b')
    if not patterns:
        return results

    line_matches = {}
    for i, line in enumerate(lines, 1):
        for sym, pat in patterns.items():
            if pat.search(line):
                line_matches.setdefault(i, []).append(sym)
    if not line_matches:
        return results

    try:
        scope_map = _build_scope_map(content.encode('utf-8'), lang, tree=tree)
    except Exception:
        scope_map = {}

    default = {'name': '<module>', 'type': 'module'}
    for lineno, syms in line_matches.items():
        scope = scope_map.get(lineno, default)
        for sym in syms:
            results[sym].append({'file': file_path, 'line': lineno,
                                 'text': lines[lineno - 1].strip(),
                                 'context': scope})
    return results


# ── Git plumbing ──────────────────────────────────────────────────────────────

class GitDiffIngester:
    def __init__(self, repo_path):
        self.repo = os.path.abspath(repo_path)

    def _run(self, args):
        start = time.time()
        try:
            r = subprocess.run(['git', '-C', self.repo, *args],
                               capture_output=True)
        except Exception:
            log_phase('git', 'ERROR', cmd=' '.join(args[:2]))
            raise
        dur = int((time.time() - start) * 1000)
        if dur > 5000:
            log_phase('git', 'END', cmd=' '.join(args[:2]),
                      duration_ms=dur, slow=True)
        if r.returncode != 0:
            raise RuntimeError(
                f'git {" ".join(args[:2])} failed: '
                f'{r.stderr.decode("utf-8", "replace")[:200]}')
        return r.stdout

    def git(self, *args):
        return self._run(list(args)).decode('utf-8', 'replace').rstrip('\n')

    def git_raw(self, *args):
        """Undecoded stdout. Binary blobs must not round-trip through
        errors='replace' — that would corrupt the bytes and make the
        content hash meaningless."""
        return self._run(list(args))

    def commit_message(self, h):
        return self.git('log', '--format=%B', '-n', '1', h).strip()

    def author_date(self, h):
        return self.git('log', '--format=%aI', '-n', '1', h).strip()

    def author_name(self, h):
        return self.git('log', '--format=%an <%ae>', '-n', '1', h).strip()

    def _diff_names(self, h, diff_filter):
        """Names changed vs FIRST PARENT. Plain diff-tree outputs nothing
        for merge commits, and vendoring (subtree add, dependency bumps)
        routinely lands via merge — an invisible merge is an invisible
        payload. Diffing parent..h matches file_at_raw(parent, …), so the
        file list and the body reads can never disagree about the baseline.
        --root fallback covers the parentless root commit."""
        parent = self.parent_hash(h)
        if parent:
            out = self.git('diff', '--no-renames', '--name-only',
                           f'--diff-filter={diff_filter}', parent, h)
        else:
            out = self.git('diff-tree', '--root', '--no-commit-id', '-r',
                           '--name-only', f'--diff-filter={diff_filter}', h)
        return [f for f in (l.strip() for l in out.split('\n'))
                if f and is_ingestable(f)]

    def changed_files(self, h):
        return self._diff_names(h, 'ACMR')

    def deleted_files(self, h):
        return self._diff_names(h, 'D')

    def file_at_raw(self, h, path):
        try:
            return self.git_raw('show', f'{h}:{path}')
        except Exception:
            return None

    def file_at(self, h, path):
        data = self.file_at_raw(h, path)
        if data is None or _is_binary(data):
            return None
        return data.decode('utf-8', 'replace')

    def parent_hash(self, h):
        try:
            return self.git('rev-parse', f'{h}^')
        except Exception:
            return None

    def head_hash(self):
        return self.git('rev-parse', 'HEAD')

    def commit_range(self, since=None, max_n=None):
        if since:
            out = self.git('log', '--format=%H', '--topo-order', '--reverse',
                           f'{since}..HEAD')
            hashes = [h for h in out.split('\n') if h]
            if not hashes:
                # Root-commit fallback: sinceRef..HEAD excludes sinceRef itself,
                # so a root ref yields nothing — return full history instead.
                try:
                    root = self.git('rev-parse', since)
                    self.git('cat-file', '-e', root)
                    out = self.git('log', '--format=%H', '--topo-order',
                                   '--reverse')
                    hashes = [h for h in out.split('\n') if h]
                except Exception:
                    hashes = []
            return hashes[:max_n] if max_n else hashes
        count = f'-{max_n}' if max_n else ''
        args = ['log', '--format=%H', '--topo-order'] + ([count] if count else [])
        out = self.git(*args)
        return [h for h in out.split('\n') if h][::-1]

    # ── Symbol diffing ────────────────────────────────────────────────────────

    def changed_symbols(self, file_path, before, after):
        """before/after are raw bytes (or None).

        A single file legitimately holds several symbols sharing BOTH name and
        structureType — six #if/#elif variants of the same macro, a shell
        variable reassigned down the script, repeated cmake set() calls. Those
        are distinct symbols with distinct def_keys (the line differentiates
        them), so a name-keyed or (name,type)-keyed diff silently drops all but
        one. Diffing is therefore done per occurrence, using match_occurrences.
        """
        after_syms = extract_symbols_from_bytes(after, file_path)
        if before is None:
            return [dict(s, filePath=file_path, changeType='added')
                    for s in after_syms]

        before_syms = extract_symbols_from_bytes(before, file_path)
        pairs, added, deleted = match_occurrences(before_syms, after_syms)

        changed = []
        for old, new in pairs:
            if old['code'] != new['code']:
                nc = dict(new, filePath=file_path, changeType='modified')
                if new['structureType'] == 'blob' and before and after:
                    d = _blob_byte_delta(before, after)
                    nc['code'] += (
                        f"delta:   {d['prefix']} B identical prefix, "
                        f"{d['suffix']} B identical suffix; "
                        f"{d['old_changed']}->{d['new_changed']} B changed "
                        f"region ({d['size_delta']:+d} B)\n"
                        f"         framing outside the changed region is "
                        f"byte-identical; the changed region is unread. A "
                        f"stated regeneration/cleanup goal PERMITS this shape "
                        f"but does not PREDICT which region moved.\n")
                changed.append(nc)
        for s in added:
            changed.append(dict(s, filePath=file_path, changeType='added'))
        for s in deleted:
            changed.append(dict(s, filePath=file_path, changeType='deleted'))
        return changed

    # ── Ancestry enrichment ───────────────────────────────────────────────────

    def enrich_ancestry(self, h, origins, changed):
        if not changed:
            return
        log_phase('ancestry', 'START', commit=h[:8], total_symbols=len(changed))
        start = time.time()

        live = [s for s in changed if s['changeType'] != 'deleted']
        by_file = {}
        for s in live:
            by_file.setdefault(s['filePath'], []).append(s)

        for file_path, syms in by_file.items():
            content = self.file_at(h, file_path)
            if content is None:
                continue
            refs_by_symbol = find_references(
                content, [s['name'] for s in syms], file_path)
            for s in syms:
                refs = refs_by_symbol.get(s['name']) or []
                if not refs:
                    continue
                def_key = (f"{s['filePath']}:{s['name']}:"
                           f"{s['line']}:{s['structureType']}")
                origins[def_key] = json.dumps(refs)

        log_phase('ancestry', 'END', commit=h[:8],
                  duration_ms=int((time.time() - start) * 1000))

    def _blob_consumers(self, commit, file_path):
        """Files at this commit that reference the fixture BY EXACT NAME,
        as sorted (path, is_ingestable) pairs; None on git failure — an
        infra error must never render as "nothing names it". Non-ingested
        hits (READMEs, docs) are kept and tagged: a maintainer-written
        description of the fixture is evidence a probe should see, even
        though its body isn't in the graph. Glob-based consumers (a
        harness looping files/bad-*.xz) reference by pattern, not name,
        so they do NOT appear here — matching those is a server-side
        graph query over already-ingested harness symbols. Bounded to the
        tree at this commit; a consumer added later is invisible here."""
        base = os.path.basename(file_path)
        # -e marks the name as search text even if it starts with '-';
        # '--' ends the options. Without them a file name can inject options.
        r = subprocess.run(['git', '-C', self.repo, 'grep', '-l', '-F',
                            '-e', base, commit, '--'], capture_output=True)
        if r.returncode not in (0, 1):
            return None        # exit 1 = no match; anything else = failure
        hits = {}
        for line in r.stdout.decode('utf-8', 'replace').split('\n'):
            p = line.split(':', 1)[-1].strip()   # strip `<rev>:` prefix
            if p and p != file_path:
                hits[p] = is_ingestable(p)
        return sorted(hits.items())

    # ── Core ingest ───────────────────────────────────────────────────────────

    def ingest_commit(self, h, goal_override=None):
        resolved = self.head_hash() if h == 'HEAD' else h
        log_phase('ingestCommit', 'START', commit=resolved[:8])
        start = time.time()
        try:
            goal = goal_override if goal_override is not None \
                else self.commit_message(resolved)
            changed_files = self.changed_files(resolved)
            deleted_files = self.deleted_files(resolved)
            parent = self.parent_hash(resolved)
            new_files = []

            definitions, origins = {}, {}
            file_payloads, all_changed = [], []

            for file_path in changed_files:
                after = self.file_at_raw(resolved, file_path)
                if after is None:
                    continue
                before = self.file_at_raw(parent, file_path) if parent else None
                is_new = before is None
                if is_new:
                    new_files.append(file_path)

                all_symbols = extract_symbols_from_bytes(after, file_path)
                changed = self.changed_symbols(file_path, before, after)

                if _is_binary(after):
                    named = self._blob_consumers(resolved, file_path)
                    if named is None:
                        tag = ('named by: (consumer check failed — no claim '
                               'about who references this file)\n')
                    elif named:
                        tag = ('named by: ' + ', '.join(
                            p if ing else f'{p} (not ingested)'
                            for p, ing in named) + '\n')
                    else:
                        tag = ('named by: NONE — no file at this commit '
                               'references this fixture by exact name '
                               '(glob-based consumers are matched '
                               'server-side, not here)\n')
                    for s in all_symbols + changed:
                        if s.get('structureType') == 'blob':
                            s['code'] += tag

                # def_key-keyed, NOT name-keyed. Six #ifdef variants of one
                # macro are six symbols with six def_keys; a name-keyed dict
                # would report a single change type for all of them and five
                # would never reach a skill.
                change_types = {local_def_key(file_path, s): s['changeType']
                                for s in changed}
                for s in changed:
                    if s['changeType'] != 'deleted':
                        definitions[local_def_key(file_path, s)] = s['code']
                    all_changed.append(s)

                file_payloads.append({
                    'filePath': file_path,
                    'isNew': is_new,
                    'isDeleted': False,
                    'allSymbols': all_symbols,
                    # Dead since occurrence pairing replaced hunk math.
                    # Key kept as [] so the server's payload parser is
                    # untouched; was one git subprocess per file per commit.
                    'lineDeltas': [],
                    'changeTypes': change_types,
                })

            for file_path in deleted_files:
                if not parent:
                    continue
                before = self.file_at_raw(parent, file_path)
                symbols = extract_symbols_from_bytes(before, file_path) \
                    if before else []
                file_payloads.append({
                    'filePath': file_path,
                    'isNew': False,
                    'isDeleted': True,
                    'allSymbols': symbols,
                    'lineDeltas': [],
                    'changeTypes': {local_def_key(file_path, s): 'deleted'
                                    for s in symbols},
                })

            if all_changed:
                self.enrich_ancestry(resolved, origins, all_changed)

            payload = {
                'goal': goal,
                'commitHash': resolved,
                'authorDate': self.author_date(resolved),
                'author': self.author_name(resolved),
                'filesChanged': changed_files,
                'newFiles': new_files,
                'deletedFiles': deleted_files,
                'searchResults': [{
                    'query': goal,
                    'pattern': f'git:{resolved[:8]}',
                    'matches': [],
                    'timestamp': int(time.time() * 1000),
                    'definitions': definitions,
                    'origins': origins,
                    'files': file_payloads,
                }],
            }
            log_phase('ingestCommit', 'END', commit=resolved[:8],
                      duration_ms=int((time.time() - start) * 1000),
                      filesChanged=len(changed_files),
                      symbols=len(all_changed))
            return payload
        except Exception as e:
            log_phase('ingestCommit', 'ERROR', commit=resolved[:8],
                      duration_ms=int((time.time() - start) * 1000),
                      error=f'{type(e).__name__}: {e}')
            raise


# ── Coverage scan ─────────────────────────────────────────────────────────────

def scan_coverage(repo_path):
    """Accurate per-file coverage of the repo at HEAD.

    Every file is resolved through resolve_language — the same code path
    ingestion uses — so the yes/no is real, not an extension guess. A .h
    that would demote to whole-file on actual content reports as not
    covered. Binary files are manifest-only, reported as not covered.

    Output (stdout JSON):
      {
        "covered":     {"<ext-or-name>": count, ...},
        "not_covered": {"<ext-or-name>": count, ...},
        "files_covered": N, "files_not_covered": M, "files_total": T,
        "not_covered_files": [path, ...]     # the ask-us list
      }
    """
    ing = GitDiffIngester(repo_path)
    head = ing.head_hash()
    out = ing.git('ls-tree', '-r', '--name-only', head)
    paths = [p for p in out.split('\n') if p and is_ingestable(p)]

    def bucket(path):
        base = os.path.basename(path)
        if base in LANG_BY_NAME:
            return base
        ext = os.path.splitext(path)[1].lower()
        return ext if ext else base

    covered, not_covered, nc_files = {}, {}, []
    for path in paths:
        data = ing.file_at_raw(head, path)
        if data is None:
            continue
        if _is_binary(data):
            magic = next(
                (label for sig, label in BINARY_MAGIC.items()
                 if data[:8].startswith(sig)),
                None,
            )
            b = bucket(path)
            if magic:
                key = f"{b} [{magic}]"
                covered[key] = covered.get(key, 0) + 1
            else:
                key = f"{b} [unknown binary]"
                not_covered[key] = not_covered.get(key, 0) + 1
                nc_files.append(path)
            continue
        else:
            content = data.decode('utf-8', 'replace')
            lang, tier, _tree = resolve_language(path, content)
        b = bucket(path)
        if lang is not None:
            covered[b] = covered.get(b, 0) + 1
        else:
            not_covered[b] = not_covered.get(b, 0) + 1
            nc_files.append(path)

    return {
        'covered':     dict(sorted(covered.items(), key=lambda kv: -kv[1])),
        'not_covered': dict(sorted(not_covered.items(), key=lambda kv: -kv[1])),
        'files_covered':     sum(covered.values()),
        'files_not_covered': sum(not_covered.values()),
        'files_total':       sum(covered.values()) + sum(not_covered.values()),
        'not_covered_files': nc_files,
    }

# ── CLI ───────────────────────────────────────────────────────────────────────

def _flag(rest, name):
    try:
        i = rest.index(f'--{name}')
        return rest[i + 1] if i + 1 < len(rest) else None
    except ValueError:
        return None


def main():
    if len(sys.argv) < 3:
        print('Usage: ingester.py <repoPath> <command> [...args]\n'
              '  commit <hash> [--goal "msg"]\n'
              '  list-commits [--since <ref>] [--max <n>]\n'
              '  scan-coverage\n'
              '  prefetch', file=sys.stderr)
        sys.exit(1)

    repo_path, command, *rest = sys.argv[1:]

    if command == 'prefetch':
        for lang in PREFETCH_LANGS:
            try:
                _parser(lang)
                print(f'grammar ready: {lang}', file=sys.stderr)
            except Exception as e:
                print(f'grammar MISSING: {lang} ({e})', file=sys.stderr)
        return

    ingester = GitDiffIngester(repo_path)
    try:
        if command == 'commit':
            h = next((r for r in rest if not r.startswith('--')), 'HEAD')
            payload = ingester.ingest_commit(h, _flag(rest, 'goal'))
            sys.stdout.write(json.dumps(payload))
        elif command == 'list-commits':
            since = _flag(rest, 'since')
            max_flag = _flag(rest, 'max')
            max_n = int(max_flag) if max_flag else None
            sys.stdout.write(json.dumps(ingester.commit_range(since, max_n)))
        elif command == 'scan-coverage':
            sys.stdout.write(json.dumps(scan_coverage(repo_path), indent=2))
        else:
            print(f'Unknown command: {command}', file=sys.stderr)
            sys.exit(1)
    except Exception as e:
        print(str(e), file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()