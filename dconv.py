#!/usr/bin/env python3
"""dconv - SQL Server to MySQL file converter"""

import argparse
import json
import re
import sys
import os
import glob as _glob

VERSION = "1.2.0"


# ---------------------------------------------------------------------------
# File I/O
# ---------------------------------------------------------------------------

def read_file(path: str) -> str:
    """Read a file handling UTF-16 BOM, UTF-8 BOM, or plain UTF-8."""
    with open(path, 'rb') as f:
        raw = f.read()
    if raw[:2] in (b'\xff\xfe', b'\xfe\xff'):
        return raw.decode('utf-16')
    if raw[:3] == b'\xef\xbb\xbf':
        return raw.decode('utf-8-sig')
    return raw.decode('utf-8', errors='replace')


def write_file(path: str, content: str) -> None:
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

def _config_path() -> str:
    xdg = os.environ.get('XDG_CONFIG_HOME', os.path.join(os.path.expanduser('~'), '.config'))
    return os.path.join(xdg, 'dconv', 'config.json')


def load_config(custom_path: str | None = None) -> dict:
    path = custom_path if custom_path else _config_path()
    if not os.path.isfile(path):
        if custom_path:
            print(f"Error: config file '{path}' not found.", file=sys.stderr)
            sys.exit(1)
        return {}
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        print(f"Warning: could not read config '{path}': {e}", file=sys.stderr)
        return {}


def _extract_db_name(content: str) -> str | None:
    """Extract database name from USE [DbName] statement."""
    m = re.search(r'(?im)^USE\s+\[([^\]]+)\]', content)
    return m.group(1) if m else None


def _find_db_config(config: dict, db_name: str | None, source_filename: str) -> dict:
    """
    Lookup database-specific config:
    1. Exact match on db_name extracted from USE statement
    2. Substring match: a key in databases that appears in the source filename
    3. Fallback to 'default' block
    """
    databases = config.get('databases', {})

    # 1. Exact match on USE db name
    if db_name and db_name in databases:
        return databases[db_name]

    # 2. Substring match on source filename
    basename = os.path.basename(source_filename)
    for key in databases:
        if key in basename:
            return databases[key]

    # 3. Default
    return config.get('default', {})


# ---------------------------------------------------------------------------
# Values parser (used for CREATE TABLE type inference)
# ---------------------------------------------------------------------------

def _split_values(vals: str) -> list:
    """Split comma-separated SQL values respecting single-quoted strings."""
    parts = []
    buf = []
    in_str = False
    i = 0
    while i < len(vals):
        c = vals[i]
        if not in_str and c == "'":
            in_str = True
            buf.append(c)
        elif in_str and c == "'":
            buf.append(c)
            # Escaped '' inside string
            if i + 1 < len(vals) and vals[i + 1] == "'":
                buf.append("'")
                i += 2
                continue
            in_str = False
        elif not in_str and c == ',':
            parts.append(''.join(buf).strip())
            buf = []
        else:
            buf.append(c)
        i += 1
    if buf:
        parts.append(''.join(buf).strip())
    return parts


def _infer_type(value: str) -> str:
    v = value.strip()
    if v.upper() == 'NULL':
        return 'TEXT'
    if v.startswith("'"):
        return 'TEXT'
    try:
        int(v)
        return 'INT'
    except ValueError:
        pass
    try:
        float(v)
        return 'DOUBLE'
    except ValueError:
        pass
    return 'TEXT'


def _read_values_block(content: str, pos: int) -> tuple:
    """
    Starting at pos (right after 'VALUES ('), read the content of the
    parentheses block, respecting nested parens and quoted strings.
    Returns (values_str, end_pos).
    """
    depth = 1
    in_str = False
    start = pos
    while pos < len(content) and depth > 0:
        c = content[pos]
        if not in_str and c == "'":
            in_str = True
        elif in_str and c == "'":
            if pos + 1 < len(content) and content[pos + 1] == "'":
                pos += 2
                continue
            in_str = False
        elif not in_str and c == '(':
            depth += 1
        elif not in_str and c == ')':
            depth -= 1
        pos += 1
    return content[start:pos - 1], pos


# ---------------------------------------------------------------------------
# CREATE TABLE generation
# ---------------------------------------------------------------------------

