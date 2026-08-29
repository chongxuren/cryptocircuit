#!/usr/bin/env python3
"""Verify the published classical circuit IR records.

The verifier deliberately does not treat a standard-cell model as measured
silicon. It validates the retained provenance metadata, checks Boolean/linear
equivalence independently, and recomputes primitive gate counts, circuit depth,
nonlinear depth, and supported algebraic properties. Source PDFs are excluded
from this publication repository by policy, so their recorded SHA-256 values
are validated as metadata rather than rehashed locally.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_IR_DIRS = (
    ROOT / "ir" / "results" / "classical",
    ROOT / "ir" / "baselines" / "classical",
)
GATE_OPS = {
    "xor", "xnor", "not", "not_free", "and", "nand", "or", "nor",
    "andnot", "mux", "nmux", "oa21", "and3", "nand3", "or3", "nor3",
    "and4", "nand4", "or4", "nor4",
    "maoi1", "moai1", "moai1_feng", "andxor", "maj3",
    "add", "sub", "mul", "neg_free",
}
LINEAR_OPS = {"xor", "xnor", "not", "add", "sub"}
NONLINEAR_OPS = {
    "and", "andnot", "nand", "or", "nor", "and3", "nand3", "or3", "nor3",
    "and4", "nand4", "or4", "nor4",
    "maoi1", "moai1", "moai1_feng", "mux", "nmux", "oa21",
    "andxor", "maj3", "mul",
}
PROGRAM_RE = re.compile(r"^([A-Za-z][A-Za-z0-9_]*) = ([a-z0-9_]+)(?: (.*))?$")


AES_SBOX = [
    0x63, 0x7C, 0x77, 0x7B, 0xF2, 0x6B, 0x6F, 0xC5,
    0x30, 0x01, 0x67, 0x2B, 0xFE, 0xD7, 0xAB, 0x76,
    0xCA, 0x82, 0xC9, 0x7D, 0xFA, 0x59, 0x47, 0xF0,
    0xAD, 0xD4, 0xA2, 0xAF, 0x9C, 0xA4, 0x72, 0xC0,
    0xB7, 0xFD, 0x93, 0x26, 0x36, 0x3F, 0xF7, 0xCC,
    0x34, 0xA5, 0xE5, 0xF1, 0x71, 0xD8, 0x31, 0x15,
    0x04, 0xC7, 0x23, 0xC3, 0x18, 0x96, 0x05, 0x9A,
    0x07, 0x12, 0x80, 0xE2, 0xEB, 0x27, 0xB2, 0x75,
    0x09, 0x83, 0x2C, 0x1A, 0x1B, 0x6E, 0x5A, 0xA0,
    0x52, 0x3B, 0xD6, 0xB3, 0x29, 0xE3, 0x2F, 0x84,
    0x53, 0xD1, 0x00, 0xED, 0x20, 0xFC, 0xB1, 0x5B,
    0x6A, 0xCB, 0xBE, 0x39, 0x4A, 0x4C, 0x58, 0xCF,
    0xD0, 0xEF, 0xAA, 0xFB, 0x43, 0x4D, 0x33, 0x85,
    0x45, 0xF9, 0x02, 0x7F, 0x50, 0x3C, 0x9F, 0xA8,
    0x51, 0xA3, 0x40, 0x8F, 0x92, 0x9D, 0x38, 0xF5,
    0xBC, 0xB6, 0xDA, 0x21, 0x10, 0xFF, 0xF3, 0xD2,
    0xCD, 0x0C, 0x13, 0xEC, 0x5F, 0x97, 0x44, 0x17,
    0xC4, 0xA7, 0x7E, 0x3D, 0x64, 0x5D, 0x19, 0x73,
    0x60, 0x81, 0x4F, 0xDC, 0x22, 0x2A, 0x90, 0x88,
    0x46, 0xEE, 0xB8, 0x14, 0xDE, 0x5E, 0x0B, 0xDB,
    0xE0, 0x32, 0x3A, 0x0A, 0x49, 0x06, 0x24, 0x5C,
    0xC2, 0xD3, 0xAC, 0x62, 0x91, 0x95, 0xE4, 0x79,
    0xE7, 0xC8, 0x37, 0x6D, 0x8D, 0xD5, 0x4E, 0xA9,
    0x6C, 0x56, 0xF4, 0xEA, 0x65, 0x7A, 0xAE, 0x08,
    0xBA, 0x78, 0x25, 0x2E, 0x1C, 0xA6, 0xB4, 0xC6,
    0xE8, 0xDD, 0x74, 0x1F, 0x4B, 0xBD, 0x8B, 0x8A,
    0x70, 0x3E, 0xB5, 0x66, 0x48, 0x03, 0xF6, 0x0E,
    0x61, 0x35, 0x57, 0xB9, 0x86, 0xC1, 0x1D, 0x9E,
    0xE1, 0xF8, 0x98, 0x11, 0x69, 0xD9, 0x8E, 0x94,
    0x9B, 0x1E, 0x87, 0xE9, 0xCE, 0x55, 0x28, 0xDF,
    0x8C, 0xA1, 0x89, 0x0D, 0xBF, 0xE6, 0x42, 0x68,
    0x41, 0x99, 0x2D, 0x0F, 0xB0, 0x54, 0xBB, 0x16,
]

ASCON_SBOX = [
    0x04, 0x0B, 0x1F, 0x14, 0x1A, 0x15, 0x09, 0x02,
    0x1B, 0x05, 0x08, 0x12, 0x1D, 0x03, 0x06, 0x1C,
    0x1E, 0x13, 0x07, 0x0E, 0x00, 0x0D, 0x11, 0x18,
    0x10, 0x0C, 0x01, 0x19, 0x16, 0x0A, 0x0F, 0x17,
]

SM4_SBOX = [
    0xD6, 0x90, 0xE9, 0xFE, 0xCC, 0xE1, 0x3D, 0xB7,
    0x16, 0xB6, 0x14, 0xC2, 0x28, 0xFB, 0x2C, 0x05,
    0x2B, 0x67, 0x9A, 0x76, 0x2A, 0xBE, 0x04, 0xC3,
    0xAA, 0x44, 0x13, 0x26, 0x49, 0x86, 0x06, 0x99,
    0x9C, 0x42, 0x50, 0xF4, 0x91, 0xEF, 0x98, 0x7A,
    0x33, 0x54, 0x0B, 0x43, 0xED, 0xCF, 0xAC, 0x62,
    0xE4, 0xB3, 0x1C, 0xA9, 0xC9, 0x08, 0xE8, 0x95,
    0x80, 0xDF, 0x94, 0xFA, 0x75, 0x8F, 0x3F, 0xA6,
    0x47, 0x07, 0xA7, 0xFC, 0xF3, 0x73, 0x17, 0xBA,
    0x83, 0x59, 0x3C, 0x19, 0xE6, 0x85, 0x4F, 0xA8,
    0x68, 0x6B, 0x81, 0xB2, 0x71, 0x64, 0xDA, 0x8B,
    0xF8, 0xEB, 0x0F, 0x4B, 0x70, 0x56, 0x9D, 0x35,
    0x1E, 0x24, 0x0E, 0x5E, 0x63, 0x58, 0xD1, 0xA2,
    0x25, 0x22, 0x7C, 0x3B, 0x01, 0x21, 0x78, 0x87,
    0xD4, 0x00, 0x46, 0x57, 0x9F, 0xD3, 0x27, 0x52,
    0x4C, 0x36, 0x02, 0xE7, 0xA0, 0xC4, 0xC8, 0x9E,
    0xEA, 0xBF, 0x8A, 0xD2, 0x40, 0xC7, 0x38, 0xB5,
    0xA3, 0xF7, 0xF2, 0xCE, 0xF9, 0x61, 0x15, 0xA1,
    0xE0, 0xAE, 0x5D, 0xA4, 0x9B, 0x34, 0x1A, 0x55,
    0xAD, 0x93, 0x32, 0x30, 0xF5, 0x8C, 0xB1, 0xE3,
    0x1D, 0xF6, 0xE2, 0x2E, 0x82, 0x66, 0xCA, 0x60,
    0xC0, 0x29, 0x23, 0xAB, 0x0D, 0x53, 0x4E, 0x6F,
    0xD5, 0xDB, 0x37, 0x45, 0xDE, 0xFD, 0x8E, 0x2F,
    0x03, 0xFF, 0x6A, 0x72, 0x6D, 0x6C, 0x5B, 0x51,
    0x8D, 0x1B, 0xAF, 0x92, 0xBB, 0xDD, 0xBC, 0x7F,
    0x11, 0xD9, 0x5C, 0x41, 0x1F, 0x10, 0x5A, 0xD8,
    0x0A, 0xC1, 0x31, 0x88, 0xA5, 0xCD, 0x7B, 0xBD,
    0x2D, 0x74, 0xD0, 0x12, 0xB8, 0xE5, 0xB4, 0xB0,
    0x89, 0x69, 0x97, 0x4A, 0x0C, 0x96, 0x77, 0x7E,
    0x65, 0xB9, 0xF1, 0x09, 0xC5, 0x6E, 0xC6, 0x84,
    0x18, 0xF0, 0x7D, 0xEC, 0x3A, 0xDC, 0x4D, 0x20,
    0x79, 0xEE, 0x5F, 0x3E, 0xD7, 0xCB, 0x39, 0x48,
]


class VerificationError(Exception):
    pass


SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_source_metadata(record: dict[str, Any]) -> str:
    source = record.get("source")
    if not isinstance(source, dict):
        raise VerificationError("source must be an object")
    if "pdf" in source:
        raise VerificationError("source must not contain an out-of-repository PDF path")
    digest = source.get("sha256")
    locator = source.get("locator")
    pages = source.get("pages")
    if not isinstance(digest, str) or SHA256_RE.fullmatch(digest) is None:
        raise VerificationError("source.sha256 must be a lowercase SHA-256 digest")
    if not isinstance(locator, str) or not locator:
        raise VerificationError("source.locator must be a nonempty evidence locator")
    if not isinstance(pages, list) or not pages or any(
        not isinstance(page, int) or page <= 0 for page in pages
    ):
        raise VerificationError("source.pages must contain positive page numbers")
    return digest


def parse_program(lines: list[str]) -> list[tuple[str, str, list[str]]]:
    parsed = []
    defined = {"0", "1"}
    for number, line in enumerate(lines, 1):
        match = PROGRAM_RE.fullmatch(line.strip())
        if not match:
            raise VerificationError(f"program line {number} has invalid syntax: {line!r}")
        out, op, arg_text = match.groups()
        args = [] if arg_text is None else arg_text.split()
        if out in defined:
            raise VerificationError(f"program line {number} redefines {out}")
        if op == "alias" and len(args) != 1:
            raise VerificationError(f"program line {number}: alias needs one argument")
        if op in {"not", "not_free", "neg_free"} and len(args) != 1:
            raise VerificationError(f"program line {number}: {op} needs one argument")
        if op in {"xor", "xnor"} and len(args) < 2:
            raise VerificationError(f"program line {number}: {op} needs at least two arguments")
        if op in {"and", "andnot", "nand", "or", "nor"} and len(args) != 2:
            raise VerificationError(f"program line {number}: {op} needs two arguments")
        if op in {"add", "sub", "mul"} and len(args) != 2:
            raise VerificationError(f"program line {number}: {op} needs two arguments")
        if op in {"mux", "nmux", "oa21", "andxor", "maj3"} and len(args) != 3:
            raise VerificationError(f"program line {number}: {op} needs three arguments")
        if op in {"and3", "nand3", "or3", "nor3"} and len(args) != 3:
            raise VerificationError(f"program line {number}: {op} needs three arguments")
        if op in {"and4", "nand4", "or4", "nor4"} and len(args) != 4:
            raise VerificationError(f"program line {number}: {op} needs four arguments")
        if op in {"maoi1", "moai1", "moai1_feng"} and len(args) != 4:
            raise VerificationError(f"program line {number}: {op} needs four arguments")
        if op not in GATE_OPS | {"alias"}:
            raise VerificationError(f"program line {number}: unsupported operation {op}")
        parsed.append((out, op, args))
        defined.add(out)
    return parsed


def bit_position(index: int, width: int, order: str) -> int:
    if order == "lsb0":
        return index
    if order == "msb0":
        return width - 1 - index
    raise VerificationError(f"unsupported bit order {order!r}")


def gf_mul(a: int, b: int, modulus: int, degree: int) -> int:
    result = 0
    top = 1 << degree
    mask = top - 1
    while b:
        if b & 1:
            result ^= a
        b >>= 1
        a <<= 1
        if a & top:
            a ^= modulus
    return result & mask


def polynomial_mod(dividend: int, divisor: int) -> int:
    if divisor <= 0:
        raise VerificationError("polynomial divisor must be positive")
    divisor_degree = divisor.bit_length() - 1
    while dividend and dividend.bit_length() - 1 >= divisor_degree:
        dividend ^= divisor << (dividend.bit_length() - 1 - divisor_degree)
    return dividend


def is_irreducible(modulus: int, degree: int) -> bool:
    if modulus.bit_length() != degree + 1 or not (modulus & 1):
        return False
    for factor_degree in range(1, degree // 2 + 1):
        for lower_terms in range(1, 1 << factor_degree, 2):
            factor = (1 << factor_degree) | lower_terms
            if polynomial_mod(modulus, factor) == 0:
                return False
    return True


def gf_pow(value: int, exponent: int, modulus: int, degree: int) -> int:
    result = 1
    base = value
    while exponent:
        if exponent & 1:
            result = gf_mul(result, base, modulus, degree)
        base = gf_mul(base, base, modulus, degree)
        exponent >>= 1
    return result


def gf_pow_alpha(exponent: int, modulus: int, degree: int) -> int:
    order = (1 << degree) - 1
    exponent %= order
    result = 1
    alpha = 2
    for _ in range(exponent):
        result = gf_mul(result, alpha, modulus, degree)
    return result


def matrix_identity(size: int) -> list[int]:
    return [1 << i for i in range(size)]


def matrix_mul(a: list[int], b: list[int], size: int) -> list[int]:
    result = []
    for a_row in a:
        row = 0
        for index in range(size):
            if (a_row >> index) & 1:
                row ^= b[index]
        result.append(row)
    return result


def matrix_inverse(rows: list[int], size: int) -> list[int]:
    work = [rows[i] | (1 << (size + i)) for i in range(size)]
    for column in range(size):
        pivot = next((r for r in range(column, size) if (work[r] >> column) & 1), None)
        if pivot is None:
            raise VerificationError("target base matrix is singular")
        work[column], work[pivot] = work[pivot], work[column]
        for row in range(size):
            if row != column and ((work[row] >> column) & 1):
                work[row] ^= work[column]
    mask = (1 << size) - 1
    return [(row >> size) & mask for row in work]


def matrix_power(base: list[int], exponent: int, size: int) -> list[int]:
    if exponent < 0:
        base = matrix_inverse(base, size)
        exponent = -exponent
    result = matrix_identity(size)
    while exponent:
        if exponent & 1:
            result = matrix_mul(base, result, size)
        base = matrix_mul(base, base, size)
        exponent >>= 1
    return result


def build_field_matrix(target: dict[str, Any]) -> tuple[list[int], int, int]:
    degree = int(target["degree"])
    modulus = int(str(target["modulus"]), 0)
    coefficients = target["coefficients"]
    bit_order = target.get("word_bit_order", "lsb0")
    blocks = len(coefficients)
    rows = [0] * (degree * blocks)
    for block_row, coefficient_row in enumerate(coefficients):
        if len(coefficient_row) != blocks:
            raise VerificationError("field matrix is not square")
        for block_col, coefficient in enumerate(coefficient_row):
            if isinstance(coefficient, str) and coefficient.startswith("a^"):
                value = gf_pow_alpha(int(coefficient[2:]), modulus, degree)
            else:
                value = int(str(coefficient), 0)
            for input_bit_ir in range(degree):
                input_bit_poly = bit_position(input_bit_ir, degree, bit_order)
                product = gf_mul(value, 1 << input_bit_poly, modulus, degree)
                for output_bit_ir in range(degree):
                    output_bit_poly = bit_position(output_bit_ir, degree, bit_order)
                    if (product >> output_bit_poly) & 1:
                        rows[block_row * degree + output_bit_ir] |= (
                            1 << (block_col * degree + input_bit_ir)
                        )
    return rows, degree, blocks


def build_block_power_matrix(target: dict[str, Any]) -> tuple[list[int], int, int]:
    block_size = int(target["block_size"])
    base = [int(str(value), 0) for value in target["base_rows"]]
    if len(base) != block_size:
        raise VerificationError("base_rows length does not match block_size")
    entries = target["entries"]
    blocks = len(entries)
    powers: dict[int, list[int]] = {}

    def get_power(exponent: int) -> list[int]:
        if exponent not in powers:
            powers[exponent] = matrix_power(base, exponent, block_size)
        return powers[exponent]

    rows = [0] * (block_size * blocks)
    for block_row, entry_row in enumerate(entries):
        if len(entry_row) != blocks:
            raise VerificationError("block matrix is not square")
        for block_col, exponent_list in enumerate(entry_row):
            if isinstance(exponent_list, int):
                exponent_list = [exponent_list]
            block = [0] * block_size
            for exponent in exponent_list:
                power = get_power(int(exponent))
                block = [a ^ b for a, b in zip(block, power)]
            for bit, row in enumerate(block):
                rows[block_row * block_size + bit] |= row << (block_col * block_size)
    return rows, block_size, blocks


def target_linear_rows(target: dict[str, Any]) -> tuple[list[int], int | None, int | None]:
    kind = target["kind"]
    if kind == "aes_mixcolumns":
        materialized = {
            "kind": "gf2m_matrix",
            "degree": 8,
            "modulus": "0x11b",
            "word_bit_order": target.get("word_bit_order", "lsb0"),
            "coefficients": [
                [2, 3, 1, 1],
                [1, 2, 3, 1],
                [1, 1, 2, 3],
                [3, 1, 1, 2],
            ],
        }
        return build_field_matrix(materialized)
    if kind == "gf2m_matrix":
        return build_field_matrix(target)
    if kind == "block_power_matrix":
        return build_block_power_matrix(target)
    if kind == "binary_matrix":
        block_size = target.get("block_size")
        blocks = target.get("blocks")
        if (block_size is None) != (blocks is None):
            raise VerificationError(
                "binary_matrix target must provide both block_size and blocks"
            )
        if block_size is not None:
            block_size = int(block_size)
            blocks = int(blocks)
            if block_size <= 0 or blocks <= 0:
                raise VerificationError(
                    "binary_matrix block dimensions must be positive"
                )
        return [int(str(value), 0) for value in target["rows"]], block_size, blocks
    raise VerificationError(f"unsupported linear target kind {kind!r}")


def gf2_rank(rows: list[int], columns: int) -> int:
    work = rows[:]
    rank = 0
    for column in range(columns):
        pivot = next((r for r in range(rank, len(work)) if (work[r] >> column) & 1), None)
        if pivot is None:
            continue
        work[rank], work[pivot] = work[pivot], work[rank]
        for row in range(len(work)):
            if row != rank and ((work[row] >> column) & 1):
                work[row] ^= work[rank]
        rank += 1
    return rank


def combinations(values: list[int], choose: int):
    if choose == 0:
        yield ()
        return
    if len(values) < choose:
        return
    first, rest = values[0], values[1:]
    for suffix in combinations(rest, choose - 1):
        yield (first,) + suffix
    yield from combinations(rest, choose)


def verify_mds(rows: list[int], block_size: int, blocks: int) -> None:
    block_indices = list(range(blocks))
    for size in range(1, blocks + 1):
        for selected_rows in combinations(block_indices, size):
            for selected_cols in combinations(block_indices, size):
                minor_rows = []
                for block_row in selected_rows:
                    for bit_row in range(block_size):
                        source = rows[block_row * block_size + bit_row]
                        packed = 0
                        for packed_col, block_col in enumerate(selected_cols):
                            block = (source >> (block_col * block_size)) & ((1 << block_size) - 1)
                            packed |= block << (packed_col * block_size)
                        minor_rows.append(packed)
                dimension = size * block_size
                if gf2_rank(minor_rows, dimension) != dimension:
                    raise VerificationError(
                        f"target is not MDS: singular {size}x{size} block minor "
                        f"rows={selected_rows}, cols={selected_cols}"
                    )


def is_prime_integer(value: int) -> bool:
    if value < 2:
        return False
    if value % 2 == 0:
        return value == 2
    divisor = 3
    while divisor * divisor <= value:
        if value % divisor == 0:
            return False
        divisor += 2
    return True


def prime_field_rank(rows: list[list[int]], columns: int, modulus: int) -> int:
    work = [[entry % modulus for entry in row] for row in rows]
    if any(len(row) != columns for row in work):
        raise VerificationError("prime-field matrix has inconsistent row widths")
    rank = 0
    for column in range(columns):
        pivot = next(
            (row for row in range(rank, len(work)) if work[row][column]),
            None,
        )
        if pivot is None:
            continue
        work[rank], work[pivot] = work[pivot], work[rank]
        inverse = pow(work[rank][column], -1, modulus)
        work[rank] = [(entry * inverse) % modulus for entry in work[rank]]
        for row in range(len(work)):
            if row == rank or not work[row][column]:
                continue
            factor = work[row][column]
            work[row] = [
                (left - factor * right) % modulus
                for left, right in zip(work[row], work[rank])
            ]
        rank += 1
    return rank


def build_prime_field_rotadd_target(
    target: dict[str, Any],
) -> tuple[list[list[int]], int, int, int]:
    modulus = int(target["modulus"])
    block_size = int(target["block_size"])
    blocks = int(target["blocks"])
    if not is_prime_integer(modulus):
        raise VerificationError("prime-field target modulus must be prime")
    if block_size <= 0 or blocks <= 0:
        raise VerificationError("prime-field block dimensions must be positive")
    if target.get("rotation_direction") != "left":
        raise VerificationError("prime-field RotAdd verifier requires left rotations")
    positive = [int(value) for value in target["positive_rotations"]]
    negative = [int(value) for value in target["negative_rotations"]]
    width = block_size * blocks
    if len(set(positive)) != len(positive) or len(set(negative)) != len(negative):
        raise VerificationError("prime-field RotAdd target contains duplicate rotations")
    if set(positive) & set(negative):
        raise VerificationError("positive and negative RotAdd rotations must be disjoint")
    if any(value < 0 or value >= width for value in positive + negative):
        raise VerificationError("prime-field RotAdd rotation is outside the state width")

    matrix = [[0] * width for _ in range(width)]
    for output in range(width):
        for rotation in positive:
            source = (output + rotation) % width
            matrix[output][source] = (matrix[output][source] + 1) % modulus
        for rotation in negative:
            source = (output + rotation) % width
            matrix[output][source] = (matrix[output][source] - 1) % modulus
    return matrix, modulus, block_size, blocks


def verify_prime_field_mds(
    matrix: list[list[int]], block_size: int, blocks: int, modulus: int
) -> None:
    block_indices = list(range(blocks))
    for size in range(1, blocks + 1):
        for selected_rows in combinations(block_indices, size):
            for selected_cols in combinations(block_indices, size):
                minor = []
                for block_row in selected_rows:
                    for row_offset in range(block_size):
                        row = []
                        source = matrix[block_row * block_size + row_offset]
                        for block_col in selected_cols:
                            start = block_col * block_size
                            row.extend(source[start : start + block_size])
                        minor.append(row)
                dimension = size * block_size
                if prime_field_rank(minor, dimension, modulus) != dimension:
                    raise VerificationError(
                        f"prime-field target is not MDS: singular {size}x{size} "
                        f"block minor rows={selected_rows}, cols={selected_cols}"
                    )


def verify_involutory(rows: list[int]) -> None:
    size = len(rows)
    if matrix_mul(rows, rows, size) != matrix_identity(size):
        raise VerificationError("target matrix is not involutory")


def apply_truth_op(op: str, args: list[int], mask: int) -> int:
    if op == "alias":
        return args[0]
    if op == "xor":
        result = 0
        for arg in args:
            result ^= arg
        return result
    if op == "xnor":
        result = 0
        for arg in args:
            result ^= arg
        return result ^ mask
    if op in {"not", "not_free"}:
        return args[0] ^ mask
    if op == "and":
        return args[0] & args[1]
    if op == "andnot":
        return args[0] & (args[1] ^ mask)
    if op == "nand":
        return (args[0] & args[1]) ^ mask
    if op == "or":
        return args[0] | args[1]
    if op == "nor":
        return (args[0] | args[1]) ^ mask
    if op in {"mux", "nmux"}:
        result = (args[0] & args[1]) | ((args[0] ^ mask) & args[2])
        return result if op == "mux" else result ^ mask
    if op == "oa21":
        return ((args[0] | args[1]) & args[2]) ^ mask
    if op == "andxor":
        return (args[0] & args[1]) ^ args[2]
    if op == "maj3":
        return (args[0] & args[1]) | (args[0] & args[2]) | (args[1] & args[2])
    if op == "and3":
        return args[0] & args[1] & args[2]
    if op == "nand3":
        return (args[0] & args[1] & args[2]) ^ mask
    if op == "or3":
        return args[0] | args[1] | args[2]
    if op == "nor3":
        return (args[0] | args[1] | args[2]) ^ mask
    if op == "and4":
        return args[0] & args[1] & args[2] & args[3]
    if op == "nand4":
        return (args[0] & args[1] & args[2] & args[3]) ^ mask
    if op == "or4":
        return args[0] | args[1] | args[2] | args[3]
    if op == "nor4":
        return (args[0] | args[1] | args[2] | args[3]) ^ mask
    if op == "maoi1":
        return ((args[0] & args[1]) | ((args[2] | args[3]) ^ mask)) ^ mask
    if op == "moai1":
        return ((args[0] | args[1]) & ((args[2] & args[3]) ^ mask)) ^ mask
    if op == "moai1_feng":
        return (((args[0] & args[1]) ^ mask) & (args[2] | args[3])) ^ mask
    raise VerificationError(f"unsupported truth operation {op}")


def verify_lookup(
    record: dict[str, Any], program: list[tuple[str, str, list[str]]]
) -> None:
    inputs = record["interface"]["inputs"]
    outputs = record["interface"]["outputs"]
    width = len(inputs)
    kind = record["target"]["kind"]
    width_limit = (
        16
        if kind in {
            "gf2m_normal_basis_multiply",
            "multi_output_subset_operator",
            "unsigned_addition",
        }
        else 12
    )
    if width > width_limit:
        raise VerificationError(
            f"truth-table verification for {kind!r} is limited to {width_limit} inputs"
        )
    assignments = 1 << width
    truth_mask = (1 << assignments) - 1
    input_order = record["target"].get("input_bit_order", "msb0")
    output_order = record["target"].get("output_bit_order", "msb0")
    values = {"0": 0, "1": truth_mask}
    for input_index, name in enumerate(inputs):
        logical_bit = bit_position(input_index, width, input_order)
        plane = 0
        for value in range(assignments):
            if (value >> logical_bit) & 1:
                plane |= 1 << value
        values[name] = plane
    for out, op, args in program:
        try:
            arg_values = [values[arg] for arg in args]
        except KeyError as error:
            raise VerificationError(f"{out} uses undefined signal {error.args[0]}") from error
        values[out] = apply_truth_op(op, arg_values, truth_mask)

    if kind == "aes_sbox":
        expected = AES_SBOX
    elif kind == "aes_combined_sbox":
        target = record["target"]
        selector_input = target.get("selector_input")
        data_inputs = target.get("data_inputs")
        if width != 9 or len(outputs) != 8:
            raise VerificationError(
                "combined AES S-box needs one selector, eight data inputs, and eight outputs"
            )
        if selector_input not in inputs:
            raise VerificationError("combined AES S-box selector is not an interface input")
        if (
            not isinstance(data_inputs, list)
            or len(data_inputs) != 8
            or len(set(data_inputs)) != 8
            or set(data_inputs) != set(inputs) - {selector_input}
        ):
            raise VerificationError(
                "combined AES S-box data_inputs must contain the other eight inputs exactly once"
            )
        if target.get("selector_one") != "forward" or target.get("selector_zero") != "inverse":
            raise VerificationError(
                "combined AES S-box currently requires selector 1=forward and 0=inverse"
            )
        inverse = [0] * 256
        for value, image in enumerate(AES_SBOX):
            inverse[image] = value
        input_positions = {
            name: bit_position(index, width, input_order)
            for index, name in enumerate(inputs)
        }
        expected = []
        for assignment in range(assignments):
            data = 0
            for data_index, name in enumerate(data_inputs):
                logical_bit = bit_position(data_index, len(data_inputs), "msb0")
                data |= ((assignment >> input_positions[name]) & 1) << logical_bit
            selector = (assignment >> input_positions[selector_input]) & 1
            expected.append(AES_SBOX[data] if selector else inverse[data])
    elif kind == "ascon_sbox":
        expected = ASCON_SBOX
    elif kind == "gf2m_power":
        degree = int(record["target"]["degree"])
        if degree != width:
            raise VerificationError("GF(2^m) power target degree does not match input width")
        modulus = int(str(record["target"]["modulus"]), 0)
        exponent = int(record["target"]["exponent"])
        if not is_irreducible(modulus, degree):
            raise VerificationError("GF(2^m) power target modulus is not irreducible")
        if exponent < 0:
            raise VerificationError("GF(2^m) power target exponent must be nonnegative")
        expected = [gf_pow(value, exponent, modulus, degree) for value in range(assignments)]
    elif kind == "lookup_table":
        expected = [int(str(value), 0) for value in record["target"]["table"]]
    elif kind == "gf2m_normal_basis_multiply":
        target = record["target"]
        degree = int(target["degree"])
        if width != 2 * degree or len(outputs) != degree:
            raise VerificationError(
                "normal-basis multiplication needs 2m inputs and m outputs"
            )
        modulus = int(str(target["modulus"]), 0)
        normal_element = int(str(target["normal_element"]), 0)
        if not is_irreducible(modulus, degree):
            raise VerificationError("normal-basis target modulus is not irreducible")
        if normal_element <= 0 or normal_element >= 1 << degree:
            raise VerificationError("normal-basis generator is outside the field")

        left_inputs = target["left_inputs"]
        right_inputs = target["right_inputs"]
        if len(left_inputs) != degree or len(right_inputs) != degree:
            raise VerificationError("normal-basis input groups must each have m signals")
        if set(left_inputs + right_inputs) != set(inputs):
            raise VerificationError(
                "normal-basis input groups do not partition the circuit inputs"
            )

        basis = []
        element = normal_element
        for _ in range(degree):
            basis.append(element)
            element = gf_mul(element, element, modulus, degree)
        basis_rows = []
        for polynomial_bit in range(degree):
            row = 0
            for coordinate_bit, basis_element in enumerate(basis):
                if (basis_element >> polynomial_bit) & 1:
                    row |= 1 << coordinate_bit
            basis_rows.append(row)
        if gf2_rank(basis_rows, degree) != degree:
            raise VerificationError("declared generator does not produce a normal basis")
        inverse_rows = matrix_inverse(basis_rows, degree)

        def coordinates_to_polynomial(coordinates: int) -> int:
            value = 0
            for coordinate_bit, basis_element in enumerate(basis):
                if (coordinates >> coordinate_bit) & 1:
                    value ^= basis_element
            return value

        def polynomial_to_coordinates(value: int) -> int:
            coordinates = 0
            for coordinate_bit, inverse_row in enumerate(inverse_rows):
                parity = bin(inverse_row & value).count("1") & 1
                coordinates |= parity << coordinate_bit
            return coordinates

        input_positions = {
            name: bit_position(index, width, input_order)
            for index, name in enumerate(inputs)
        }
        expected = []
        for assignment in range(assignments):
            left = sum(
                ((assignment >> input_positions[name]) & 1) << bit
                for bit, name in enumerate(left_inputs)
            )
            right = sum(
                ((assignment >> input_positions[name]) & 1) << bit
                for bit, name in enumerate(right_inputs)
            )
            product = gf_mul(
                coordinates_to_polynomial(left),
                coordinates_to_polynomial(right),
                modulus,
                degree,
            )
            expected.append(polynomial_to_coordinates(product))
    elif kind == "multi_output_subset_operator":
        target = record["target"]
        operator = target.get("operator")
        if operator not in {"and", "or", "xor"}:
            raise VerificationError(
                f"unsupported subset operator {operator!r}"
            )
        output_subsets = target.get("output_subsets")
        if not isinstance(output_subsets, dict) or set(output_subsets) != set(outputs):
            raise VerificationError(
                "subset-operator target must define every circuit output exactly once"
            )
        input_positions = {
            name: bit_position(index, width, input_order)
            for index, name in enumerate(inputs)
        }
        for output, subset in output_subsets.items():
            if not isinstance(subset, list) or not subset:
                raise VerificationError(f"output subset {output!r} must be nonempty")
            if len(subset) != len(set(subset)) or not set(subset) <= set(inputs):
                raise VerificationError(
                    f"output subset {output!r} contains duplicate or unknown inputs"
                )
        expected = []
        for assignment in range(assignments):
            result = 0
            for output_index, output in enumerate(outputs):
                bits = [
                    (assignment >> input_positions[name]) & 1
                    for name in output_subsets[output]
                ]
                if operator == "and":
                    bit = int(all(bits))
                elif operator == "or":
                    bit = int(any(bits))
                else:
                    bit = sum(bits) & 1
                logical_bit = bit_position(output_index, len(outputs), output_order)
                result |= bit << logical_bit
            expected.append(result)
    elif kind == "unsigned_addition":
        target = record["target"]
        operand_width = int(target["operand_width"])
        left_inputs = target["left_inputs"]
        right_inputs = target["right_inputs"]
        if width != 2 * operand_width or len(outputs) != operand_width + 1:
            raise VerificationError(
                "unsigned addition needs 2n inputs and n+1 outputs"
            )
        if len(left_inputs) != operand_width or len(right_inputs) != operand_width:
            raise VerificationError(
                "unsigned-addition input groups must each have n signals"
            )
        if set(left_inputs + right_inputs) != set(inputs):
            raise VerificationError(
                "unsigned-addition input groups do not partition the circuit inputs"
            )
        input_positions = {
            name: bit_position(index, width, input_order)
            for index, name in enumerate(inputs)
        }
        expected = []
        for assignment in range(assignments):
            left = sum(
                ((assignment >> input_positions[name]) & 1) << bit
                for bit, name in enumerate(left_inputs)
            )
            right = sum(
                ((assignment >> input_positions[name]) & 1) << bit
                for bit, name in enumerate(right_inputs)
            )
            expected.append(left + right)
    else:
        raise VerificationError(f"unsupported lookup target kind {kind!r}")
    if len(expected) != assignments:
        raise VerificationError("lookup target has the wrong table length")
    for value in range(assignments):
        actual = 0
        for output_index, name in enumerate(outputs):
            if name not in values:
                raise VerificationError(f"missing output signal {name}")
            logical_bit = bit_position(output_index, len(outputs), output_order)
            actual |= ((values[name] >> value) & 1) << logical_bit
        if actual != expected[value]:
            raise VerificationError(
                f"truth-table mismatch at input 0x{value:x}: "
                f"got 0x{actual:x}, expected 0x{expected[value]:x}"
            )


def anf_xor(*values: frozenset[int]) -> frozenset[int]:
    result: set[int] = set()
    for value in values:
        result.symmetric_difference_update(value)
    return frozenset(result)


def anf_and(left: frozenset[int], right: frozenset[int]) -> frozenset[int]:
    result: set[int] = set()
    for left_monomial in left:
        for right_monomial in right:
            monomial = left_monomial | right_monomial
            if monomial in result:
                result.remove(monomial)
            else:
                result.add(monomial)
    return frozenset(result)


def lookup_bit_anf(
    table: list[int], output_bit_lsb0: int, input_width: int, global_offset: int
) -> frozenset[int]:
    coefficients = [(value >> output_bit_lsb0) & 1 for value in table]
    for bit in range(input_width):
        for mask in range(1 << input_width):
            if (mask >> bit) & 1:
                coefficients[mask] ^= coefficients[mask ^ (1 << bit)]
    monomials: set[int] = set()
    for local_mask, coefficient in enumerate(coefficients):
        if not coefficient:
            continue
        global_mask = 0
        for value_bit_lsb0 in range(input_width):
            if (local_mask >> value_bit_lsb0) & 1:
                input_msb0 = input_width - 1 - value_bit_lsb0
                global_mask |= 1 << (global_offset + input_msb0)
        monomials.add(global_mask)
    return frozenset(monomials)


def verify_ascon_sbox_diffusion(
    record: dict[str, Any], program: list[tuple[str, str, list[str]]]
) -> None:
    inputs = record["interface"]["inputs"]
    outputs = record["interface"]["outputs"]
    target = record["target"]
    word_size = target.get("word_size")
    rotations = target.get("rotations")
    input_words = target.get("input_words")
    output_words = target.get("output_words")
    expected_rotations = [[19, 28], [61, 39], [1, 6], [10, 17], [7, 41]]
    if word_size != 64 or rotations != expected_rotations:
        raise VerificationError(
            "Ascon substitution-diffusion verifier requires the SP 800-232 rotations"
        )
    if target.get("boundary") != "pL_after_pS" or target.get("bit_indexing") != "lsb0":
        raise VerificationError(
            "Ascon substitution-diffusion verifier requires pL_after_pS and lsb0 bits"
        )
    if (
        not isinstance(input_words, list)
        or not isinstance(output_words, list)
        or len(input_words) != 5
        or len(output_words) != 5
        or any(len(word) != word_size for word in input_words + output_words)
    ):
        raise VerificationError("Ascon target needs five 64-bit input and output words")
    flat_inputs = [name for word in input_words for name in word]
    flat_outputs = [name for word in output_words for name in word]
    if flat_inputs != inputs or flat_outputs != outputs:
        raise VerificationError(
            "Ascon input_words/output_words must match the interface in word-major order"
        )

    values: dict[str, frozenset[int]] = {
        "0": frozenset(),
        "1": frozenset({0}),
    }
    for index, name in enumerate(inputs):
        values[name] = frozenset({1 << index})
    constant = frozenset({0})
    for out, op, args in program:
        try:
            arguments = [values[arg] for arg in args]
        except KeyError as error:
            raise VerificationError(f"{out} uses undefined signal {error.args[0]}") from error
        if op == "alias":
            result = arguments[0]
        elif op == "xor":
            result = anf_xor(*arguments)
        elif op == "xnor":
            result = anf_xor(*arguments, constant)
        elif op in {"not", "not_free"}:
            result = anf_xor(arguments[0], constant)
        elif op == "and":
            result = anf_and(arguments[0], arguments[1])
        elif op == "nand":
            result = anf_xor(anf_and(arguments[0], arguments[1]), constant)
        elif op == "or":
            result = anf_xor(
                arguments[0], arguments[1], anf_and(arguments[0], arguments[1])
            )
        elif op == "nor":
            result = anf_xor(
                arguments[0],
                arguments[1],
                anf_and(arguments[0], arguments[1]),
                constant,
            )
        else:
            raise VerificationError(
                "Ascon substitution-diffusion ANF verifier does not support "
                f"operation {op!r}"
            )
        values[out] = result

    local_output_anfs = [
        lookup_bit_anf(ASCON_SBOX, 4 - output_word, 5, 0)
        for output_word in range(5)
    ]
    substituted: list[list[frozenset[int]]] = [[] for _ in range(5)]
    for output_word in range(5):
        for bit in range(word_size):
            lifted: set[int] = set()
            for local_monomial in local_output_anfs[output_word]:
                global_monomial = 0
                for input_word in range(5):
                    if (local_monomial >> input_word) & 1:
                        global_monomial |= 1 << (input_word * word_size + bit)
                lifted.add(global_monomial)
            substituted[output_word].append(frozenset(lifted))

    expected = []
    for word, (first_rotation, second_rotation) in enumerate(expected_rotations):
        for bit in range(word_size):
            expected.append(
                anf_xor(
                    substituted[word][bit],
                    substituted[word][(bit + first_rotation) % word_size],
                    substituted[word][(bit + second_rotation) % word_size],
                )
            )
    actual = []
    for output in outputs:
        if output not in values:
            raise VerificationError(f"missing output signal {output}")
        actual.append(values[output])
    if actual != expected:
        mismatch = next(index for index in range(len(outputs)) if actual[index] != expected[index])
        extra = len(actual[mismatch] - expected[mismatch])
        missing = len(expected[mismatch] - actual[mismatch])
        raise VerificationError(
            f"Ascon pL-after-pS ANF mismatch at output {outputs[mismatch]}: "
            f"extra_monomials={extra}, missing_monomials={missing}"
        )


def verify_sm4_transform(
    record: dict[str, Any], program: list[tuple[str, str, list[str]]]
) -> None:
    inputs = record["interface"]["inputs"]
    outputs = record["interface"]["outputs"]
    target = record["target"]
    if len(inputs) != 32 or len(outputs) != 32:
        raise VerificationError("SM4 transform must have 32 inputs and 32 outputs")
    if target.get("input_bit_order") != "msb0" or target.get("output_bit_order") != "msb0":
        raise VerificationError("SM4 transform verifier requires msb0 input/output order")
    variant = target.get("variant")
    if variant == "T":
        rotations = (0, 2, 10, 18, 24)
    elif variant == "Tprime":
        rotations = (0, 13, 23)
    else:
        raise VerificationError(f"unsupported SM4 transform variant {variant!r}")

    values: dict[str, frozenset[int]] = {
        "0": frozenset(),
        "1": frozenset({0}),
    }
    for index, name in enumerate(inputs):
        values[name] = frozenset({1 << index})
    constant = frozenset({0})
    for out, op, args in program:
        try:
            arguments = [values[arg] for arg in args]
        except KeyError as error:
            raise VerificationError(f"{out} uses undefined signal {error.args[0]}") from error
        if op == "alias":
            result = arguments[0]
        elif op == "xor":
            result = anf_xor(*arguments)
        elif op == "xnor":
            result = anf_xor(*arguments, constant)
        elif op == "not" or op == "not_free":
            result = anf_xor(arguments[0], constant)
        elif op == "and":
            result = anf_and(arguments[0], arguments[1])
        else:
            raise VerificationError(
                f"SM4 algebraic-normal-form verifier does not support operation {op!r}"
            )
        values[out] = result

    substituted: list[frozenset[int]] = []
    for byte in range(4):
        for output_msb0 in range(8):
            substituted.append(
                lookup_bit_anf(SM4_SBOX, 7 - output_msb0, 8, byte * 8)
            )
    expected: list[frozenset[int]] = []
    for output_msb0 in range(32):
        expected.append(
            anf_xor(
                *(substituted[(output_msb0 + rotation) % 32] for rotation in rotations)
            )
        )
    actual = []
    for output in outputs:
        if output not in values:
            raise VerificationError(f"missing output signal {output}")
        actual.append(values[output])
    if actual != expected:
        mismatch = next(index for index in range(32) if actual[index] != expected[index])
        extra = len(actual[mismatch] - expected[mismatch])
        missing = len(expected[mismatch] - actual[mismatch])
        raise VerificationError(
            f"SM4 {variant} ANF mismatch at output {outputs[mismatch]}: "
            f"extra_monomials={extra}, missing_monomials={missing}"
        )


def verify_aes_column_round(
    record: dict[str, Any], program: list[tuple[str, str, list[str]]]
) -> None:
    """Verify an AES S-box/diffusion/key-add column by exact ANF propagation."""

    inputs = record["interface"]["inputs"]
    outputs = record["interface"]["outputs"]
    target = record["target"]
    data_inputs = target.get("data_inputs")
    key_inputs = target.get("key_inputs")
    if len(inputs) != 64 or len(outputs) != 32:
        raise VerificationError("AES column round must have 64 inputs and 32 outputs")
    if data_inputs + key_inputs != inputs or len(data_inputs) != 32 or len(key_inputs) != 32:
        raise VerificationError(
            "AES column target must list 32 data inputs followed by 32 key inputs"
        )
    if target.get("bit_order") != "msb0 within each byte":
        raise VerificationError("AES column verifier requires msb0 byte interfaces")
    direction = target.get("direction")
    if direction == "forward":
        table = AES_SBOX
        coefficients = (
            (2, 3, 1, 1),
            (1, 2, 3, 1),
            (1, 1, 2, 3),
            (3, 1, 1, 2),
        )
    elif direction == "inverse":
        table = [0] * 256
        for value, substituted in enumerate(AES_SBOX):
            table[substituted] = value
        coefficients = (
            (14, 11, 13, 9),
            (9, 14, 11, 13),
            (13, 9, 14, 11),
            (11, 13, 9, 14),
        )
    else:
        raise VerificationError(f"unsupported AES column direction {direction!r}")

    values: dict[str, frozenset[int]] = {
        "0": frozenset(),
        "1": frozenset({0}),
    }
    for index, name in enumerate(inputs):
        values[name] = frozenset({1 << index})
    constant = frozenset({0})
    for out, op, args in program:
        try:
            arguments = [values[arg] for arg in args]
        except KeyError as error:
            raise VerificationError(f"{out} uses undefined signal {error.args[0]}") from error
        if op == "alias":
            result = arguments[0]
        elif op == "xor":
            result = anf_xor(*arguments)
        elif op == "xnor":
            result = anf_xor(*arguments, constant)
        elif op in {"not", "not_free"}:
            result = anf_xor(arguments[0], constant)
        elif op == "and":
            result = anf_and(arguments[0], arguments[1])
        else:
            raise VerificationError(
                f"AES column ANF verifier does not support operation {op!r}"
            )
        values[out] = result

    substituted: list[frozenset[int]] = []
    for byte in range(4):
        for output_msb0 in range(8):
            substituted.append(
                lookup_bit_anf(table, 7 - output_msb0, 8, byte * 8)
            )
    input_positions = {name: index for index, name in enumerate(inputs)}
    expected: list[frozenset[int]] = []
    for output_byte in range(4):
        for output_msb0 in range(8):
            output_polynomial_bit = 7 - output_msb0
            terms: list[frozenset[int]] = []
            for input_byte in range(4):
                coefficient = coefficients[output_byte][input_byte]
                for input_msb0 in range(8):
                    product = gf_mul(
                        coefficient, 1 << (7 - input_msb0), 0x11B, 8
                    )
                    if (product >> output_polynomial_bit) & 1:
                        terms.append(substituted[input_byte * 8 + input_msb0])
            key_index = output_byte * 8 + output_msb0
            terms.append(
                frozenset({1 << input_positions[key_inputs[key_index]]})
            )
            expected.append(anf_xor(*terms))
    actual = []
    for output in outputs:
        if output not in values:
            raise VerificationError(f"missing output signal {output}")
        actual.append(values[output])
    if actual != expected:
        mismatch = next(index for index in range(32) if actual[index] != expected[index])
        extra = len(actual[mismatch] - expected[mismatch])
        missing = len(expected[mismatch] - actual[mismatch])
        raise VerificationError(
            f"AES {direction} column ANF mismatch at output {outputs[mismatch]}: "
            f"extra_monomials={extra}, missing_monomials={missing}"
        )


def verify_linear(
    record: dict[str, Any], program: list[tuple[str, str, list[str]]]
) -> tuple[list[int], int | None, int | None]:
    inputs = record["interface"]["inputs"]
    outputs = record["interface"]["outputs"]
    values = {"0": 0, "1": 0}
    constants = {"0": 0, "1": 1}
    for index, name in enumerate(inputs):
        values[name] = 1 << index
        constants[name] = 0
    for out, op, args in program:
        if op not in {"xor", "xnor", "not", "not_free", "alias"}:
            raise VerificationError(f"linear record contains nonlinear operation {op}")
        try:
            masks = [values[arg] for arg in args]
            affine = [constants[arg] for arg in args]
        except KeyError as error:
            raise VerificationError(f"{out} uses undefined signal {error.args[0]}") from error
        result = 0
        constant = 0
        for mask, bit in zip(masks, affine):
            result ^= mask
            constant ^= bit
        if op in {"xnor", "not", "not_free"}:
            constant ^= 1
        values[out] = result
        constants[out] = constant
    actual = []
    for output in outputs:
        if output not in values:
            raise VerificationError(f"missing output signal {output}")
        if constants[output]:
            raise VerificationError(f"linear output {output} has an unexpected affine constant")
        actual.append(values[output])
    expected, block_size, blocks = target_linear_rows(record["target"])
    if actual != expected:
        mismatch = next(index for index, pair in enumerate(zip(actual, expected)) if pair[0] != pair[1])
        raise VerificationError(
            f"linear mismatch at output {outputs[mismatch]}: "
            f"got 0x{actual[mismatch]:x}, expected 0x{expected[mismatch]:x}"
        )
    return expected, block_size, blocks


def verify_prime_field_linear(
    record: dict[str, Any], program: list[tuple[str, str, list[str]]]
) -> tuple[list[list[int]], int, int, int]:
    inputs = record["interface"]["inputs"]
    outputs = record["interface"]["outputs"]
    expected, modulus, block_size, blocks = build_prime_field_rotadd_target(
        record["target"]
    )
    width = block_size * blocks
    if len(inputs) != width or len(outputs) != width:
        raise VerificationError("prime-field interface width does not match target blocks")

    zero = [0] * width
    values: dict[str, list[int]] = {"0": zero, "1": zero}
    constants = {"0": 0, "1": 1}
    for index, name in enumerate(inputs):
        basis = [0] * width
        basis[index] = 1
        values[name] = basis
        constants[name] = 0

    allowed = {"alias", "add", "sub", "neg_free"}
    for out, op, args in program:
        if op not in allowed:
            raise VerificationError(
                f"prime-field linear record contains unsupported operation {op}"
            )
        try:
            arguments = [values[arg] for arg in args]
            affine = [constants[arg] for arg in args]
        except KeyError as error:
            raise VerificationError(f"{out} uses undefined signal {error.args[0]}") from error
        if op == "alias":
            values[out] = arguments[0][:]
            constants[out] = affine[0]
        elif op == "neg_free":
            values[out] = [(-entry) % modulus for entry in arguments[0]]
            constants[out] = (-affine[0]) % modulus
        else:
            sign = 1 if op == "add" else -1
            values[out] = [
                (left + sign * right) % modulus
                for left, right in zip(arguments[0], arguments[1])
            ]
            constants[out] = (affine[0] + sign * affine[1]) % modulus

    actual = []
    for output in outputs:
        if output not in values:
            raise VerificationError(f"missing output signal {output}")
        if constants[output]:
            raise VerificationError(
                f"prime-field linear output {output} has an unexpected affine constant"
            )
        actual.append(values[output])
    if actual != expected:
        mismatch = next(
            index for index, pair in enumerate(zip(actual, expected)) if pair[0] != pair[1]
        )
        raise VerificationError(
            f"prime-field linear mismatch at output {outputs[mismatch]}: "
            f"got {actual[mismatch]}, expected {expected[mismatch]}"
        )
    return expected, modulus, block_size, blocks


Polynomial = dict[tuple[str, ...], int]


def normalize_polynomial(polynomial: Polynomial) -> Polynomial:
    return {monomial: coefficient for monomial, coefficient in polynomial.items() if coefficient}


def add_polynomials(left: Polynomial, right: Polynomial, sign: int = 1) -> Polynomial:
    result = dict(left)
    for monomial, coefficient in right.items():
        result[monomial] = result.get(monomial, 0) + sign * coefficient
    return normalize_polynomial(result)


def multiply_polynomials(left: Polynomial, right: Polynomial) -> Polynomial:
    result: Polynomial = {}
    for left_monomial, left_coefficient in left.items():
        for right_monomial, right_coefficient in right.items():
            monomial = left_monomial + right_monomial
            result[monomial] = (
                result.get(monomial, 0) + left_coefficient * right_coefficient
            )
    return normalize_polynomial(result)


def format_polynomial(polynomial: Polynomial) -> str:
    if not polynomial:
        return "0"
    terms = []
    for monomial, coefficient in sorted(polynomial.items()):
        product = "*".join(monomial) if monomial else "1"
        terms.append(f"{coefficient:+d}*{product}")
    return " ".join(terms)


def verify_matrix_multiply(
    record: dict[str, Any], program: list[tuple[str, str, list[str]]]
) -> None:
    """Verify a ring-generic matrix product as a noncommutative polynomial identity."""

    target = record["target"]
    rows = int(target["rows"])
    inner = int(target["inner"])
    columns = int(target["columns"])
    if min(rows, inner, columns) <= 0:
        raise VerificationError("matrix dimensions must be positive")
    if target.get("indexing", "row_major") != "row_major":
        raise VerificationError("only row-major matrix indexing is supported")

    left_inputs = target["left_inputs"]
    right_inputs = target["right_inputs"]
    inputs = record["interface"]["inputs"]
    outputs = record["interface"]["outputs"]
    if len(left_inputs) != rows * inner:
        raise VerificationError("left input count does not match matrix dimensions")
    if len(right_inputs) != inner * columns:
        raise VerificationError("right input count does not match matrix dimensions")
    if left_inputs + right_inputs != inputs:
        raise VerificationError(
            "matrix target inputs must exactly match the interface in left/right row-major order"
        )
    if len(outputs) != rows * columns:
        raise VerificationError("output count does not match matrix dimensions")

    values: dict[str, Polynomial] = {
        "0": {},
        "1": {(): 1},
        **{name: {(name,): 1} for name in inputs},
    }
    allowed = {"alias", "add", "sub", "mul", "neg_free"}
    for out, op, args in program:
        if op not in allowed:
            raise VerificationError(
                f"matrix-multiplication record contains unsupported arithmetic operation {op}"
            )
        try:
            arguments = [values[arg] for arg in args]
        except KeyError as error:
            raise VerificationError(f"{out} uses undefined signal {error.args[0]}") from error
        if op == "alias":
            values[out] = dict(arguments[0])
        elif op == "add":
            values[out] = add_polynomials(arguments[0], arguments[1])
        elif op == "sub":
            values[out] = add_polynomials(arguments[0], arguments[1], -1)
        elif op == "mul":
            values[out] = multiply_polynomials(arguments[0], arguments[1])
        else:
            values[out] = {monomial: -coefficient for monomial, coefficient in arguments[0].items()}

    for row in range(rows):
        for column in range(columns):
            output_index = row * columns + column
            output = outputs[output_index]
            if output not in values:
                raise VerificationError(f"missing output signal {output}")
            expected: Polynomial = {}
            for shared in range(inner):
                left = left_inputs[row * inner + shared]
                right = right_inputs[shared * columns + column]
                expected[(left, right)] = expected.get((left, right), 0) + 1
            if values[output] != expected:
                raise VerificationError(
                    f"matrix-product mismatch at output {output}: got "
                    f"{format_polynomial(values[output])}, expected {format_polynomial(expected)}"
                )


def metrics(
    record: dict[str, Any], program: list[tuple[str, str, list[str]]]
) -> dict[str, Any]:
    depth = {name: 0 for name in record["interface"]["inputs"]}
    nonlinear_depth = dict(depth)
    depth.update({"0": 0, "1": 0})
    nonlinear_depth.update({"0": 0, "1": 0})
    counts: Counter[str] = Counter()
    for out, op, args in program:
        try:
            arg_depths = [depth[arg] for arg in args]
            arg_nonlinear_depths = [nonlinear_depth[arg] for arg in args]
        except KeyError as error:
            raise VerificationError(f"{out} uses undefined signal {error.args[0]}") from error
        if op in {"alias", "neg_free"}:
            depth[out] = arg_depths[0]
            nonlinear_depth[out] = arg_nonlinear_depths[0]
            continue
        if op != "not_free":
            counts[op] += 1
            if op in {"xor", "xnor"}:
                counts[f"{op}{len(args)}"] += 1
        depth[out] = 1 + max(arg_depths)
        nonlinear_depth[out] = max(arg_nonlinear_depths) + (1 if op in NONLINEAR_OPS else 0)
    output_depth = max(depth[name] for name in record["interface"]["outputs"])
    output_nonlinear_depth = max(
        nonlinear_depth[name] for name in record["interface"]["outputs"]
    )
    counts["linear"] = sum(counts[op] for op in LINEAR_OPS)
    counts["nonlinear"] = sum(counts[op] for op in NONLINEAR_OPS)
    counts["total"] = counts["linear"] + counts["nonlinear"]
    return {
        "counts": dict(sorted(counts.items())),
        "depth": output_depth,
        "nonlinear_depth": output_nonlinear_depth,
    }


def compare_claims(record: dict[str, Any], measured: dict[str, Any]) -> None:
    claim = record["claim"]
    claimed_counts = claim.get("counts", {})
    for name, expected in claimed_counts.items():
        actual = measured["counts"].get(name, 0)
        if actual != expected:
            raise VerificationError(f"count {name}: got {actual}, claimed {expected}")
    for name in ("depth", "nonlinear_depth"):
        if name in claim and measured[name] != claim[name]:
            raise VerificationError(f"{name}: got {measured[name]}, claimed {claim[name]}")


def verify_optimization(
    record: dict[str, Any],
    program: list[tuple[str, str, list[str]]],
    measured: dict[str, Any],
) -> str | None:
    optimization = record.get("optimization")
    if optimization is None:
        return None
    required = {"goal", "count_metric", "depth_metric", "depth_bound"}
    missing = required - optimization.keys()
    if missing:
        raise VerificationError(f"optimization metadata misses {sorted(missing)}")

    goal = optimization["goal"]
    count_metric = optimization["count_metric"]
    depth_metric = optimization["depth_metric"]
    depth_bound = optimization["depth_bound"]
    if goal not in {"min_and_count_under_depth", "min_xor_count_under_depth"}:
        raise VerificationError(f"unsupported optimization goal {goal!r}")
    if not isinstance(depth_bound, int) or depth_bound < 0:
        raise VerificationError("optimization depth_bound must be a nonnegative integer")
    if depth_metric not in {"depth", "nonlinear_depth"}:
        raise VerificationError(f"unsupported depth metric {depth_metric!r}")
    if measured[depth_metric] > depth_bound:
        raise VerificationError(
            f"optimization bound violated: {depth_metric}={measured[depth_metric]} "
            f"> {depth_bound}"
        )
    if count_metric not in measured["counts"]:
        raise VerificationError(f"count metric {count_metric!r} is absent from measured counts")

    used_ops = {op for _, op, _ in program if op != "alias"}
    if goal == "min_and_count_under_depth":
        if count_metric != "and":
            raise VerificationError("min-AND goal must use count_metric='and'")
        non_and = (used_ops & NONLINEAR_OPS) - {"and"}
        if non_and:
            raise VerificationError(
                f"min-AND XAG record contains other nonlinear gates: {sorted(non_and)}"
            )
    else:
        if not count_metric.startswith("xor"):
            raise VerificationError("min-XOR goal must use an XOR count metric")
        if measured["counts"].get("nonlinear", 0):
            raise VerificationError("min-XOR linear record contains nonlinear gates")
        non_xor_linear = (used_ops & LINEAR_OPS) - {"xor"}
        if non_xor_linear:
            raise VerificationError(
                f"min-XOR record contains other counted linear gates: {sorted(non_xor_linear)}"
            )
    return (
        f"{goal}({count_metric}={measured['counts'][count_metric]},"
        f"{depth_metric}<={depth_bound})"
    )


def verify_cost(
    record: dict[str, Any], program: list[tuple[str, str, list[str]]]
) -> dict[str, Any] | None:
    cost_claim = record["claim"].get("cost")
    if cost_claim is None:
        return None
    model_path = ROOT / cost_claim["model"]
    if not model_path.is_file():
        raise VerificationError(f"cost model does not exist: {model_path}")
    model = json.loads(model_path.read_text(encoding="utf-8"))
    if model.get("schema") != "circuit-cost-model/v1":
        raise VerificationError(f"unsupported cost-model schema in {model_path}")
    model_source = ROOT / model["source"]["pdf"]
    if not model_source.is_file():
        raise VerificationError(f"cost-model source PDF does not exist: {model_source}")
    model_source_hash = sha256(model_source)
    if model_source_hash != model["source"]["sha256"]:
        raise VerificationError(
            f"cost-model source PDF hash mismatch: got {model_source_hash}, "
            f"expected {model['source']['sha256']}"
        )
    costs = model["gate_costs_integer_units"]
    total = 0
    breakdown: Counter[str] = Counter()
    for _, op, args in program:
        if op in {"alias", "not_free"}:
            continue
        fanin_key = f"{op}{len(args)}"
        key = fanin_key if fanin_key in costs else op
        if key not in costs:
            raise VerificationError(
                f"cost model {model['id']} has no price for {op} with fan-in {len(args)}"
            )
        weight = costs[key]
        if not isinstance(weight, int) or weight < 0:
            raise VerificationError(f"cost {key} in {model['id']} is not a nonnegative integer")
        total += weight
        breakdown[key] += weight
    if total != cost_claim["integer_units"]:
        raise VerificationError(
            f"cost integer_units: got {total}, claimed {cost_claim['integer_units']}"
        )
    unit = model["ge_per_integer_unit"]
    numerator = total * int(unit["numerator"])
    denominator = int(unit["denominator"])
    divisor = math.gcd(numerator, denominator)
    numerator //= divisor
    denominator //= divisor
    claimed_ge = cost_claim["ge"]
    claimed_numerator = int(claimed_ge["numerator"])
    claimed_denominator = int(claimed_ge["denominator"])
    if numerator * claimed_denominator != claimed_numerator * denominator:
        raise VerificationError(
            f"GE rational: got {numerator}/{denominator}, "
            f"claimed {claimed_numerator}/{claimed_denominator}"
        )
    return {
        "model": model["id"],
        "integer_units": total,
        "ge": {"numerator": numerator, "denominator": denominator},
        "weighted_breakdown": dict(sorted(breakdown.items())),
    }


def verify_record(path: Path) -> dict[str, Any]:
    record = json.loads(path.read_text(encoding="utf-8"))
    required = {"schema", "id", "source", "interface", "target", "claim", "program"}
    missing = required - record.keys()
    if missing:
        raise VerificationError(f"missing required fields: {sorted(missing)}")
    if record["schema"] != "circuit-ir/v1":
        raise VerificationError(f"unsupported schema {record['schema']!r}")
    if path.stem != record["id"]:
        raise VerificationError("filename does not match record id")

    recorded_source_hash = verify_source_metadata(record)

    inputs = record["interface"]["inputs"]
    outputs = record["interface"]["outputs"]
    if len(inputs) != len(set(inputs)) or len(outputs) != len(set(outputs)):
        raise VerificationError("duplicate interface signal")
    program = parse_program(record["program"])
    measured = metrics(record, program)
    compare_claims(record, measured)
    optimization_property = verify_optimization(record, program, measured)
    measured_cost = verify_cost(record, program)
    if measured_cost is not None:
        measured["cost"] = measured_cost

    kind = record["target"]["kind"]
    if kind in {
        "aes_sbox",
        "aes_combined_sbox",
        "ascon_sbox",
        "gf2m_power",
        "gf2m_normal_basis_multiply",
        "multi_output_subset_operator",
        "unsigned_addition",
        "lookup_table",
    }:
        verify_lookup(record, program)
        target_rows = None
        prime_field_matrix = None
        prime_field_modulus = None
        block_size = blocks = None
    elif kind == "matrix_multiply":
        verify_matrix_multiply(record, program)
        target_rows = None
        prime_field_matrix = None
        prime_field_modulus = None
        block_size = blocks = None
    elif kind == "sm4_transform":
        verify_sm4_transform(record, program)
        target_rows = None
        prime_field_matrix = None
        prime_field_modulus = None
        block_size = blocks = None
    elif kind == "aes_column_round":
        verify_aes_column_round(record, program)
        target_rows = None
        prime_field_matrix = None
        prime_field_modulus = None
        block_size = blocks = None
    elif kind == "ascon_sbox_diffusion":
        verify_ascon_sbox_diffusion(record, program)
        target_rows = None
        prime_field_matrix = None
        prime_field_modulus = None
        block_size = blocks = None
    elif kind == "prime_field_linear_map":
        prime_field_matrix, prime_field_modulus, block_size, blocks = (
            verify_prime_field_linear(record, program)
        )
        target_rows = None
    else:
        target_rows, block_size, blocks = verify_linear(record, program)
        prime_field_matrix = None
        prime_field_modulus = None

    properties = []
    if optimization_property is not None:
        properties.append(optimization_property)
    if record["claim"].get("involutory"):
        if target_rows is None:
            raise VerificationError("involutory claim requires a binary linear target")
        verify_involutory(target_rows)
        properties.append("involutory")
    if "mds_branch_number" in record["claim"]:
        claimed = record["claim"]["mds_branch_number"]
        if block_size is None or blocks is None or claimed != blocks + 1:
            raise VerificationError("unsupported or inconsistent MDS branch-number claim")
        if prime_field_matrix is not None:
            if prime_field_modulus is None:
                raise VerificationError("prime-field MDS target is missing its modulus")
            verify_prime_field_mds(
                prime_field_matrix, block_size, blocks, prime_field_modulus
            )
        else:
            if target_rows is None:
                raise VerificationError("MDS claim requires a linear target")
            verify_mds(target_rows, block_size, blocks)
        properties.append(f"mds_branch_number={claimed}")

    return {
        "id": record["id"],
        "status": "pass",
        "source_sha256": recorded_source_hash,
        "metrics": measured,
        "properties": properties,
        "not_verified": record["claim"].get("not_verified", []),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("paths", nargs="*", type=Path)
    parser.add_argument("--ir-dir", type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    if args.paths:
        paths = args.paths
    elif args.ir_dir is not None:
        paths = sorted(args.ir_dir.glob("*.json"))
    else:
        paths = sorted(path for directory in DEFAULT_IR_DIRS for path in directory.glob("*.json"))
    reports = []
    failures = 0
    for path in paths:
        if not path.is_absolute():
            path = ROOT / path
        try:
            report = verify_record(path)
        except (OSError, ValueError, VerificationError) as error:
            failures += 1
            report = {"id": path.stem, "status": "fail", "error": str(error)}
        reports.append(report)
    summary = {"schema": "circuit-ir-verification/v1", "records": reports}
    if args.json:
        print(json.dumps(summary, indent=2, sort_keys=True))
    else:
        for report in reports:
            if report["status"] == "pass":
                metrics_text = report["metrics"]
                print(
                    f"PASS {report['id']}: counts={metrics_text['counts']} "
                    f"depth={metrics_text['depth']} "
                    f"nonlinear_depth={metrics_text['nonlinear_depth']}"
                )
            else:
                print(f"FAIL {report['id']}: {report['error']}", file=sys.stderr)
        print(f"verified={len(reports) - failures} failed={failures}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
