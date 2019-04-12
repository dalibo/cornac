# This module implements config.py editing.
#
# The implementation is solely targetted at appending credentials from
# generate-credentials command. Editing a config.py file to manage credentials
# is far from ideal, but I found it easy to begin and fun to write.
#
# This is only based on lib2to3 from standard library. Comments and identation
# are preserved.

from lib2to3.pytree import Node, Leaf
from lib2to3 import pygram, pytree
from lib2to3.pygram import (
    python_symbols as syms,
    python_grammar_no_print_statement as grammar,
)
from lib2to3.pgen2.driver import Driver
from lib2to3.pgen2 import token


def parse_py(src_txt):
    drv = Driver(grammar, pytree.convert)
    result = drv.parse_string(src_txt, True)
    if isinstance(result, Leaf):
        result = Node(pygram.python_symbols.file_input, [result])
    return result


def iter_assign(node):
    # Find all assignment just below node. Yields varname and value node (an
    # atom node) for editing.

    for stmt in node.children:
        if stmt.type != syms.simple_stmt:
            continue

        assign = stmt.children[0]
        if assign.type != syms.expr_stmt:
            continue

        if assign.children[1].type != token.EQUAL:
            continue

        atom = assign.children[2]
        if atom.type != syms.atom:
            continue

        varname = assign.children[0].value
        yield varname, atom


def append_to_dict(atom, key, value, comment=None):
    dictmaker = atom.children[1]
    closing_brace = atom.children[-1]

    # Automatically append comma.
    if dictmaker.children:
        if dictmaker.children[-1].type != token.COMMA:
            dictmaker.children.append(Leaf(token.COMMA, ','))

    # Manage closing brace prefix to insert our code just before the brace.
    # If there is comments in brace prefix, split lines and keep comments
    # above our code.
    prefix = closing_brace.prefix
    if not prefix:
        # prefix is empty, closing brace is on the same line as final
        # comma. Let's put a new line before our code.
        prefix = '\n'
    # Last brace is likely to be outdented. Pad our code to indent it of
    # one level.
    prefix += '    '
    if comment:
        prefix += f'# {comment}\n    '

    # Insert our code at the end of {…}.
    dictmaker.children.extend([
        Leaf(token.STRING, repr(key), prefix=prefix),
        Leaf(token.COLON, ':'),
        Leaf(token.STRING, repr(value), prefix=' '),
        Leaf(token.COMMA, ',',),
    ])

    # Always put closing brace on a new line after last entry.
    closing_brace.prefix = f'\n'


def append_credentials(src, access_key, secret_key,
                       target='CREDENTIALS', comment='Added by cornac'):
    if isinstance(src, str):
        if not src.endswith('\n'):
            src += '\n'
        src = parse_py(src)
    for varname, atom in iter_assign(src):
        if varname != target:
            continue

        if len(atom.children) == 2:
            # Atom is an empty dict.
            dictmaker = Node(syms.dictsetmaker, [])
            atom.children.insert(1, dictmaker)

        if atom.children[1].type != syms.dictsetmaker:
            raise ValueError(f"{target} is not a plain dict.")

        append_to_dict(atom, key=access_key, value=secret_key, comment=comment)
        break
    else:
        raise ValueError(f"{target} is not set.")
    return src