def _extract_tables(content: str) -> dict:
    """
    Scan ALL INSERT INTO statements and build a map of
    table_name -> (ordered_columns, type_map).
    Iterates every INSERT to collect the full union of columns across
    all rows (SQL Server may omit columns with defaults in some INSERTs).
    """
    # table -> {col: type}  (preserving insertion order via dict)
    tables: dict = {}
    header_re = re.compile(
        r'INSERT\s+INTO\s+`(\w+)`\s*\(([^)]+)\)\s*VALUES\s*\(',
        re.IGNORECASE,
    )
    for m in header_re.finditer(content):
        table = m.group(1)
        cols = [c.strip().strip('`') for c in m.group(2).split(',')]
        vals_str, _ = _read_values_block(content, m.end())
        values = _split_values(vals_str)

        if table not in tables:
            tables[table] = {}

        col_types = tables[table]
        for col, val in zip(cols, values):
            # Don't downgrade a known type (TEXT beats INT if mixed)
            existing = col_types.get(col)
            inferred = _infer_type(val)
            if existing is None:
                col_types[col] = inferred
            elif existing == 'INT' and inferred == 'TEXT':
                col_types[col] = 'TEXT'
            elif existing == 'DOUBLE' and inferred == 'TEXT':
                col_types[col] = 'TEXT'

    return tables


def _make_create_table(table: str, cols: list, types: dict) -> str:
    col_defs = ',\n'.join(f"  `{c}` {types.get(c, 'TEXT')}" for c in cols)
    return (
        f"CREATE TABLE IF NOT EXISTS `{table}` (\n"
        f"{col_defs}\n"
        f") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;\n"
    )


# ---------------------------------------------------------------------------
# Extra columns (from config)
# ---------------------------------------------------------------------------

def _make_alter_statements(db_config: dict) -> str:
    """Generate ALTER TABLE ... ADD COLUMN statements from extra_columns config."""
    tables = db_config.get('tables', {})
    stmts = []
    for table, table_cfg in tables.items():
        for col in table_cfg.get('extra_columns', []):
            stmts.append(
                f"ALTER TABLE `{table}` ADD COLUMN `{col['name']}` {col['definition']};"
            )
    return '\n'.join(stmts)


# ---------------------------------------------------------------------------
# Core conversion
# ---------------------------------------------------------------------------

def convert(content: str, clean: bool = False, gen_tables: bool = False) -> str:
    # Normalize line endings
    content = content.replace('\r\n', '\n').replace('\r', '\n')

    # Remove USE [DatabaseName] lines
    if clean:
        content = re.sub(r'(?im)^USE\s+\[[^\]]+\]\s*$\n?', '', content)

    # Remove GO (SQL Server batch separator)
    content = re.sub(r'(?im)^GO\s*$\n?', '', content)

    # Remove SET IDENTITY_INSERT statements (SQL Server-specific, not valid in MySQL)
    content = re.sub(r'(?im)^SET\s+IDENTITY_INSERT\s+.*$\n?', '', content)

    # Remove [dbo]. schema prefix
    content = content.replace('[dbo].', '')

    # Convert [name] -> `name` (only valid SQL identifiers: word chars + spaces)
    content = re.sub(r'\[(\w[\w\s]*)\]', r'`\1`', content)

    # Remove N'' unicode string prefix (N'...' -> '...')
    content = re.sub(r"\bN'", "'", content)

    # Add INTO after INSERT when missing (INSERT `table` -> INSERT INTO `table`)
    content = re.sub(r'(?i)\bINSERT\s+(?!INTO\b)', 'INSERT INTO ', content)

    # Add semicolon at end of each INSERT statement (MySQL requires it)
    # An INSERT ends at the closing ) of VALUES (...), optionally followed by spaces
    content = re.sub(r'\)\s*\n(?=\s*INSERT|\s*CREATE|\s*$)', ');\n', content)

    # Prepend CREATE TABLE statements before first INSERT of each table
    if gen_tables:
        tables = _extract_tables(content)
        for table, col_types in tables.items():
            create_stmt = _make_create_table(table, list(col_types.keys()), col_types)
            pattern = re.compile(
                r'(?=INSERT\s+INTO\s+`' + re.escape(table) + r'`)',
                re.IGNORECASE,
            )
            content = pattern.sub(create_stmt + '\n', content, count=1)

    return content


# ---------------------------------------------------------------------------
# File processing
# ---------------------------------------------------------------------------

def process_file(src: str, dst: str, clean: bool, gen_tables: bool,
                  config: dict | None = None) -> None:
    try:
        content = read_file(src)
    except OSError as e:
        print(f"Error reading '{src}': {e}", file=sys.stderr)
        sys.exit(1)

    # Resolve database-specific config before conversion modifies content
    db_config = {}
    if config:
        db_name = _extract_db_name(content)
        db_config = _find_db_config(config, db_name, src)

    output = convert(content, clean=clean, gen_tables=gen_tables)

    # Append ALTER TABLE statements for extra columns
    alter_stmts = _make_alter_statements(db_config)
    if alter_stmts:
        output = output.rstrip('\n') + '\n\n' + alter_stmts + '\n'

    try:
        write_file(dst, output)
    except OSError as e:
        print(f"Error writing '{dst}': {e}", file=sys.stderr)
        sys.exit(1)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

HELP_TEXT = f"""\
dconv {VERSION} - SQL Server to MySQL file converter

Usage:
  dconv -s <source> -t <target> [options]
  dconv -b [options]

Modes:
  -s SOURCE       Source SQL Server file
  -t TARGET       Target MySQL file
  -b, --bulk-mode Process all .sql files in the current directory;
                  output files are named <basename>_d.sql

Options:
  -c, --clean     Remove USE statements and other SQL Server-specific syntax
  -g              Generate CREATE TABLE statements from INSERT structure
                  (mutually exclusive with -i)
  -i              Generate only INSERT statements, no CREATE TABLE
                  (mutually exclusive with -g)
  -f, --config    Path to a custom config file (default: ~/.config/dconv/config.json)
  -h, --help      Show this help message

Notes:
  - Input files may be UTF-16 or UTF-8; output is always UTF-8
  - [dbo].[Table] notation is converted to backtick syntax
  - N'...' Unicode prefixes are stripped
  - GO batch separators are always removed

Config file:
  dconv looks for ~/.config/dconv/config.json (or $XDG_CONFIG_HOME/dconv/config.json)
  to apply per-database customizations (e.g. extra VIRTUAL GENERATED columns).
  Database is detected from USE [DbName] in the dump, or by matching a
  config key against the source filename. See README for config format.
"""


def main():
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument('-s', metavar='SOURCE')
    parser.add_argument('-t', metavar='TARGET')
    parser.add_argument('-b', '--bulk-mode', action='store_true')
    parser.add_argument('-c', '--clean', action='store_true')
    parser.add_argument('-g', action='store_true')
    parser.add_argument('-i', action='store_true')
    parser.add_argument('-f', '--config', metavar='CONFIG', default=None)
    parser.add_argument('-h', '--help', action='store_true')

    args = parser.parse_args()

    if args.help:
        print(HELP_TEXT)
        sys.exit(0)

    if args.g and args.i:
        print("Error: -g and -i are mutually exclusive.", file=sys.stderr)
        sys.exit(1)

    if args.bulk_mode and (args.s or args.t):
        print("Error: -b/--bulk-mode cannot be combined with -s or -t.", file=sys.stderr)
        sys.exit(1)

    gen_tables = args.g
    config = load_config(args.config)

    if args.bulk_mode:
        source_dir = os.getcwd()
        sql_files = sorted(_glob.glob(os.path.join(source_dir, '*.sql')))
        if not sql_files:
            print(f"No .sql files found in '{source_dir}'.", file=sys.stderr)
            sys.exit(1)
        for src in sql_files:
            base = os.path.splitext(os.path.basename(src))[0]
            dst = os.path.join(os.path.dirname(src), f"{base}_d.sql")
            print(f"  {os.path.basename(src)} -> {os.path.basename(dst)}")
            process_file(src, dst, clean=args.clean, gen_tables=gen_tables,
                         config=config)
        print("Done.")
    else:
        if not args.s or not args.t:
            print("Error: -s and -t are required (or use -b for bulk mode).", file=sys.stderr)
            print(HELP_TEXT)
            sys.exit(1)
        process_file(args.s, args.t, clean=args.clean, gen_tables=gen_tables,
                     config=config)
        print(f"Done: {args.t}")


if __name__ == '__main__':
    main()
