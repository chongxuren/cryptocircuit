#!/usr/bin/env python3
"""Verify the published logical quantum and reversible circuit IR records.

Several deliberately narrow schema families are supported: fixed 32-qubit AES
MixColumns CNOT circuits, the 26-qubit AES S-box affine-output boundary over
CNOT/X, source-pinned AES/Ascon NCT circuits, source-diagram Ascon NCT
transcriptions, embedded Ascon linear-layer and round-core schedules, the
round-constant-specialized Ascon NCT boundary, and target-specific
repository-derived NCT circuits at pinned source boundaries. The verifier
checks retained in-repository hashes, fixed wire order,
ancilla initialization and cleanup or explicit garbage policy, complete
disjoint-layer schedules when supplied, independently declared basis-state
semantics, and full logical resource vectors. It does not infer device
routing, noise, fidelity, or fault-tolerant cost.
"""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_IR_DIRS = (
    ROOT / "ir" / "results" / "quantum",
    ROOT / "ir" / "baselines" / "quantum",
)
QUBITS = 32
AFFINE_QUBITS = 26
ASCON_WORD_BITS = 64
ASCON_WORD_COUNT = 5
ASCON_STATE_QUBITS = ASCON_WORD_BITS * ASCON_WORD_COUNT
ASCON_LINEAR_COPY_QUBITS = 2 * ASCON_STATE_QUBITS
ASCON_ROTATION_PAIRS = [(19, 28), (61, 39), (1, 6), (10, 17), (7, 41)]
AFFINE_PRODUCT_NAMES = [f"M{index}" for index in range(46, 64)]
AFFINE_OUTPUT_NAMES = [f"s{index}" for index in range(8)]
AFFINE_ROWS = [
    [3, 4, 6, 7, 9, 10, 15, 16],
    [0, 1, 6, 7, 9, 10, 15, 16],
    [0, 2, 6, 8, 12, 14, 15, 17],
    [0, 1, 3, 4, 9, 10, 15, 16],
    [1, 2, 4, 5, 9, 10, 15, 16],
    [0, 2, 3, 4, 7, 8, 10, 11, 12, 14, 15, 16],
    [4, 5, 7, 8, 12, 13, 15, 16],
    [0, 2, 3, 5, 12, 13, 15, 16],
]
AFFINE_CONSTANTS = [1, 2, 6, 7]


class VerificationError(Exception):
    pass


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def xtime(value: int) -> int:
    return (((value << 1) ^ 0x11B) if value & 0x80 else value << 1) & 0xFF


def mixcolumns_word(value: int) -> int:
    inputs = [(value >> (8 * index)) & 0xFF for index in range(4)]
    doubled = [xtime(byte) for byte in inputs]
    tripled = [doubled[index] ^ inputs[index] for index in range(4)]
    outputs = [
        doubled[0] ^ tripled[1] ^ inputs[2] ^ inputs[3],
        inputs[0] ^ doubled[1] ^ tripled[2] ^ inputs[3],
        inputs[0] ^ inputs[1] ^ doubled[2] ^ tripled[3],
        tripled[0] ^ inputs[1] ^ inputs[2] ^ doubled[3],
    ]
    return sum(byte << (8 * index) for index, byte in enumerate(outputs))


def target_rows() -> list[int]:
    rows = [0] * QUBITS
    for input_index in range(QUBITS):
        output = mixcolumns_word(1 << input_index)
        for output_index in range(QUBITS):
            if output & (1 << output_index):
                rows[output_index] |= 1 << input_index
    return rows


def require_equal(actual: Any, expected: Any, label: str) -> None:
    if actual != expected:
        raise VerificationError(f"{label}: expected {expected!r}, got {actual!r}")


def verify_provenance(record: dict[str, Any]) -> None:
    provenance = record.get("provenance")
    if not isinstance(provenance, dict):
        raise VerificationError("provenance must be an object")
    if provenance.get("evidence_status") not in {
        "deterministic-composition-verified",
        "component-composed-verified",
        "source-disclosed-verified",
        "source-derived-verified",
        "repository-derived-verified",
    }:
        raise VerificationError("unsupported evidence status")
    files = provenance.get("files", [])
    if not isinstance(files, list):
        raise VerificationError("provenance.files must be a list")
    for index, entry in enumerate(files):
        if not isinstance(entry, dict):
            raise VerificationError(f"provenance file {index} is not an object")
        relative = entry.get("path")
        expected_hash = entry.get("sha256")
        if not isinstance(relative, str) or not isinstance(expected_hash, str):
            raise VerificationError(f"provenance file {index} needs path and sha256")
        path = ROOT / relative
        if not path.is_file():
            raise VerificationError(f"missing provenance file: {relative}")
        actual_hash = sha256(path)
        if actual_hash != expected_hash:
            raise VerificationError(
                f"provenance hash mismatch for {relative}: {actual_hash} != {expected_hash}"
            )
    excluded = provenance.get("excluded_sources", [])
    if not isinstance(excluded, list):
        raise VerificationError("provenance.excluded_sources must be a list")
    for index, entry in enumerate(excluded):
        if not isinstance(entry, dict):
            raise VerificationError(f"excluded provenance source {index} is not an object")
        locator = entry.get("locator")
        digest = entry.get("sha256")
        if not isinstance(locator, str) or not locator:
            raise VerificationError(f"excluded provenance source {index} needs a locator")
        if not isinstance(digest, str) or re.fullmatch(r"[0-9a-f]{64}", digest) is None:
            raise VerificationError(f"excluded provenance source {index} has invalid SHA-256")
    if not isinstance(provenance.get("evidence_locator"), str):
        raise VerificationError("provenance.evidence_locator must be a string")


def parse_layers(
    raw_layers: Any, qubit_count: int = QUBITS
) -> list[list[tuple[int, int]]]:
    if not isinstance(raw_layers, list) or not raw_layers:
        raise VerificationError("layers must be a nonempty list")
    layers: list[list[tuple[int, int]]] = []
    for layer_index, raw_layer in enumerate(raw_layers):
        if not isinstance(raw_layer, list) or not raw_layer:
            raise VerificationError(f"layer {layer_index} must be nonempty")
        used: set[int] = set()
        layer: list[tuple[int, int]] = []
        for gate_index, raw_gate in enumerate(raw_layer):
            if (
                not isinstance(raw_gate, list)
                or len(raw_gate) != 2
                or any(not isinstance(qubit, int) for qubit in raw_gate)
            ):
                raise VerificationError(
                    f"layer {layer_index} gate {gate_index} is not [control, target]"
                )
            control, target = raw_gate
            if not 0 <= control < qubit_count or not 0 <= target < qubit_count:
                raise VerificationError(f"layer {layer_index} gate {gate_index} is out of range")
            if control == target:
                raise VerificationError(f"layer {layer_index} gate {gate_index} is a self-CNOT")
            if control in used or target in used:
                raise VerificationError(f"layer {layer_index} reuses a qubit")
            used.update((control, target))
            layer.append((control, target))
        layers.append(layer)
    return layers


def circuit_rows(
    layers: list[list[tuple[int, int]]],
    qubit_count: int = QUBITS,
    initialized_input_qubits: int | None = None,
) -> list[int]:
    if initialized_input_qubits is None:
        initialized_input_qubits = qubit_count
    rows = [
        1 << index if index < initialized_input_qubits else 0
        for index in range(qubit_count)
    ]
    for layer in layers:
        before = rows[:]
        for control, target in layer:
            rows[target] = before[target] ^ before[control]
    return rows


def verify_mixcolumns_record(record: dict[str, Any]) -> dict[str, Any]:
    require_equal(record.get("schema"), "quantum-circuit-ir/v1", "schema")
    require_equal(record.get("target"), "aes_mixcolumns_forward_column", "target")
    verify_provenance(record)

    boundary = record.get("boundary")
    if not isinstance(boundary, dict):
        raise VerificationError("boundary must be an object")
    require_equal(boundary.get("operation"), "unitary", "boundary.operation")
    require_equal(boundary.get("basis_semantics"), "forward_aes_mixcolumns", "basis semantics")
    require_equal(boundary.get("input_wires"), list(range(QUBITS)), "input wire order")
    require_equal(boundary.get("output_wires"), list(range(QUBITS)), "output wire order")
    require_equal(boundary.get("byte_order"), ["s0", "s1", "s2", "s3"], "byte order")
    require_equal(boundary.get("bit_order_within_byte"), "lsb0", "bit order")
    require_equal(
        boundary.get("wire_definition"),
        "q[8*j+k] is the coefficient of x^k in byte s[j]",
        "wire definition",
    )
    require_equal(boundary.get("terminal_permutation"), "identity", "terminal permutation")

    model = record.get("model")
    if not isinstance(model, dict):
        raise VerificationError("model must be an object")
    expected_model = {
        "logical_qubits": QUBITS,
        "clean_ancillas": 0,
        "dirty_ancillas": 0,
        "ancilla_final_state": "not_applicable",
        "gate_set": ["CNOT"],
        "connectivity": "all_to_all",
        "measurements": 0,
        "classical_feed_forward": False,
        "compilation_level": "logical_pre_device_mapping",
        "physical_qubits": None,
        "noise_model": None,
        "fault_tolerance_model": None,
    }
    require_equal(model, expected_model, "logical circuit model")

    layers = parse_layers(record.get("layers"))
    actual_rows = circuit_rows(layers)
    expected_rows = target_rows()
    if actual_rows != expected_rows:
        mismatches = [index for index in range(QUBITS) if actual_rows[index] != expected_rows[index]]
        raise VerificationError(f"AES MixColumns matrix mismatch on output rows {mismatches}")

    count = sum(len(layer) for layer in layers)
    depth = len(layers)
    expected_resources = {
        "logical_qubits": QUBITS,
        "physical_qubits": None,
        "clean_ancillas": 0,
        "dirty_ancillas": 0,
        "total_gate_count": count,
        "cnot_count": count,
        "toffoli_count": 0,
        "t_count": 0,
        "total_depth": depth,
        "cnot_depth": depth,
        "toffoli_depth": 0,
        "t_depth": 0,
        "measurement_rounds": 0,
        "classical_control_operations": 0,
        "topology_overhead": None,
    }
    require_equal(record.get("resources"), expected_resources, "resource vector")
    acceptance = record.get("acceptance_bounds")
    if acceptance is not None:
        if not isinstance(acceptance, dict):
            raise VerificationError("acceptance_bounds must be an object")
        if count > acceptance.get("cnot_count_at_most", count):
            raise VerificationError("CNOT count exceeds acceptance bound")
        if depth > acceptance.get("cnot_depth_at_most", depth):
            raise VerificationError("CNOT depth exceeds acceptance bound")
    return {
        "id": record.get("id"),
        "cnot_count": count,
        "cnot_depth": depth,
        "total_logical_depth": depth,
    }


def expected_oh_ascon_linear_copy_layers() -> list[list[tuple[int, int]]]:
    copy_layer: list[tuple[int, int]] = []
    first_rotation_layer: list[tuple[int, int]] = []
    second_rotation_layer: list[tuple[int, int]] = []
    for bit in range(ASCON_WORD_BITS):
        for word, (first_rotation, second_rotation) in enumerate(ASCON_ROTATION_PAIRS):
            state_offset = word * ASCON_WORD_BITS
            copy_offset = ASCON_STATE_QUBITS + state_offset
            copy_layer.append((state_offset + bit, copy_offset + bit))
            first_rotation_layer.append(
                (
                    copy_offset + (bit + first_rotation) % ASCON_WORD_BITS,
                    state_offset + bit,
                )
            )
            second_rotation_layer.append(
                (
                    copy_offset + (bit + second_rotation) % ASCON_WORD_BITS,
                    state_offset + bit,
                )
            )
    return [copy_layer, first_rotation_layer, second_rotation_layer]


def expected_ascon_linear_rows() -> list[int]:
    rows: list[int] = []
    for word, (first_rotation, second_rotation) in enumerate(ASCON_ROTATION_PAIRS):
        offset = word * ASCON_WORD_BITS
        for bit in range(ASCON_WORD_BITS):
            rows.append(
                (1 << (offset + bit))
                ^ (1 << (offset + (bit + first_rotation) % ASCON_WORD_BITS))
                ^ (1 << (offset + (bit + second_rotation) % ASCON_WORD_BITS))
            )
    return rows


def expected_ascon_linear_msb0_rows() -> list[int]:
    rows: list[int] = []
    for word, (first_rotation, second_rotation) in enumerate(ASCON_ROTATION_PAIRS):
        offset = word * ASCON_WORD_BITS
        for bit in range(ASCON_WORD_BITS):
            rows.append(
                (1 << (offset + bit))
                ^ (1 << (offset + (bit - first_rotation) % ASCON_WORD_BITS))
                ^ (1 << (offset + (bit - second_rotation) % ASCON_WORD_BITS))
            )
    return rows


def expected_ascon_linear_copy_rows() -> list[int]:
    return expected_ascon_linear_rows() + [
        1 << index for index in range(ASCON_STATE_QUBITS)
    ]


def verify_ascon_linear_copy_record(record: dict[str, Any]) -> dict[str, Any]:
    require_equal(
        record.get("schema"),
        "quantum-ascon-linear-copy-source-ir/v1",
        "schema",
    )
    require_equal(
        record.get("target"),
        "ascon_linear_layer_with_retained_input_copy",
        "target",
    )
    verify_provenance(record)
    provenance = record["provenance"]
    require_equal(
        provenance.get("source_commit"),
        "126b498b842275311f189d9a6748b2595501fce1",
        "Oh et al. source commit",
    )

    expected_boundary = {
        "operation": "isometry",
        "basis_semantics": "ascon_linear_layer_with_retained_input_copy",
        "input_state_wires": list(range(ASCON_STATE_QUBITS)),
        "zero_initialized_ancilla_wires": list(
            range(ASCON_STATE_QUBITS, ASCON_LINEAR_COPY_QUBITS)
        ),
        "output_state_wires": list(range(ASCON_STATE_QUBITS)),
        "garbage_wires": list(
            range(ASCON_STATE_QUBITS, ASCON_LINEAR_COPY_QUBITS)
        ),
        "garbage_copy_from_input_wires": list(range(ASCON_STATE_QUBITS)),
        "word_order": [f"x{index}" for index in range(ASCON_WORD_COUNT)],
        "bit_order_within_word": "lsb0",
        "wire_definition": "q[64*j+i] is bit i of x[j]; q[320+64*j+i] is its zero-initialized retained-copy wire",
        "rotation_pairs": [list(pair) for pair in ASCON_ROTATION_PAIRS],
        "terminal_state": "q[0:320] = L(x), q[320:640] = x",
        "ancilla_cleanup_policy": "specified_retained_input_copy_garbage",
        "terminal_permutation": "identity",
    }
    require_equal(record.get("boundary"), expected_boundary, "Ascon linear-copy boundary")

    expected_model = {
        "logical_qubits": ASCON_LINEAR_COPY_QUBITS,
        "input_qubits": ASCON_STATE_QUBITS,
        "output_qubits": ASCON_STATE_QUBITS,
        "zero_initialized_ancillas": ASCON_STATE_QUBITS,
        "clean_ancillas_returned_to_zero": 0,
        "dirty_ancillas": 0,
        "garbage_qubits": ASCON_STATE_QUBITS,
        "gate_set": ["CNOT"],
        "connectivity": "all_to_all",
        "measurements": 0,
        "classical_feed_forward": False,
        "compilation_level": "logical_pre_device_mapping",
        "physical_qubits": None,
        "noise_model": None,
        "fault_tolerance_model": None,
    }
    require_equal(record.get("model"), expected_model, "Ascon linear-copy model")

    layers = parse_layers(record.get("layers"), ASCON_LINEAR_COPY_QUBITS)
    require_equal(
        layers,
        expected_oh_ascon_linear_copy_layers(),
        "Oh et al. source schedule",
    )
    actual_rows = circuit_rows(
        layers,
        ASCON_LINEAR_COPY_QUBITS,
        initialized_input_qubits=ASCON_STATE_QUBITS,
    )
    require_equal(
        actual_rows,
        expected_ascon_linear_copy_rows(),
        "Ascon retained-copy isometry",
    )

    count = sum(len(layer) for layer in layers)
    depth = len(layers)
    expected_resources = {
        "logical_qubits": ASCON_LINEAR_COPY_QUBITS,
        "physical_qubits": None,
        "zero_initialized_ancillas": ASCON_STATE_QUBITS,
        "clean_ancillas_returned_to_zero": 0,
        "dirty_ancillas": 0,
        "garbage_qubits": ASCON_STATE_QUBITS,
        "total_gate_count": count,
        "cnot_count": count,
        "toffoli_count": 0,
        "t_count": 0,
        "total_logical_depth": depth,
        "cnot_depth": depth,
        "toffoli_depth": 0,
        "t_depth": 0,
        "measurement_rounds": 0,
        "classical_control_operations": 0,
        "topology_overhead": None,
    }
    require_equal(record.get("resources"), expected_resources, "Ascon linear-copy resources")
    require_equal(record.get("acceptance_bounds"), None, "source acceptance bounds")
    return {
        "id": record.get("id"),
        "cnot_count": count,
        "cnot_depth": depth,
        "total_logical_depth": depth,
    }


def ordered_cnot_depth(gates: list[tuple[int, int]], width: int) -> int:
    depths = [0] * width
    for control, target in gates:
        gate_depth = max(depths[control], depths[target]) + 1
        depths[control] = gate_depth
        depths[target] = gate_depth
    return max(depths, default=0)


def permutation_minimum_transpositions(permutation: list[int]) -> int:
    seen = [False] * len(permutation)
    cycles = 0
    for start in range(len(permutation)):
        if seen[start]:
            continue
        cycles += 1
        current = start
        while not seen[current]:
            seen[current] = True
            current = permutation[current]
    return len(permutation) - cycles


def verify_ascon_linear_embedded_record(record: dict[str, Any]) -> dict[str, Any]:
    """Verify a complete embedded in-place Ascon linear-layer schedule.

    Publication records omit research schedules and search receipts.  The
    retained IR is nevertheless independently checkable because it contains
    the full input placement and every CNOT layer.
    """

    schema = record.get("schema")
    if schema not in {
        "quantum-ascon-linear-inplace-derived-ir/v1",
        "quantum-ascon-linear-inplace-rewrite-ir/v1",
    }:
        raise VerificationError(f"unsupported embedded Ascon linear schema: {schema!r}")
    require_equal(
        record.get("target"),
        "ascon_linear_layer_inplace_free_input_placement",
        "embedded Ascon target",
    )
    verify_provenance(record)

    boundary = record.get("boundary")
    if not isinstance(boundary, dict):
        raise VerificationError("embedded Ascon boundary must be an object")
    placement = boundary.get("logical_input_to_physical_wires")
    if (
        not isinstance(placement, list)
        or len(placement) != ASCON_STATE_QUBITS
        or any(not isinstance(item, int) for item in placement)
        or sorted(placement) != list(range(ASCON_STATE_QUBITS))
    ):
        raise VerificationError("embedded Ascon placement is not a 320-wire permutation")
    expected_boundary = {
        "operation": "unitary",
        "basis_semantics": "ascon_linear_layer_with_declared_free_input_placement",
        "logical_input_to_physical_wires": placement,
        "physical_output_wires": list(range(ASCON_STATE_QUBITS)),
        "word_order": [f"x{index}" for index in range(ASCON_WORD_COUNT)],
        "bit_order_within_word": "msb0",
        "wire_definition": "logical bit 64*j+i is bit i from the MSB of x[j]; physical output wire 64*j+i is bit i from the MSB of Sigma_j(x[j])",
        "rotation_pairs": [list(pair) for pair in ASCON_ROTATION_PAIRS],
        "input_placement_policy": "declared_permutation_free_at_boundary",
        "input_placement_minimum_transpositions_if_materialized": permutation_minimum_transpositions(placement),
        "terminal_output_permutation": "identity",
    }
    require_equal(boundary, expected_boundary, "embedded Ascon boundary")

    expected_model = {
        "logical_qubits": ASCON_STATE_QUBITS,
        "input_qubits": ASCON_STATE_QUBITS,
        "output_qubits": ASCON_STATE_QUBITS,
        "zero_initialized_ancillas": 0,
        "clean_ancillas_returned_to_zero": 0,
        "dirty_ancillas": 0,
        "garbage_qubits": 0,
        "gate_set": ["CNOT"],
        "connectivity": "all_to_all",
        "initial_placement_cost_model": "free_logical_relabeling_at_boundary",
        "swap_gates_in_schedule": 0,
        "measurements": 0,
        "classical_feed_forward": False,
        "compilation_level": "logical_pre_device_mapping",
        "physical_qubits": None,
        "noise_model": None,
        "fault_tolerance_model": None,
    }
    require_equal(record.get("model"), expected_model, "embedded Ascon model")

    schedule = record.get("schedule")
    if not isinstance(schedule, dict):
        raise VerificationError("embedded Ascon schedule must be an object")
    require_equal(set(schedule), {"serialization", "layers"}, "embedded schedule fields")
    require_equal(schedule.get("serialization"), "layer_major", "embedded serialization")
    layers = parse_layers(schedule.get("layers"), ASCON_STATE_QUBITS)
    gates = [gate for layer in layers for gate in layer]
    depth = len(layers)
    require_equal(
        ordered_cnot_depth(gates, ASCON_STATE_QUBITS),
        depth,
        "embedded Ascon canonical depth",
    )
    if any(
        control // ASCON_WORD_BITS != target // ASCON_WORD_BITS
        for control, target in gates
    ):
        raise VerificationError("embedded Ascon schedule contains a cross-word CNOT")

    rows = [0] * ASCON_STATE_QUBITS
    for logical_input, physical_wire in enumerate(placement):
        rows[physical_wire] = 1 << logical_input
    for control, target in gates:
        rows[target] ^= rows[control]
    require_equal(rows, expected_ascon_linear_msb0_rows(), "embedded Ascon matrix")

    component_resources = []
    for word, pair in enumerate(ASCON_ROTATION_PAIRS):
        word_gates = [gate for gate in gates if gate[0] // ASCON_WORD_BITS == word]
        component_resources.append(
            {
                "word": f"x{word}",
                "rotation_pair": list(pair),
                "cnot_count": len(word_gates),
                "cnot_depth": ordered_cnot_depth(word_gates, ASCON_STATE_QUBITS),
            }
        )
    count = len(gates)
    expected_resources = {
        "logical_qubits": ASCON_STATE_QUBITS,
        "physical_qubits": None,
        "zero_initialized_ancillas": 0,
        "clean_ancillas_returned_to_zero": 0,
        "dirty_ancillas": 0,
        "garbage_qubits": 0,
        "total_gate_count": count,
        "cnot_count": count,
        "toffoli_count": 0,
        "t_count": 0,
        "total_logical_depth": depth,
        "cnot_depth": depth,
        "toffoli_depth": 0,
        "t_depth": 0,
        "measurement_rounds": 0,
        "classical_control_operations": 0,
        "topology_overhead": None,
        "component_resources": component_resources,
    }
    require_equal(record.get("resources"), expected_resources, "embedded Ascon resources")

    bounds = {
        "track_a": {"cnot_count_max": 1594, "cnot_depth_max": 119},
        "track_b": {"cnot_count_max": 1595, "cnot_depth_max": 118},
    }
    require_equal(record.get("acceptance_bounds"), bounds, "embedded Ascon bounds")
    acceptance = {
        "track_a": count <= 1594 and depth <= 119,
        "track_b": count <= 1595 and depth <= 118,
    }
    require_equal(record.get("acceptance"), acceptance, "embedded Ascon acceptance")

    if record.get("id") == "ascon_linear_commutation_rescheduled_inplace_1595cnot_depth45":
        predecessor_id = "ascon_linear_roy_baksi_chattopadhyay_inplace_1595cnot_depth119"
        predecessor_count, predecessor_depth = 1595, 119
    else:
        require_equal(
            record.get("id"),
            f"ascon_linear_local_rewrite_inplace_{count}cnot_depth{depth}",
            "embedded Ascon record id",
        )
        predecessor_id = "ascon_linear_commutation_rescheduled_inplace_1595cnot_depth45"
        predecessor_count, predecessor_depth = 1595, 45
    require_equal(
        record.get("comparison"),
        {
            "predecessor_id": predecessor_id,
            "predecessor_cnot_count": predecessor_count,
            "predecessor_cnot_depth": predecessor_depth,
            "cnot_reduction": predecessor_count - count,
            "depth_reduction": predecessor_depth - depth,
        },
        "embedded Ascon comparison",
    )
    return {
        "id": record.get("id"),
        "cnot_count": count,
        "cnot_depth": depth,
        "total_logical_depth": depth,
    }


def verify_ascon_round_core_record(record: dict[str, Any]) -> dict[str, Any]:
    require_equal(
        record.get("schema"),
        "quantum-ascon-round-core-derived-ir/v1",
        "round-core schema",
    )
    require_equal(
        record.get("target"),
        "ascon_final_standard_pL_after_pS_round_core",
        "round-core target",
    )
    verify_provenance(record)
    provenance = record["provenance"]
    require_equal(
        provenance.get("derivation"),
        "source_sbox_parallel_composition_followed_by_inplace_linear_tail",
        "round-core derivation",
    )
    files = provenance.get("files")
    if not isinstance(files, list) or len(files) != 3:
        raise VerificationError("round-core provenance needs three included files")
    expected_prefix_paths = [
        "ir/baselines/quantum/ascon_sbox_guo_et_al_width5_16gate_nct.json",
        "ir/baselines/quantum/ascon_sbox_guo_et_al_width5_16gate_nct.qasm",
    ]
    require_equal(
        [entry.get("path") for entry in files[:2]],
        expected_prefix_paths,
        "round-core source paths",
    )
    linear_relative = files[2].get("path")
    if not isinstance(linear_relative, str):
        raise VerificationError("round-core linear provenance path is missing")
    linear_path = ROOT / linear_relative
    linear_record = json.loads(linear_path.read_text(encoding="utf-8"))
    linear_summary = verify_record(linear_path)

    boundary = record.get("boundary")
    if not isinstance(boundary, dict):
        raise VerificationError("round-core boundary must be an object")
    initial_placement = boundary.get("logical_input_to_physical_wires")
    if (
        not isinstance(initial_placement, list)
        or len(initial_placement) != ASCON_STATE_QUBITS
        or any(not isinstance(wire, int) for wire in initial_placement)
        or sorted(initial_placement) != list(range(ASCON_STATE_QUBITS))
    ):
        raise VerificationError("round-core initial placement is not a permutation")
    expected_boundary = {
        "operation": "unitary",
        "basis_semantics": "final_standard_ascon_pL_after_pS",
        "logical_input_to_physical_wires": initial_placement,
        "physical_output_wires": list(range(ASCON_STATE_QUBITS)),
        "word_order": [f"x{word}" for word in range(ASCON_WORD_COUNT)],
        "bit_order_within_word": "msb0",
        "wire_definition": "logical bit 64*j+i is bit i from the MSB of x[j]; physical output wire 64*j+i is bit i from the MSB of Sigma_j(Sbox(x))[j]",
        "round_constant_layer": "excluded",
        "sbox_slice_count": ASCON_WORD_BITS,
        "sbox_source_output_coordinate_wires": [4, 0, 3, 2, 1],
        "initial_placement_policy": "one_declared_permutation_free_at_boundary",
        "terminal_output_permutation": "identity",
    }
    require_equal(boundary, expected_boundary, "round-core boundary")
    expected_model = {
        "logical_qubits": ASCON_STATE_QUBITS,
        "input_qubits": ASCON_STATE_QUBITS,
        "output_qubits": ASCON_STATE_QUBITS,
        "zero_initialized_ancillas": 0,
        "clean_ancillas_returned_to_zero": 0,
        "dirty_ancillas": 0,
        "garbage_qubits": 0,
        "gate_set": ["X", "CNOT", "Toffoli"],
        "connectivity": "all_to_all",
        "initial_placement_cost_model": "one_free_logical_relabeling_at_boundary",
        "measurements": 0,
        "classical_feed_forward": False,
        "compilation_level": "logical_nct_pre_clifford_t_and_pre_device_mapping",
        "physical_qubits": None,
        "noise_model": None,
        "fault_tolerance_model": None,
    }
    require_equal(record.get("model"), expected_model, "round-core model")

    schedule = record.get("schedule")
    if not isinstance(schedule, dict):
        raise VerificationError("round-core schedule must be an object")
    require_equal(
        set(schedule),
        {
            "serialization",
            "sbox_prefix_layer_count",
            "linear_tail_layer_count",
            "layers",
        },
        "round-core schedule fields",
    )
    require_equal(schedule.get("serialization"), "layer_major", "round serialization")
    gates, gate_layers = parse_nct_ir_layers(
        schedule.get("layers"), ASCON_STATE_QUBITS
    )
    layer_depth, layer_toffoli_depth = verify_nct_layers(gates, gate_layers)
    layers: list[list[tuple[str, tuple[int, ...]]]] = [
        [] for _ in range(layer_depth)
    ]
    for gate, layer in zip(gates, gate_layers):
        assert layer is not None
        layers[layer - 1].append(gate)
    prefix_depth = schedule.get("sbox_prefix_layer_count")
    tail_depth = schedule.get("linear_tail_layer_count")
    require_equal(prefix_depth, 11, "round S-box prefix depth")
    require_equal(
        tail_depth,
        linear_record["resources"]["cnot_depth"],
        "round linear tail depth",
    )
    require_equal(prefix_depth + tail_depth, layer_depth, "round component depth sum")

    physical_to_slice: dict[int, tuple[int, int]] = {}
    linear_placement = [0] * ASCON_STATE_QUBITS
    output_q_for_word = (4, 0, 3, 2, 1)
    for bit in range(ASCON_WORD_BITS):
        q_wires = [
            initial_placement[word * ASCON_WORD_BITS + bit]
            for word in range(ASCON_WORD_COUNT)
        ]
        if len(set(q_wires)) != ASCON_WORD_COUNT:
            raise VerificationError(f"round S-box slice {bit} reuses a wire")
        for q, wire in enumerate(q_wires):
            if wire in physical_to_slice:
                raise VerificationError("round physical wire belongs to two slices")
            physical_to_slice[wire] = (bit, q)
        for word, q in enumerate(output_q_for_word):
            linear_placement[word * ASCON_WORD_BITS + bit] = q_wires[q]
    require_equal(
        sorted(physical_to_slice),
        list(range(ASCON_STATE_QUBITS)),
        "round S-box slice cover",
    )
    require_equal(
        linear_placement,
        linear_record["boundary"]["logical_input_to_physical_wires"],
        "round composed linear placement",
    )

    per_slice: list[list[tuple[str, tuple[int, ...]]]] = [
        [] for _ in range(ASCON_WORD_BITS)
    ]
    for layer in layers[:prefix_depth]:
        for name, wires in layer:
            owners = {physical_to_slice[wire][0] for wire in wires}
            if len(owners) != 1:
                raise VerificationError("round prefix gate crosses S-box slices")
            bit = owners.pop()
            local_wires = tuple(physical_to_slice[wire][1] for wire in wires)
            per_slice[bit].append((name, local_wires))
    for bit, slice_gates in enumerate(per_slice):
        require_equal(
            Counter(name for name, _ in slice_gates),
            Counter({"X": 3, "CNOT": 6, "Toffoli": 7}),
            f"round slice {bit} gate counts",
        )
        for value in range(32):
            inputs = [(value >> index) & 1 for index in range(5)]
            final = run_nct_basis_state(slice_gates, inputs)
            observed = [final[q] for q in output_q_for_word]
            require_equal(
                observed,
                ascon_sbox_bits(inputs),
                f"round slice {bit} input {value}",
            )

    linear_layers = parse_layers(
        linear_record["schedule"]["layers"], ASCON_STATE_QUBITS
    )
    expected_tail = [
        [("CNOT", (control, target)) for control, target in layer]
        for layer in linear_layers
    ]
    require_equal(layers[prefix_depth:], expected_tail, "round exact linear tail")
    rows = [0] * ASCON_STATE_QUBITS
    for logical_input, physical_wire in enumerate(linear_placement):
        rows[physical_wire] = 1 << logical_input
    for layer in expected_tail:
        for _name, (control, target) in layer:
            rows[target] ^= rows[control]
    require_equal(rows, expected_ascon_linear_msb0_rows(), "round final linear matrix")

    counts = nct_gate_counts(gates)
    total_count = sum(counts.values())
    weighted_depth = sum(
        max({"X": 1, "CNOT": 1, "Toffoli": 7}[name] for name, _ in layer)
        for layer in layers
    )
    expected_resources = {
        "logical_qubits": ASCON_STATE_QUBITS,
        "physical_qubits": None,
        "zero_initialized_ancillas": 0,
        "clean_ancillas_returned_to_zero": 0,
        "dirty_ancillas": 0,
        "garbage_qubits": 0,
        "total_gate_count": total_count,
        **counts,
        "t_count": None,
        "total_logical_depth": layer_depth,
        "cnot_depth": None,
        "toffoli_depth": layer_toffoli_depth,
        "t_depth": None,
        "source_weighted_full_depth": weighted_depth,
        "source_weighted_depth_gate_costs": {"X": 1, "CNOT": 1, "Toffoli": 7},
        "source_weighted_depth_semantics": "sum_of_per_layer_maximum_source_gate_costs",
        "measurement_rounds": 0,
        "classical_control_operations": 0,
        "topology_overhead": None,
        "component_resources": {
            "sbox_slices": {
                "copies": ASCON_WORD_BITS,
                "per_copy": {
                    "x_count": 3,
                    "cnot_count": 6,
                    "toffoli_count": 7,
                    "total_gate_count": 16,
                    "total_logical_depth": 11,
                    "toffoli_depth": 7,
                    "source_weighted_full_depth": 53,
                },
            },
            "linear_tail": {
                "id": linear_record["id"],
                "cnot_count": linear_summary["cnot_count"],
                "cnot_depth": linear_summary["cnot_depth"],
            },
        },
    }
    require_equal(record.get("resources"), expected_resources, "round resources")
    followup = (
        record.get("id")
        == "ascon_round_core_guo_linear_rewrite_2549gate_depth56"
    )
    expected_bounds = {
        "total_gate_count_max": 2549 if followup else 2618,
        "x_count_max": 192,
        "cnot_count_max": 1909 if followup else 1978,
        "toffoli_count_max": 448,
        "toffoli_depth_max": 7,
        "total_logical_depth_max": 56,
        "source_weighted_full_depth_max": 98,
    }
    require_equal(record.get("acceptance_bounds"), expected_bounds, "round bounds")
    target_met = (
        total_count <= expected_bounds["total_gate_count_max"]
        and counts["x_count"] <= expected_bounds["x_count_max"]
        and counts["cnot_count"] <= expected_bounds["cnot_count_max"]
        and counts["toffoli_count"] <= expected_bounds["toffoli_count_max"]
        and layer_toffoli_depth <= expected_bounds["toffoli_depth_max"]
        and layer_depth <= expected_bounds["total_logical_depth_max"]
        and weighted_depth <= expected_bounds["source_weighted_full_depth_max"]
    )
    require_equal(record.get("acceptance"), {"target_met": target_met}, "round acceptance")
    baseline = record.get("id") == "ascon_round_core_guo_xzlbz_2619gate_depth56"
    if baseline:
        require_equal(
            provenance.get("evidence_status"),
            "deterministic-composition-verified",
            "round baseline evidence class",
        )
        require_equal(
            record.get("comparison"),
            {
                "evidence_class": "derived_baseline",
                "sbox_component_id": "ascon_sbox_guo_et_al_width5_16gate_nct",
                "linear_component_id": linear_record["id"],
            },
            "round baseline comparison",
        )
    elif followup:
        require_equal(
            provenance.get("evidence_status"),
            "repository-derived-verified",
            "round follow-up evidence class",
        )
        require_equal(
            record.get("id"),
            f"ascon_round_core_guo_linear_rewrite_{total_count}gate_depth{layer_depth}",
            "round follow-up id",
        )
        require_equal(
            record.get("comparison"),
            {
                "predecessor_id": "ascon_round_core_guo_linear_rewrite_2550gate_depth56",
                "predecessor_total_gate_count": 2550,
                "predecessor_cnot_count": 1910,
                "total_gate_reduction": 2550 - total_count,
                "cnot_reduction": 1910 - counts["cnot_count"],
                "logical_depth_reduction": 56 - layer_depth,
            },
            "round follow-up comparison",
        )
    else:
        require_equal(
            provenance.get("evidence_status"),
            "repository-derived-verified",
            "round candidate evidence class",
        )
        require_equal(
            record.get("id"),
            f"ascon_round_core_guo_linear_rewrite_{total_count}gate_depth{layer_depth}",
            "round candidate id",
        )
        require_equal(
            record.get("comparison"),
            {
                "predecessor_id": "ascon_round_core_guo_xzlbz_2619gate_depth56",
                "predecessor_total_gate_count": 2619,
                "predecessor_cnot_count": 1979,
                "total_gate_reduction": 2619 - total_count,
                "cnot_reduction": 1979 - counts["cnot_count"],
                "logical_depth_reduction": 56 - layer_depth,
            },
            "round candidate comparison",
        )
    return {
        "id": record.get("id"),
        "kind": "nct",
        "logical_qubits": ASCON_STATE_QUBITS,
        **counts,
        "total_gate_count": total_count,
        "toffoli_depth": layer_toffoli_depth,
        "total_logical_depth": layer_depth,
        "source_weighted_full_depth": weighted_depth,
        "target_met": target_met,
        "sbox_exhaustive_rows": ASCON_WORD_BITS * 32,
        "linear_rows_verified": ASCON_STATE_QUBITS,
    }


def parse_affine_layers(raw_layers: Any) -> list[list[tuple[str, int | None, int]]]:
    if not isinstance(raw_layers, list) or not raw_layers:
        raise VerificationError("layers must be a nonempty list")
    layers: list[list[tuple[str, int | None, int]]] = []
    for layer_index, raw_layer in enumerate(raw_layers):
        if not isinstance(raw_layer, list) or not raw_layer:
            raise VerificationError(f"layer {layer_index} must be nonempty")
        used: set[int] = set()
        layer: list[tuple[str, int | None, int]] = []
        for gate_index, raw_gate in enumerate(raw_layer):
            if not isinstance(raw_gate, dict):
                raise VerificationError(f"layer {layer_index} gate {gate_index} is not an object")
            gate = raw_gate.get("gate")
            if gate == "CNOT":
                control = raw_gate.get("control")
                target = raw_gate.get("target")
                if set(raw_gate) != {"gate", "control", "target"}:
                    raise VerificationError(f"layer {layer_index} CNOT has unexpected fields")
                if not isinstance(control, int) or not isinstance(target, int):
                    raise VerificationError(f"layer {layer_index} CNOT indices must be integers")
                if not 0 <= control < AFFINE_QUBITS or not 0 <= target < AFFINE_QUBITS:
                    raise VerificationError(f"layer {layer_index} CNOT is out of range")
                if control == target:
                    raise VerificationError(f"layer {layer_index} contains a self-CNOT")
                gate_wires = {control, target}
                layer.append((gate, control, target))
            elif gate == "X":
                target = raw_gate.get("target")
                if set(raw_gate) != {"gate", "target"} or not isinstance(target, int):
                    raise VerificationError(f"layer {layer_index} X gate is malformed")
                if not 0 <= target < AFFINE_QUBITS:
                    raise VerificationError(f"layer {layer_index} X is out of range")
                gate_wires = {target}
                layer.append((gate, None, target))
            else:
                raise VerificationError(f"layer {layer_index} has unsupported gate {gate!r}")
            if used & gate_wires:
                raise VerificationError(f"layer {layer_index} reuses a qubit")
            used |= gate_wires
        layers.append(layer)
    return layers


def affine_circuit_semantics(
    layers: list[list[tuple[str, int | None, int]]],
) -> tuple[list[int], list[int]]:
    rows = [1 << index for index in range(AFFINE_QUBITS)]
    constants = [0] * AFFINE_QUBITS
    for layer in layers:
        before_rows = rows[:]
        before_constants = constants[:]
        for gate, control, target in layer:
            if gate == "CNOT":
                assert control is not None
                rows[target] = before_rows[target] ^ before_rows[control]
                constants[target] = before_constants[target] ^ before_constants[control]
            else:
                constants[target] = before_constants[target] ^ 1
    return rows, constants


def expected_affine_semantics() -> tuple[list[int], list[int]]:
    rows = [1 << index for index in range(AFFINE_QUBITS)]
    constants = [0] * AFFINE_QUBITS
    for output, columns in enumerate(AFFINE_ROWS):
        wire = 18 + output
        for column in columns:
            rows[wire] ^= 1 << column
        constants[wire] = int(output in AFFINE_CONSTANTS)
    return rows, constants


def verify_affine_record(record: dict[str, Any]) -> dict[str, Any]:
    require_equal(record.get("schema"), "quantum-affine-circuit-ir/v1", "schema")
    require_equal(record.get("target"), "aes_sbox_jiang_output_accumulation", "target")
    verify_provenance(record)

    wire_names = AFFINE_PRODUCT_NAMES + AFFINE_OUTPUT_NAMES
    boundary = record.get("boundary")
    if not isinstance(boundary, dict):
        raise VerificationError("boundary must be an object")
    expected_boundary = {
        "operation": "unitary",
        "basis_semantics": "|m>|y> -> |m>|y xor A*m xor c>",
        "input_wires": wire_names,
        "output_wires": wire_names,
        "product_wire_order": AFFINE_PRODUCT_NAMES,
        "accumulator_wire_order": AFFINE_OUTPUT_NAMES,
        "aes_bit_order": "msb0",
        "terminal_permutation": "identity",
        "product_inputs_available_at_boundary": True,
        "accumulator_initial_state": "arbitrary",
        "target_rows": AFFINE_ROWS,
        "constant_outputs": AFFINE_CONSTANTS,
    }
    require_equal(boundary, expected_boundary, "affine boundary")

    expected_model = {
        "logical_qubits": AFFINE_QUBITS,
        "clean_ancillas": 0,
        "dirty_ancillas": 0,
        "ancilla_initial_state": "not_applicable_all_wires_are_boundary_io",
        "ancilla_final_state": "not_applicable_all_wires_are_boundary_io",
        "gate_set": ["CNOT", "X"],
        "measurements": 0,
        "classical_feed_forward": False,
        "connectivity": "all_to_all",
        "compilation_level": "logical_pre_device_mapping",
        "physical_qubits": None,
        "noise_model": None,
        "fault_tolerance_model": None,
    }
    require_equal(record.get("model"), expected_model, "logical circuit model")

    layers = parse_affine_layers(record.get("layers"))
    actual_rows, actual_constants = affine_circuit_semantics(layers)
    expected_rows, expected_constants = expected_affine_semantics()
    if actual_rows != expected_rows:
        mismatches = [
            index for index in range(AFFINE_QUBITS) if actual_rows[index] != expected_rows[index]
        ]
        raise VerificationError(f"affine matrix mismatch on output rows {mismatches}")
    if actual_constants != expected_constants:
        mismatches = [
            index
            for index in range(AFFINE_QUBITS)
            if actual_constants[index] != expected_constants[index]
        ]
        raise VerificationError(f"affine constant mismatch on output rows {mismatches}")

    gates = [gate for layer in layers for gate in layer]
    cnot_count = sum(gate[0] == "CNOT" for gate in gates)
    x_count = sum(gate[0] == "X" for gate in gates)
    depth = len(layers)
    cnot_depth = sum(any(gate[0] == "CNOT" for gate in layer) for layer in layers)
    expected_resources = {
        "logical_qubits": AFFINE_QUBITS,
        "physical_qubits": None,
        "clean_ancillas": 0,
        "dirty_ancillas": 0,
        "total_gate_count": cnot_count + x_count,
        "cnot_count": cnot_count,
        "x_count": x_count,
        "toffoli_count": 0,
        "t_count": 0,
        "total_logical_depth": depth,
        "cnot_depth": cnot_depth,
        "toffoli_depth": 0,
        "t_depth": 0,
        "measurement_rounds": 0,
        "classical_control_operations": 0,
        "topology_overhead": None,
    }
    require_equal(record.get("resources"), expected_resources, "resource vector")
    return {
        "id": record.get("id"),
        "cnot_count": cnot_count,
        "x_count": x_count,
        "cnot_depth": cnot_depth,
        "total_logical_depth": depth,
    }


NCT_NORMALIZATION = (
    "cancel_identical_self_inverse_gates_adjacent_on_all_incident_wires_to_fixed_point"
)
NCT_SOURCE_CONFIGS: dict[str, dict[str, Any]] = {
    "aes_sbox_forward_minimal_width_nct": {
        "width": 9,
        "input_width": 8,
        "qasm_path": "ir/baselines/quantum/aes_sbox_huang_zhang_lin_width9_raw.qasm",
        "layer_qasm_path": "ir/baselines/quantum/aes_sbox_huang_zhang_lin_width9_layers.qasm",
        "output_coordinate_wires": [4, 2, 0, 1, 3, 5, 6, 7],
        "clean_workspace_wires": [8],
        "zero_initialized_output_wires": [],
        "preserved_input_wires": [],
        "clean_ancillas": 1,
        "zero_initialized_output_qubits": 0,
        "layer_full_depth": 1597,
        "layer_toffoli_depth": 793,
    },
    "ascon_sbox_forward_minimal_width_nct": {
        "width": 5,
        "input_width": 5,
        "qasm_path": "ir/baselines/quantum/ascon_sbox_huang_zhang_lin_width5_raw.qasm",
        "layer_qasm_path": "ir/baselines/quantum/ascon_sbox_huang_zhang_lin_width5_layers.qasm",
        "output_coordinate_wires": [0, 2, 4, 1, 3],
        "clean_workspace_wires": [],
        "zero_initialized_output_wires": [],
        "preserved_input_wires": [],
        "clean_ancillas": 0,
        "zero_initialized_output_qubits": 0,
        "layer_full_depth": 44,
        "layer_toffoli_depth": 7,
    },
    "ascon_sbox_forward_toffoli_depth1_nct": {
        "width": 15,
        "input_width": 5,
        "qasm_path": "ir/baselines/quantum/ascon_sbox_huang_zhang_lin_toffoli_depth1_raw.qasm",
        "layer_qasm_path": "ir/baselines/quantum/ascon_sbox_huang_zhang_lin_toffoli_depth1_layers.qasm",
        "output_coordinate_wires": [10, 11, 12, 13, 14],
        "clean_workspace_wires": [5, 6, 7, 8, 9],
        "zero_initialized_output_wires": [10, 11, 12, 13, 14],
        "preserved_input_wires": [0, 1, 2, 3, 4],
        "clean_ancillas": 5,
        "zero_initialized_output_qubits": 5,
        "layer_full_depth": 56,
        "layer_toffoli_depth": 1,
    },
}

NCT_DIAGRAM_CONFIGS: dict[str, dict[str, Any]] = {
    "ascon_sbox_guo_et_al_width5_16gate_nct": {
        "target": "ascon_sbox_forward_width5_total_gate_nct",
        "width": 5,
        "input_width": 5,
        "qasm_path": "ir/baselines/quantum/ascon_sbox_guo_et_al_width5_16gate_nct.qasm",
        "source_figure": "Figure 3(c), physical PDF p.26",
        "output_coordinate_wires": [4, 0, 3, 2, 1],
        "zero_initialized_ancilla_wires": [],
        "garbage_wires": [],
        "garbage_final_input_coordinates": {},
        "source_reported_counts": {
            "x_count": 3,
            "cnot_count": 6,
            "toffoli_count": 7,
            "total_gate_count": 16,
        },
        "source_reported_weighted_full_depth": 53,
    },
}

NCT_SPECIALIZED_TARGET = "ascon_sbox_round_constant_x2_specialized_width5_nct"
NCT_SPECIALIZED_BASELINE_ID = "ascon_sbox_round_constant_x2_specialized_17gate_nct"
NCT_SPECIALIZED_CANDIDATE_ID = "ascon_sbox_round_constant_x2_specialized_16gate_nct"
NCT_SPECIALIZED_SOURCE_RECORD = (
    "ir/baselines/quantum/ascon_sbox_guo_et_al_width5_16gate_nct.json"
)
NCT_SPECIALIZED_BASELINE_RECORD = (
    "ir/baselines/quantum/ascon_sbox_round_constant_x2_specialized_17gate_nct.json"
)
NCT_SPECIALIZED_QASMS = {
    NCT_SPECIALIZED_BASELINE_ID: (
        "ir/baselines/quantum/"
        "ascon_sbox_round_constant_x2_specialized_17gate_nct.qasm"
    ),
    NCT_SPECIALIZED_CANDIDATE_ID: (
        "ir/results/quantum/"
        "ascon_sbox_round_constant_x2_specialized_16gate_nct.qasm"
    ),
}

NCT_REPOSITORY_CONFIGS: dict[str, dict[str, Any]] = {
    "aes_sbox_repository_width9_829toffoli": {
        "target": "aes_sbox_forward_minimal_width_nct",
        "source_record_path": "ir/baselines/quantum/aes_sbox_huang_zhang_lin_width9_nct.json",
        "candidate_qasm_path": "ir/results/quantum/aes_sbox_repository_width9_829toffoli.qasm",
        "acceptance_bounds": {
            "logical_qubits_at_most": 9,
            "clean_ancillas_at_most": 1,
            "dirty_ancillas": 0,
            "x_count_at_most": 233,
            "cnot_count_at_most": 883,
            "toffoli_count_at_most": 829,
            "toffoli_depth_at_most": 792,
            "total_logical_depth_at_most": 1591,
            "measurements": 0,
        },
    },
}

NCT_DERIVED_CONFIGS: dict[str, dict[str, Any]] = {
    "ascon_sbox_repository_toffoli_depth1_44cnot_depth19": {
        "target": "ascon_sbox_forward_toffoli_depth1_nct",
        "acceptance_bounds": {
            "logical_qubits": 15,
            "clean_ancillas": 5,
            "zero_initialized_output_qubits": 5,
            "dirty_ancillas": 0,
            "x_count_at_most": 1,
            "cnot_count_at_most": 46,
            "toffoli_count_exactly": 5,
            "toffoli_depth_at_most": 1,
            "total_logical_depth_at_most": 19,
            "measurements_exactly": 0,
        },
        "construction_requirements": {
            "method": "fixed-preparation final-output-aware affine-shell resynthesis",
            "source_preparation_cnot_count": 38,
            "replacement_preparation_cnot_count": 14,
            "source_middle_preserved_verbatim": False,
            "toffoli_layer_preserved_verbatim": True,
            "predecessor_middle_cnot_count": 19,
            "replacement_middle_cnot_count": 16,
            "quadratic_output_cnot_count": 8,
            "linear_injection_cnot_count": 8,
        },
    },
    "ascon_sbox_repository_toffoli_depth1_43cnot_depth19": {
        "target": "ascon_sbox_forward_toffoli_depth1_nct",
        "direct_predecessor_record_path": "ir/baselines/quantum/ascon_sbox_repository_toffoli_depth1_44cnot_depth19.json",
        "acceptance_bounds": {
            "logical_qubits": 15,
            "clean_ancillas": 5,
            "zero_initialized_output_qubits": 5,
            "dirty_ancillas": 0,
            "x_count_at_most": 1,
            "cnot_count_at_most": 43,
            "total_gate_count_at_most": 49,
            "toffoli_count_exactly": 5,
            "toffoli_depth_at_most": 1,
            "total_logical_depth_at_most": 19,
            "measurements_exactly": 0,
        },
        "construction_requirements": {
            "method": "pre-transform shared-linear injection resynthesis",
            "source_preparation_cnot_count": 38,
            "replacement_preparation_cnot_count": 14,
            "source_middle_preserved_verbatim": False,
            "toffoli_layer_preserved_verbatim": True,
            "predecessor_middle_cnot_count": 16,
            "replacement_middle_cnot_count": 15,
            "quadratic_output_cnot_count": 8,
            "linear_injection_cnot_count": 7,
            "shared_linear_injection_cnot_count": 1,
            "direct_linear_injection_cnot_count": 6,
            "shared_linear_source_wire": 2,
            "shared_linear_target_wire": 13,
            "shared_linear_final_output_wires": [11, 12, 13],
        },
    },
    "ascon_sbox_repository_toffoli_depth1_42cnot_depth19": {
        "target": "ascon_sbox_forward_toffoli_depth1_nct",
        "direct_predecessor_record_path": "ir/baselines/quantum/ascon_sbox_repository_toffoli_depth1_43cnot_depth19.json",
        "acceptance_bounds": {
            "logical_qubits": 15,
            "clean_ancillas": 5,
            "zero_initialized_output_qubits": 5,
            "dirty_ancillas": 0,
            "x_count_at_most": 1,
            "cnot_count_at_most": 42,
            "total_gate_count_at_most": 48,
            "toffoli_count_exactly": 5,
            "toffoli_depth_at_most": 1,
            "total_logical_depth_at_most": 19,
            "measurements_exactly": 0,
        },
        "construction_requirements": {
            "context_contract_id": "ascon_sbox_initialized_isometry_context_v1",
            "deleted_predecessor_gate_indices": [32, 35],
            "insert_boundary": 11,
            "insert_cnot": [1, 11],
            "method": "initialized-subspace contextual two-delete/one-insert resynthesis",
            "predecessor_cnot_count": 43,
            "predecessor_gate_count": 49,
            "search_space_cases": 8722980,
            "toffoli_layer_preserved_verbatim": True,
        },
    },
}

def nct_expected_boundary(target: str, config: dict[str, Any]) -> dict[str, Any]:
    input_width = config["input_width"]
    width = config["width"]
    primitive = "AES" if target.startswith("aes_") else "Ascon"
    operation = "unitary" if not (
        config["clean_workspace_wires"] or config["zero_initialized_output_wires"]
    ) else "isometry"
    return {
        "operation": operation,
        "basis_semantics": f"forward {primitive} S-box on computational-basis states",
        "input_coordinate_wires": list(range(input_width)),
        "input_coordinate_order": [f"x{index}" for index in range(input_width)],
        "input_bit_order": "msb0",
        "output_coordinate_wires": config["output_coordinate_wires"],
        "output_coordinate_order": [f"y{index}" for index in range(input_width)],
        "output_bit_order": "msb0",
        "preserved_input_wires": config["preserved_input_wires"],
        "clean_workspace_wires": config["clean_workspace_wires"],
        "clean_workspace_initial_state": (
            "zero" if config["clean_workspace_wires"] else "not_applicable"
        ),
        "clean_workspace_final_state": (
            "zero" if config["clean_workspace_wires"] else "not_applicable"
        ),
        "zero_initialized_output_wires": config["zero_initialized_output_wires"],
        "terminal_permutation": (
            "identity"
            if config["output_coordinate_wires"] == list(range(input_width))
            else "explicit_nonidentity"
        ),
        "all_circuit_wires": list(range(width)),
    }


def nct_expected_model(config: dict[str, Any]) -> dict[str, Any]:
    return {
        "logical_qubits": config["width"],
        "physical_qubits": None,
        "input_qubits": config["input_width"],
        "output_qubits": config["input_width"],
        "zero_initialized_output_qubits": config["zero_initialized_output_qubits"],
        "clean_ancillas": config["clean_ancillas"],
        "dirty_ancillas": 0,
        "gate_set": ["X", "CNOT", "Toffoli"],
        "connectivity": "all_to_all",
        "measurements": 0,
        "classical_feed_forward": False,
        "compilation_level": "logical_nct_pre_clifford_t_and_pre_device_mapping",
        "noise_model": None,
        "fault_tolerance_model": None,
    }


def nct_diagram_expected_boundary(config: dict[str, Any]) -> dict[str, Any]:
    input_width = config["input_width"]
    width = config["width"]
    zero_initialized = config["zero_initialized_ancilla_wires"]
    garbage_wires = config["garbage_wires"]
    garbage_functions = {
        f"q[{wire}]": f"x{input_coordinate}"
        for wire, input_coordinate in config["garbage_final_input_coordinates"].items()
    }
    return {
        "operation": "isometry" if zero_initialized else "unitary",
        "basis_semantics": "forward Ascon S-box on computational-basis states",
        "input_coordinate_wires": list(range(input_width)),
        "input_coordinate_order": [f"x{index}" for index in range(input_width)],
        "input_bit_order": "msb0",
        "output_coordinate_wires": config["output_coordinate_wires"],
        "output_coordinate_order": [f"y{index}" for index in range(input_width)],
        "output_bit_order": "msb0",
        "preserved_input_wires": [],
        "zero_initialized_ancilla_wires": zero_initialized,
        "zero_initialized_ancilla_initial_state": (
            "zero" if zero_initialized else "not_applicable"
        ),
        "cleaned_ancilla_wires": [],
        "garbage_wires": garbage_wires,
        "garbage_final_functions": garbage_functions,
        "ancilla_cleanup_policy": (
            "garbage_allowed" if garbage_wires else "not_applicable"
        ),
        "terminal_permutation": "explicit_nonidentity",
        "all_circuit_wires": list(range(width)),
    }


def nct_diagram_expected_model(config: dict[str, Any]) -> dict[str, Any]:
    return {
        "logical_qubits": config["width"],
        "physical_qubits": None,
        "input_qubits": config["input_width"],
        "output_qubits": config["input_width"],
        "zero_initialized_ancillas": len(config["zero_initialized_ancilla_wires"]),
        "clean_ancillas_returned_to_zero": 0,
        "dirty_ancillas": 0,
        "garbage_qubits": len(config["garbage_wires"]),
        "gate_set": ["X", "CNOT", "Toffoli"],
        "connectivity": "all_to_all",
        "measurements": 0,
        "classical_feed_forward": False,
        "compilation_level": "logical_nct_pre_clifford_t_and_pre_device_mapping",
        "noise_model": None,
        "fault_tolerance_model": None,
    }


def canonical_nct_gate(gate: tuple[str, tuple[int, ...]]) -> tuple[str, tuple[int, ...]]:
    name, wires = gate
    if name == "Toffoli":
        return name, (min(wires[0], wires[1]), max(wires[0], wires[1]), wires[2])
    return gate


def parse_nct_qasm(
    path: Path, expected_width: int, *, require_layers: bool
) -> tuple[list[tuple[str, tuple[int, ...]]], list[int | None]]:
    gate_patterns = [
        ("X", re.compile(r"x q\[(\d+)\];")),
        ("CNOT", re.compile(r"cx q\[(\d+)\],q\[(\d+)\];")),
        ("Toffoli", re.compile(r"ccx q\[(\d+)\],q\[(\d+)\],q\[(\d+)\];")),
    ]
    width: int | None = None
    current_layer: int | None = None
    gates: list[tuple[str, tuple[int, ...]]] = []
    gate_layers: list[int | None] = []
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw_line.strip()
        layer_match = re.search(r"Layer:\s*(\d+)", line)
        if layer_match:
            current_layer = int(layer_match.group(1))
            continue
        if (
            not line
            or line.startswith("//")
            or line == "OPENQASM 2.0;"
            or line == 'include "qelib1.inc";'
        ):
            continue
        qreg_match = re.fullmatch(r"qreg q\[(\d+)\];", line)
        if qreg_match:
            if width is not None:
                raise VerificationError(f"{path}: repeated qreg declaration")
            width = int(qreg_match.group(1))
            continue
        for name, pattern in gate_patterns:
            gate_match = pattern.fullmatch(line)
            if gate_match:
                wires = tuple(int(value) for value in gate_match.groups())
                if len(set(wires)) != len(wires):
                    raise VerificationError(
                        f"{path}:{line_number}: gate reuses a qubit: {line}"
                    )
                if any(not 0 <= wire < expected_width for wire in wires):
                    raise VerificationError(
                        f"{path}:{line_number}: gate wire is out of range: {line}"
                    )
                if require_layers and current_layer is None:
                    raise VerificationError(f"{path}:{line_number}: gate has no layer")
                gates.append((name, wires))
                gate_layers.append(current_layer)
                break
        else:
            raise VerificationError(f"{path}:{line_number}: unsupported QASM: {line}")
    require_equal(width, expected_width, f"{path} qreg width")
    if not gates:
        raise VerificationError(f"{path}: no gates")
    return gates, gate_layers


def parse_nct_ir_layers(
    raw_layers: Any, expected_width: int
) -> tuple[list[tuple[str, tuple[int, ...]]], list[int | None]]:
    if not isinstance(raw_layers, list) or not raw_layers:
        raise VerificationError("NCT layers must be a nonempty list")
    gates: list[tuple[str, tuple[int, ...]]] = []
    gate_layers: list[int | None] = []
    for layer_index, raw_layer in enumerate(raw_layers, 1):
        if not isinstance(raw_layer, list) or not raw_layer:
            raise VerificationError(f"NCT layer {layer_index} must be nonempty")
        used: set[int] = set()
        for gate_index, raw_gate in enumerate(raw_layer):
            if not isinstance(raw_gate, dict):
                raise VerificationError(
                    f"NCT layer {layer_index} gate {gate_index} is not an object"
                )
            name = raw_gate.get("gate")
            if name == "X":
                require_equal(
                    set(raw_gate), {"gate", "target"},
                    f"NCT layer {layer_index} X fields",
                )
                wires = (raw_gate.get("target"),)
            elif name == "CNOT":
                require_equal(
                    set(raw_gate), {"gate", "control", "target"},
                    f"NCT layer {layer_index} CNOT fields",
                )
                wires = (raw_gate.get("control"), raw_gate.get("target"))
            elif name == "Toffoli":
                require_equal(
                    set(raw_gate), {"gate", "controls", "target"},
                    f"NCT layer {layer_index} Toffoli fields",
                )
                controls = raw_gate.get("controls")
                if (
                    not isinstance(controls, list)
                    or len(controls) != 2
                    or any(not isinstance(wire, int) for wire in controls)
                ):
                    raise VerificationError(
                        f"NCT layer {layer_index} Toffoli controls must be two integers"
                    )
                wires = (controls[0], controls[1], raw_gate.get("target"))
            else:
                raise VerificationError(
                    f"NCT layer {layer_index} gate {gate_index} has unsupported gate {name!r}"
                )
            if any(not isinstance(wire, int) for wire in wires):
                raise VerificationError(
                    f"NCT layer {layer_index} gate {gate_index} has a noninteger wire"
                )
            integer_wires = tuple(int(wire) for wire in wires)
            if len(set(integer_wires)) != len(integer_wires):
                raise VerificationError(
                    f"NCT layer {layer_index} gate {gate_index} reuses a wire"
                )
            if any(not 0 <= wire < expected_width for wire in integer_wires):
                raise VerificationError(
                    f"NCT layer {layer_index} gate {gate_index} has an out-of-range wire"
                )
            if used & set(integer_wires):
                raise VerificationError(f"NCT layer {layer_index} reuses a qubit")
            used.update(integer_wires)
            gates.append((name, integer_wires))
            gate_layers.append(layer_index)
    return gates, gate_layers


def nct_gate_wires(gate: tuple[str, tuple[int, ...]]) -> set[int]:
    return set(gate[1])


def normalize_nct_gates(
    gates: list[tuple[str, tuple[int, ...]]],
) -> tuple[list[tuple[str, tuple[int, ...]]], Counter[tuple[str, tuple[int, ...]]]]:
    live = [True] * len(gates)
    removed: Counter[tuple[str, tuple[int, ...]]] = Counter()
    while True:
        per_wire: dict[int, list[int]] = {}
        for index, gate in enumerate(gates):
            if live[index]:
                for wire in nct_gate_wires(gate):
                    per_wire.setdefault(wire, []).append(index)
        next_on_wire: dict[tuple[int, int], int] = {}
        for wire, indices in per_wire.items():
            for left, right in zip(indices, indices[1:]):
                next_on_wire[(wire, left)] = right
        pair: tuple[int, int] | None = None
        for index, gate in enumerate(gates):
            if not live[index]:
                continue
            following = [next_on_wire.get((wire, index)) for wire in nct_gate_wires(gate)]
            if not following or following[0] is None or len(set(following)) != 1:
                continue
            other = following[0]
            assert other is not None
            if canonical_nct_gate(gate) == canonical_nct_gate(gates[other]):
                pair = index, other
                break
        if pair is None:
            break
        left, right = pair
        live[left] = live[right] = False
        removed[canonical_nct_gate(gates[left])] += 1
    return [gate for index, gate in enumerate(gates) if live[index]], removed


def nct_gate_counts(gates: list[tuple[str, tuple[int, ...]]]) -> dict[str, int]:
    counts = Counter(name for name, _ in gates)
    return {
        "x_count": counts["X"],
        "cnot_count": counts["CNOT"],
        "toffoli_count": counts["Toffoli"],
    }


def ordered_nct_depths(
    gates: list[tuple[str, tuple[int, ...]]], width: int
) -> tuple[int, int]:
    full_depths = [0] * width
    toffoli_depths = [0] * width
    for name, wires_tuple in gates:
        wires = list(wires_tuple)
        full_depth = max(full_depths[wire] for wire in wires) + 1
        for wire in wires:
            full_depths[wire] = full_depth
        if name == "Toffoli":
            toffoli_depth = max(toffoli_depths[wire] for wire in wires) + 1
            for wire in wires:
                toffoli_depths[wire] = toffoli_depth
        elif name == "CNOT":
            toffoli_depth = max(toffoli_depths[wire] for wire in wires)
            for wire in wires:
                toffoli_depths[wire] = toffoli_depth
    return max(full_depths), max(toffoli_depths)


def weighted_nct_depth(
    gates: list[tuple[str, tuple[int, ...]]], width: int
) -> int:
    gate_weights = {"X": 1, "CNOT": 1, "Toffoli": 7}
    depths = [0] * width
    for name, wires_tuple in gates:
        depth = max(depths[wire] for wire in wires_tuple) + gate_weights[name]
        for wire in wires_tuple:
            depths[wire] = depth
    return max(depths)


def verify_nct_layers(
    gates: list[tuple[str, tuple[int, ...]]], gate_layers: list[int | None]
) -> tuple[int, int]:
    if any(layer is None for layer in gate_layers):
        raise VerificationError("layer QASM contains an unlayered gate")
    layers = [int(layer) for layer in gate_layers if layer is not None]
    depth = max(layers)
    require_equal(sorted(set(layers)), list(range(1, depth + 1)), "QASM layer indices")
    for layer in range(1, depth + 1):
        used: set[int] = set()
        for gate, gate_layer in zip(gates, layers):
            if gate_layer != layer:
                continue
            wires = nct_gate_wires(gate)
            if used & wires:
                raise VerificationError(f"QASM layer {layer} reuses a qubit")
            used |= wires
    toffoli_depth = len(
        {
            layer
            for (name, _), layer in zip(gates, layers)
            if name == "Toffoli"
        }
    )
    return depth, toffoli_depth


def aes_gf_multiply(left: int, right: int) -> int:
    result = 0
    for _ in range(8):
        if right & 1:
            result ^= left
        carry = left & 0x80
        left = (left << 1) & 0xFF
        if carry:
            left ^= 0x1B
        right >>= 1
    return result


def aes_sbox_value(value: int) -> int:
    inverse = 0
    if value:
        inverse = 1
        base = value
        exponent = 254
        while exponent:
            if exponent & 1:
                inverse = aes_gf_multiply(inverse, base)
            base = aes_gf_multiply(base, base)
            exponent >>= 1
    rotated = [((inverse << shift) | (inverse >> (8 - shift))) & 0xFF for shift in range(1, 5)]
    return inverse ^ rotated[0] ^ rotated[1] ^ rotated[2] ^ rotated[3] ^ 0x63


def ascon_sbox_bits(inputs: list[int]) -> list[int]:
    x0, x1, x2, x3, x4 = inputs
    a0 = x0 ^ x4
    a4 = x4 ^ x3
    a2 = x2 ^ x1
    b0 = a0 ^ ((x1 ^ 1) & a2)
    b1 = x1 ^ ((a2 ^ 1) & x3)
    b2 = a2 ^ ((x3 ^ 1) & a4)
    b3 = x3 ^ ((a4 ^ 1) & a0)
    b4 = a4 ^ ((a0 ^ 1) & x1)
    return [b0 ^ b4, b1 ^ b0, b2 ^ 1, b3 ^ b2, b4]


def expected_nct_outputs(target: str, inputs: list[int]) -> list[int]:
    if target.startswith("aes_"):
        value = sum(bit << (7 - index) for index, bit in enumerate(inputs))
        output = aes_sbox_value(value)
        return [(output >> (7 - index)) & 1 for index in range(8)]
    return ascon_sbox_bits(inputs)


def run_nct_basis_state(
    gates: list[tuple[str, tuple[int, ...]]], state: list[int]
) -> list[int]:
    state = state[:]
    for name, wires in gates:
        if name == "X":
            state[wires[0]] ^= 1
        elif name == "CNOT":
            state[wires[1]] ^= state[wires[0]]
        else:
            state[wires[2]] ^= state[wires[0]] & state[wires[1]]
    return state


def verify_nct_semantics(
    target: str,
    config: dict[str, Any],
    gates: list[tuple[str, tuple[int, ...]]],
    label: str,
) -> None:
    input_width = config["input_width"]
    width = config["width"]
    for value in range(1 << input_width):
        inputs = [(value >> index) & 1 for index in range(input_width)]
        initial = [0] * width
        for wire, bit in enumerate(inputs):
            initial[wire] = bit
        final = run_nct_basis_state(gates, initial)
        outputs = [final[wire] for wire in config["output_coordinate_wires"]]
        expected = expected_nct_outputs(target, inputs)
        if outputs != expected:
            raise VerificationError(
                f"{label}: target mismatch on input {inputs}: {outputs} != {expected}"
            )
        for wire in config["preserved_input_wires"]:
            if final[wire] != initial[wire]:
                raise VerificationError(f"{label}: input wire q[{wire}] is not preserved")
        for wire in config["clean_workspace_wires"]:
            if final[wire] != 0:
                raise VerificationError(f"{label}: workspace wire q[{wire}] is not cleaned")


def verify_nct_record(record: dict[str, Any]) -> dict[str, Any]:
    require_equal(record.get("schema"), "quantum-nct-source-ir/v1", "schema")
    target = record.get("target")
    if target not in NCT_SOURCE_CONFIGS:
        raise VerificationError(f"unsupported NCT target: {target!r}")
    config = NCT_SOURCE_CONFIGS[target]
    verify_provenance(record)
    require_equal(record.get("boundary"), nct_expected_boundary(target, config), "NCT boundary")

    require_equal(record.get("model"), nct_expected_model(config), "NCT model")

    source_circuit = record.get("source_circuit")
    if not isinstance(source_circuit, dict):
        raise VerificationError("source_circuit must be an object")
    require_equal(source_circuit.get("qasm_path"), config["qasm_path"], "NCT QASM path")
    require_equal(
        source_circuit.get("layer_qasm_path"),
        config["layer_qasm_path"],
        "NCT layer QASM path",
    )
    normalization = source_circuit.get("normalization")
    if not isinstance(normalization, dict):
        raise VerificationError("source_circuit.normalization must be an object")
    require_equal(normalization.get("algorithm"), NCT_NORMALIZATION, "NCT normalization")

    raw_path = ROOT / config["qasm_path"]
    layer_path = ROOT / config["layer_qasm_path"]
    raw_gates, _ = parse_nct_qasm(raw_path, config["width"], require_layers=False)
    gates, removed = normalize_nct_gates(raw_gates)
    removed_pairs = {name.lower() + "_pairs": 0 for name in ("X", "CNOT", "Toffoli")}
    for (name, _), count in removed.items():
        removed_pairs[name.lower() + "_pairs"] += count
    require_equal(
        normalization.get("removed_identical_gate_pairs"),
        removed_pairs,
        "NCT cancellation receipt",
    )
    require_equal(
        source_circuit.get("raw_gate_counts"), nct_gate_counts(raw_gates), "raw NCT counts"
    )

    layer_gates, gate_layers = parse_nct_qasm(
        layer_path, config["width"], require_layers=True
    )
    layer_depth, layer_toffoli_depth = verify_nct_layers(layer_gates, gate_layers)
    require_equal(layer_depth, config["layer_full_depth"], "artifact layer depth")
    require_equal(
        layer_toffoli_depth, config["layer_toffoli_depth"], "artifact Toffoli layer count"
    )
    require_equal(
        Counter(canonical_nct_gate(gate) for gate in gates),
        Counter(canonical_nct_gate(gate) for gate in layer_gates),
        "normalized/layer QASM gate multiset",
    )
    verify_nct_semantics(target, config, gates, "normalized source QASM")
    verify_nct_semantics(target, config, layer_gates, "source layer QASM")

    counts = nct_gate_counts(gates)
    full_depth, toffoli_depth = ordered_nct_depths(gates, config["width"])
    expected_resources = {
        "logical_qubits": config["width"],
        "physical_qubits": None,
        "clean_ancillas": config["clean_ancillas"],
        "dirty_ancillas": 0,
        "zero_initialized_output_qubits": config["zero_initialized_output_qubits"],
        "total_gate_count": sum(counts.values()),
        **counts,
        "t_count": None,
        "total_logical_depth": full_depth,
        "cnot_depth": None,
        "toffoli_depth": toffoli_depth,
        "t_depth": None,
        "measurement_rounds": 0,
        "classical_control_operations": 0,
        "topology_overhead": None,
    }
    require_equal(record.get("resources"), expected_resources, "NCT resource vector")
    require_equal(
        source_circuit.get("artifact_layer_resources"),
        {
            "total_logical_depth": layer_depth,
            "toffoli_depth": layer_toffoli_depth,
        },
        "artifact layer resource vector",
    )
    return {
        "id": record.get("id"),
        "kind": "nct",
        "logical_qubits": config["width"],
        **counts,
        "toffoli_depth": toffoli_depth,
        "total_logical_depth": full_depth,
    }


def verify_nct_diagram_record(record: dict[str, Any]) -> dict[str, Any]:
    require_equal(record.get("schema"), "quantum-nct-diagram-source-ir/v1", "schema")
    record_id = record.get("id")
    if record_id not in NCT_DIAGRAM_CONFIGS:
        raise VerificationError(f"unsupported diagram NCT record: {record_id!r}")
    config = NCT_DIAGRAM_CONFIGS[record_id]
    target = record.get("target")
    require_equal(target, config["target"], "diagram NCT target")
    verify_provenance(record)
    require_equal(
        record.get("boundary"),
        nct_diagram_expected_boundary(config),
        "diagram NCT boundary",
    )
    require_equal(
        record.get("model"),
        nct_diagram_expected_model(config),
        "diagram NCT model",
    )

    source_circuit = record.get("source_circuit")
    if not isinstance(source_circuit, dict):
        raise VerificationError("source_circuit must be an object")
    require_equal(
        source_circuit.get("qasm_path"), config["qasm_path"], "diagram NCT QASM path"
    )
    require_equal(
        source_circuit.get("transcription"),
        {
            "source_figure": config["source_figure"],
            "method": "manual_vector_diagram_to_ordered_openqasm_2",
            "same_column_disjoint_gates": "serialized_in_arbitrary_disjoint_order",
        },
        "diagram transcription metadata",
    )

    gates, gate_layers = parse_nct_qasm(
        ROOT / config["qasm_path"], config["width"], require_layers=False
    )
    require_equal(
        gate_layers,
        [None] * len(gates),
        "diagram QASM ordered-gate representation",
    )
    counts = nct_gate_counts(gates)
    counted_resources = {**counts, "total_gate_count": sum(counts.values())}
    require_equal(
        counted_resources,
        config["source_reported_counts"],
        "diagram/source gate counts",
    )

    semantics_config = {
        **config,
        "preserved_input_wires": [],
        "clean_workspace_wires": [],
    }
    verify_nct_semantics(target, semantics_config, gates, "diagram-transcribed QASM")
    for value in range(1 << config["input_width"]):
        inputs = [(value >> index) & 1 for index in range(config["input_width"])]
        initial = inputs + [0] * (config["width"] - config["input_width"])
        final = run_nct_basis_state(gates, initial)
        for wire, input_coordinate in config[
            "garbage_final_input_coordinates"
        ].items():
            if final[wire] != inputs[input_coordinate]:
                raise VerificationError(
                    f"diagram-transcribed QASM: garbage q[{wire}] is not "
                    f"x{input_coordinate} on input {inputs}"
                )

    full_depth, toffoli_depth = ordered_nct_depths(gates, config["width"])
    weighted_depth = weighted_nct_depth(gates, config["width"])
    require_equal(
        weighted_depth,
        config["source_reported_weighted_full_depth"],
        "source weighted full depth",
    )
    expected_source_resources = {
        **config["source_reported_counts"],
        "weighted_full_depth": weighted_depth,
        "weighted_depth_gate_costs": {"X": 1, "CNOT": 1, "Toffoli": 7},
        "weighted_depth_semantics": "ordered_asap_dependency_depth",
    }
    require_equal(
        source_circuit.get("source_reported_resources"),
        expected_source_resources,
        "source-reported diagram resources",
    )

    expected_resources = {
        "logical_qubits": config["width"],
        "physical_qubits": None,
        "zero_initialized_ancillas": len(config["zero_initialized_ancilla_wires"]),
        "clean_ancillas_returned_to_zero": 0,
        "dirty_ancillas": 0,
        "garbage_qubits": len(config["garbage_wires"]),
        "total_gate_count": sum(counts.values()),
        **counts,
        "t_count": None,
        "total_logical_depth": full_depth,
        "cnot_depth": None,
        "toffoli_depth": toffoli_depth,
        "t_depth": None,
        "source_weighted_full_depth": weighted_depth,
        "source_weighted_depth_gate_costs": {"X": 1, "CNOT": 1, "Toffoli": 7},
        "measurement_rounds": 0,
        "classical_control_operations": 0,
        "topology_overhead": None,
    }
    require_equal(record.get("resources"), expected_resources, "diagram NCT resource vector")
    return {
        "id": record_id,
        "kind": "nct",
        "logical_qubits": config["width"],
        **counts,
        "toffoli_depth": toffoli_depth,
        "total_logical_depth": full_depth,
        "source_weighted_full_depth": weighted_depth,
    }


def nct_specialized_expected_boundary() -> dict[str, Any]:
    return {
        "operation": "unitary",
        "basis_semantics": (
            "S_Ascon(x0,x1,x2 xor 1,x3,x4) on computational-basis states"
        ),
        "input_coordinate_wires": list(range(5)),
        "input_coordinate_order": [f"x{index}" for index in range(5)],
        "input_bit_order": "msb0",
        "fixed_input_coordinate_complements": [2],
        "output_coordinate_wires": [4, 0, 3, 2, 1],
        "output_coordinate_order": [f"y{index}" for index in range(5)],
        "output_bit_order": "msb0",
        "preserved_input_wires": [],
        "zero_initialized_ancilla_wires": [],
        "cleaned_ancilla_wires": [],
        "garbage_wires": [],
        "ancilla_cleanup_policy": "not_applicable",
        "terminal_permutation": "explicit_nonidentity",
        "all_circuit_wires": list(range(5)),
    }


def nct_specialized_expected_model() -> dict[str, Any]:
    return {
        "logical_qubits": 5,
        "physical_qubits": None,
        "input_qubits": 5,
        "output_qubits": 5,
        "zero_initialized_ancillas": 0,
        "clean_ancillas_returned_to_zero": 0,
        "dirty_ancillas": 0,
        "garbage_qubits": 0,
        "gate_set": ["X", "CNOT", "Toffoli"],
        "connectivity": "all_to_all",
        "measurements": 0,
        "classical_feed_forward": False,
        "compilation_level": "logical_nct_pre_clifford_t_and_pre_device_mapping",
        "noise_model": None,
        "fault_tolerance_model": None,
    }


def nct_specialized_acceptance_bounds() -> dict[str, Any]:
    return {
        "logical_qubits": 5,
        "zero_initialized_ancillas": 0,
        "dirty_ancillas": 0,
        "garbage_qubits": 0,
        "total_gate_count_at_most": 16,
        "x_count_at_most": 4,
        "cnot_count_at_most": 6,
        "toffoli_count_at_most": 7,
        "toffoli_depth_at_most": 7,
        "total_logical_depth_at_most": 11,
        "source_weighted_full_depth_at_most": 53,
        "measurements_exactly": 0,
    }


def nct_gate_object(gate: tuple[str, tuple[int, ...]]) -> dict[str, Any]:
    name, wires = gate
    if name == "X":
        return {"gate": name, "target": wires[0]}
    if name == "CNOT":
        return {"gate": name, "control": wires[0], "target": wires[1]}
    return {"gate": name, "controls": list(wires[:2]), "target": wires[2]}


def verify_nct_specialized_semantics(
    gates: list[tuple[str, tuple[int, ...]]], label: str
) -> None:
    seen: set[tuple[int, ...]] = set()
    for value in range(32):
        inputs = [(value >> index) & 1 for index in range(5)]
        translated = inputs[:]
        translated[2] ^= 1
        expected = ascon_sbox_bits(translated)
        final = run_nct_basis_state(gates, inputs)
        outputs = [final[wire] for wire in [4, 0, 3, 2, 1]]
        if outputs != expected:
            raise VerificationError(
                f"{label}: target mismatch on input {inputs}: {outputs} != {expected}"
            )
        seen.add(tuple(final))
    require_equal(len(seen), 32, f"{label} permutation size")


def nct_specialized_resources(
    gates: list[tuple[str, tuple[int, ...]]],
) -> dict[str, Any]:
    counts = nct_gate_counts(gates)
    full_depth, toffoli_depth = ordered_nct_depths(gates, 5)
    weighted_depth = weighted_nct_depth(gates, 5)
    return {
        "logical_qubits": 5,
        "physical_qubits": None,
        "zero_initialized_ancillas": 0,
        "clean_ancillas_returned_to_zero": 0,
        "dirty_ancillas": 0,
        "garbage_qubits": 0,
        "total_gate_count": len(gates),
        **counts,
        "t_count": None,
        "total_logical_depth": full_depth,
        "cnot_depth": None,
        "toffoli_depth": toffoli_depth,
        "t_depth": None,
        "source_weighted_full_depth": weighted_depth,
        "source_weighted_depth_gate_costs": {"X": 1, "CNOT": 1, "Toffoli": 7},
        "measurement_rounds": 0,
        "classical_control_operations": 0,
        "topology_overhead": None,
    }


def verify_nct_specialized_record(record: dict[str, Any]) -> dict[str, Any]:
    require_equal(record.get("schema"), "quantum-nct-specialized-ir/v1", "schema")
    record_id = record.get("id")
    if record_id not in NCT_SPECIALIZED_QASMS:
        raise VerificationError(f"unsupported specialized NCT record: {record_id!r}")
    require_equal(record.get("target"), NCT_SPECIALIZED_TARGET, "specialized target")
    verify_provenance(record)
    require_equal(
        record.get("boundary"),
        nct_specialized_expected_boundary(),
        "specialized boundary",
    )
    require_equal(
        record.get("model"), nct_specialized_expected_model(), "specialized model"
    )

    qasm_relative = NCT_SPECIALIZED_QASMS[record_id]
    gates, gate_layers = parse_nct_qasm(ROOT / qasm_relative, 5, require_layers=False)
    require_equal(gate_layers, [None] * len(gates), "specialized ordered QASM")
    circuit = record.get("circuit")
    if not isinstance(circuit, dict):
        raise VerificationError("specialized circuit must be an object")
    require_equal(circuit.get("qasm_path"), qasm_relative, "specialized QASM path")
    require_equal(
        circuit.get("ordered_gates"),
        [nct_gate_object(gate) for gate in gates],
        "specialized ordered gates",
    )
    require_equal(
        circuit.get("schedule"), "ordered ASAP dependency depth", "specialized schedule"
    )
    verify_nct_specialized_semantics(gates, str(record_id))
    resources = nct_specialized_resources(gates)
    require_equal(record.get("resources"), resources, "specialized resources")

    source_record = json.loads(
        (ROOT / NCT_SPECIALIZED_SOURCE_RECORD).read_text(encoding="utf-8")
    )
    if not isinstance(source_record, dict):
        raise VerificationError("specialized source record must be an object")
    verify_nct_diagram_record(source_record)
    source_qasm = NCT_DIAGRAM_CONFIGS[source_record["id"]]["qasm_path"]
    source_gates, _ = parse_nct_qasm(ROOT / source_qasm, 5, require_layers=False)
    construction = record.get("construction")
    if record_id == NCT_SPECIALIZED_BASELINE_ID:
        require_equal(
            construction,
            {
                "method": "prepend fixed X(q2) to Guo Figure 3(c)",
                "source_record_path": NCT_SPECIALIZED_SOURCE_RECORD,
                "fixed_input_coordinate_complements": [2],
            },
            "specialized baseline construction",
        )
        require_equal(gates, [("X", (2,)), *source_gates], "specialized baseline gates")
        require_equal(record.get("acceptance_bounds"), None, "baseline acceptance")
    else:
        baseline_record = json.loads(
            (ROOT / NCT_SPECIALIZED_BASELINE_RECORD).read_text(encoding="utf-8")
        )
        if not isinstance(baseline_record, dict):
            raise VerificationError("specialized predecessor record must be an object")
        verify_nct_specialized_record(baseline_record)
        baseline_qasm = NCT_SPECIALIZED_QASMS[NCT_SPECIALIZED_BASELINE_ID]
        baseline_gates, _ = parse_nct_qasm(
            ROOT / baseline_qasm, 5, require_layers=False
        )
        require_equal(
            baseline_gates[:5],
            [("X", (2,)), ("X", (1,)), ("X", (3,)), ("CNOT", (4, 0)), ("CNOT", (1, 2))],
            "specialized baseline rewrite prefix",
        )
        if set(baseline_gates[4][1]) & set(baseline_gates[2][1]):
            raise VerificationError("specialized CNOT does not commute with X(q3)")
        if set(baseline_gates[4][1]) & set(baseline_gates[3][1]):
            raise VerificationError(
                "specialized CNOT does not commute with CNOT(q4,q0)"
            )
        left = [("X", (2,)), ("X", (1,)), ("CNOT", (1, 2))]
        right = [("CNOT", (1, 2)), ("X", (1,))]
        for value in range(32):
            inputs = [(value >> index) & 1 for index in range(5)]
            require_equal(
                run_nct_basis_state(left, inputs),
                run_nct_basis_state(right, inputs),
                f"specialized prefix identity input {value}",
            )
        require_equal(
            gates,
            [
                baseline_gates[4],
                baseline_gates[1],
                baseline_gates[2],
                baseline_gates[3],
                *baseline_gates[5:],
            ],
            "specialized candidate rewrite",
        )
        require_equal(
            construction,
            {
                "method": "disjoint-prefix commutation plus verified affine identity",
                "direct_predecessor_record_path": NCT_SPECIALIZED_BASELINE_RECORD,
                "commuted_gate": "CNOT(q1,q2)",
                "commuted_across": ["X(q3)", "CNOT(q4,q0)"],
                "affine_identity": "X(q2) X(q1) CNOT(q1,q2) = CNOT(q1,q2) X(q1)",
                "identity_basis_states": 32,
            },
            "specialized candidate construction",
        )
        bounds = nct_specialized_acceptance_bounds()
        require_equal(record.get("acceptance_bounds"), bounds, "specialized bounds")
        for bound_name, resource_name in (
            ("total_gate_count_at_most", "total_gate_count"),
            ("x_count_at_most", "x_count"),
            ("cnot_count_at_most", "cnot_count"),
            ("toffoli_count_at_most", "toffoli_count"),
            ("toffoli_depth_at_most", "toffoli_depth"),
            ("total_logical_depth_at_most", "total_logical_depth"),
            ("source_weighted_full_depth_at_most", "source_weighted_full_depth"),
        ):
            if resources[resource_name] > bounds[bound_name]:
                raise VerificationError(f"specialized candidate exceeds {bound_name}")
        require_equal(
            record["model"]["measurements"],
            bounds["measurements_exactly"],
            "specialized measurements",
        )
        predecessor_resources = baseline_record["resources"]
        require_equal(
            record.get("comparison"),
            {
                "predecessor": NCT_SPECIALIZED_BASELINE_ID,
                "predecessor_record_path": NCT_SPECIALIZED_BASELINE_RECORD,
                "predecessor_resource_vector": predecessor_resources,
                "total_gate_reduction": 1,
                "unchanged_or_improved_metrics": [
                    "logical_qubits",
                    "x_count",
                    "cnot_count",
                    "toffoli_count",
                    "total_gate_count",
                    "toffoli_depth",
                    "total_logical_depth",
                    "source_weighted_full_depth",
                    "measurement_rounds",
                ],
                "optimality_claim": None,
            },
            "specialized comparison",
        )
        if resources["total_gate_count"] >= predecessor_resources["total_gate_count"]:
            raise VerificationError("specialized candidate does not improve gate count")
        for name in (
            "logical_qubits",
            "x_count",
            "cnot_count",
            "toffoli_count",
            "toffoli_depth",
            "total_logical_depth",
            "source_weighted_full_depth",
            "measurement_rounds",
        ):
            if resources[name] > predecessor_resources[name]:
                raise VerificationError(f"specialized candidate worsens {name}")

    return {
        "id": record_id,
        "kind": "nct",
        "logical_qubits": 5,
        "x_count": resources["x_count"],
        "cnot_count": resources["cnot_count"],
        "toffoli_count": resources["toffoli_count"],
        "total_gate_count": resources["total_gate_count"],
        "toffoli_depth": resources["toffoli_depth"],
        "total_logical_depth": resources["total_logical_depth"],
        "source_weighted_full_depth": resources["source_weighted_full_depth"],
    }


def verify_nct_full_permutation_equivalence(
    source: list[tuple[str, tuple[int, ...]]],
    candidate: list[tuple[str, tuple[int, ...]]],
    width: int,
) -> None:
    for value in range(1 << width):
        initial = [(value >> wire) & 1 for wire in range(width)]
        expected = run_nct_basis_state(source, initial)
        actual = run_nct_basis_state(candidate, initial)
        if actual != expected:
            raise VerificationError(
                f"candidate/source full-permutation mismatch on q-state {value:#x}"
            )


def verify_nct_repository_record(record: dict[str, Any]) -> dict[str, Any]:
    require_equal(record.get("schema"), "quantum-nct-repository-ir/v1", "schema")
    record_id = record.get("id")
    if record_id not in NCT_REPOSITORY_CONFIGS:
        raise VerificationError(f"unsupported repository NCT record: {record_id!r}")
    repository_config = NCT_REPOSITORY_CONFIGS[record_id]
    target = record.get("target")
    require_equal(target, repository_config["target"], "repository NCT target")
    if target not in NCT_SOURCE_CONFIGS:
        raise VerificationError(f"unsupported repository NCT source target: {target!r}")
    source_config = NCT_SOURCE_CONFIGS[target]
    verify_provenance(record)
    require_equal(
        record.get("boundary"), nct_expected_boundary(target, source_config), "NCT boundary"
    )

    require_equal(record.get("model"), nct_expected_model(source_config), "NCT model")

    source = record.get("source_predecessor")
    if not isinstance(source, dict):
        raise VerificationError("source_predecessor must be an object")
    source_record_relative = repository_config["source_record_path"]
    require_equal(source.get("record_path"), source_record_relative, "source record path")
    require_equal(
        source.get("normalization_algorithm"), NCT_NORMALIZATION, "source normalization"
    )
    source_record_path = ROOT / source_record_relative
    source_record = json.loads(source_record_path.read_text(encoding="utf-8"))
    if not isinstance(source_record, dict):
        raise VerificationError("source predecessor record root must be an object")
    source_summary = verify_nct_record(source_record)
    require_equal(source.get("resources"), source_record.get("resources"), "source resources")

    direct_resources: dict[str, Any] | None = None
    direct_relative = repository_config.get("direct_predecessor_record_path")
    direct = record.get("direct_predecessor")
    if direct_relative is None:
        require_equal(direct, None, "direct predecessor")
    else:
        if not isinstance(direct, dict):
            raise VerificationError("direct_predecessor must be an object")
        require_equal(direct.get("record_path"), direct_relative, "direct predecessor path")
        direct_record = json.loads((ROOT / direct_relative).read_text(encoding="utf-8"))
        if not isinstance(direct_record, dict):
            raise VerificationError("direct predecessor record root must be an object")
        verify_nct_repository_record(direct_record)
        direct_resources = direct_record.get("resources")
        if not isinstance(direct_resources, dict):
            raise VerificationError("direct predecessor resources must be an object")
        require_equal(direct.get("resources"), direct_resources, "direct predecessor resources")

    raw_source, _ = parse_nct_qasm(
        ROOT / source_config["qasm_path"], source_config["width"], require_layers=False
    )
    normalized_source, _ = normalize_nct_gates(raw_source)

    candidate = record.get("candidate_circuit")
    if not isinstance(candidate, dict):
        raise VerificationError("candidate_circuit must be an object")
    candidate_relative = repository_config["candidate_qasm_path"]
    require_equal(candidate.get("qasm_path"), candidate_relative, "candidate QASM path")
    require_equal(
        candidate.get("full_source_permutation_equivalence_basis_states"),
        1 << source_config["width"],
        "full source equivalence coverage",
    )
    candidate_gates, candidate_layers = parse_nct_qasm(
        ROOT / candidate_relative, source_config["width"], require_layers=False
    )
    require_equal(
        candidate_layers,
        [None] * len(candidate_gates),
        "candidate QASM ordered-gate representation",
    )
    verify_nct_full_permutation_equivalence(
        normalized_source, candidate_gates, source_config["width"]
    )
    verify_nct_semantics(target, source_config, candidate_gates, "repository candidate QASM")

    counts = nct_gate_counts(candidate_gates)
    full_depth, toffoli_depth = ordered_nct_depths(
        candidate_gates, source_config["width"]
    )
    expected_resources = {
        "logical_qubits": source_config["width"],
        "physical_qubits": None,
        "clean_ancillas": source_config["clean_ancillas"],
        "dirty_ancillas": 0,
        "zero_initialized_output_qubits": source_config["zero_initialized_output_qubits"],
        "total_gate_count": sum(counts.values()),
        **counts,
        "t_count": None,
        "total_logical_depth": full_depth,
        "cnot_depth": None,
        "toffoli_depth": toffoli_depth,
        "t_depth": None,
        "measurement_rounds": 0,
        "classical_control_operations": 0,
        "topology_overhead": None,
    }
    require_equal(record.get("resources"), expected_resources, "NCT resource vector")

    acceptance = repository_config["acceptance_bounds"]
    require_equal(record.get("acceptance_bounds"), acceptance, "acceptance bounds")
    bounded_values = {
        "logical_qubits_at_most": expected_resources["logical_qubits"],
        "clean_ancillas_at_most": expected_resources["clean_ancillas"],
        "x_count_at_most": expected_resources["x_count"],
        "cnot_count_at_most": expected_resources["cnot_count"],
        "toffoli_count_at_most": expected_resources["toffoli_count"],
        "toffoli_depth_at_most": expected_resources["toffoli_depth"],
        "total_logical_depth_at_most": expected_resources["total_logical_depth"],
    }
    for name, actual in bounded_values.items():
        if actual > acceptance[name]:
            raise VerificationError(f"candidate exceeds {name}: {actual} > {acceptance[name]}")
    require_equal(expected_resources["dirty_ancillas"], acceptance["dirty_ancillas"], "dirty ancillas")
    require_equal(record["model"]["measurements"], acceptance["measurements"], "measurements")
    if counts["toffoli_count"] >= source_summary["toffoli_count"]:
        raise VerificationError("candidate does not strictly improve source Toffoli count")
    if direct_resources is not None:
        comparable_metrics = (
            "logical_qubits",
            "clean_ancillas",
            "dirty_ancillas",
            "x_count",
            "cnot_count",
            "toffoli_count",
            "total_gate_count",
            "toffoli_depth",
            "total_logical_depth",
            "measurement_rounds",
            "classical_control_operations",
        )
        for name in comparable_metrics:
            if expected_resources[name] > direct_resources[name]:
                raise VerificationError(
                    f"candidate worsens direct predecessor {name}: "
                    f"{expected_resources[name]} > {direct_resources[name]}"
                )
        if expected_resources["toffoli_count"] >= direct_resources["toffoli_count"]:
            raise VerificationError("candidate does not strictly improve direct predecessor Toffoli count")

    return {
        "id": record.get("id"),
        "kind": "nct",
        "logical_qubits": source_config["width"],
        **counts,
        "toffoli_depth": toffoli_depth,
        "total_logical_depth": full_depth,
    }


def verify_nct_derived_record(record: dict[str, Any]) -> dict[str, Any]:
    require_equal(record.get("schema"), "quantum-nct-derived-ir/v1", "schema")
    record_id = record.get("id")
    if record_id not in NCT_DERIVED_CONFIGS:
        raise VerificationError(f"unsupported derived NCT record: {record_id!r}")
    derived_config = NCT_DERIVED_CONFIGS[record_id]
    target = record.get("target")
    require_equal(target, derived_config["target"], "derived NCT target")
    if target not in NCT_SOURCE_CONFIGS:
        raise VerificationError(f"unsupported derived NCT source target: {target!r}")
    config = NCT_SOURCE_CONFIGS[target]
    verify_provenance(record)
    require_equal(record.get("boundary"), nct_expected_boundary(target, config), "NCT boundary")
    require_equal(record.get("model"), nct_expected_model(config), "NCT model")

    construction = record.get("construction")
    if not isinstance(construction, dict):
        raise VerificationError("derived NCT construction must be an object")
    for name, expected in derived_config["construction_requirements"].items():
        require_equal(
            construction.get(name), expected, f"derived NCT construction {name}"
        )

    gates, gate_layers = parse_nct_ir_layers(record.get("layers"), config["width"])
    layer_depth, layer_toffoli_depth = verify_nct_layers(gates, gate_layers)
    full_depth, toffoli_depth = ordered_nct_depths(gates, config["width"])
    require_equal(full_depth, layer_depth, "derived NCT canonical ASAP depth")
    require_equal(
        toffoli_depth,
        layer_toffoli_depth,
        "derived NCT ordered/layer Toffoli depth",
    )
    verify_nct_semantics(target, config, gates, "derived NCT layers")

    counts = nct_gate_counts(gates)
    expected_resources = {
        "logical_qubits": config["width"],
        "physical_qubits": None,
        "clean_ancillas": config["clean_ancillas"],
        "dirty_ancillas": 0,
        "zero_initialized_output_qubits": config["zero_initialized_output_qubits"],
        "total_gate_count": sum(counts.values()),
        **counts,
        "t_count": None,
        "total_logical_depth": layer_depth,
        "cnot_depth": None,
        "toffoli_depth": layer_toffoli_depth,
        "t_depth": None,
        "measurement_rounds": 0,
        "classical_control_operations": 0,
        "topology_overhead": None,
    }
    require_equal(record.get("resources"), expected_resources, "derived NCT resource vector")

    expected_acceptance = derived_config["acceptance_bounds"]
    require_equal(record.get("acceptance_bounds"), expected_acceptance, "acceptance bounds")
    if counts["x_count"] > expected_acceptance["x_count_at_most"]:
        raise VerificationError("derived NCT X count exceeds acceptance bound")
    if counts["cnot_count"] > expected_acceptance["cnot_count_at_most"]:
        raise VerificationError("derived NCT CNOT count exceeds acceptance bound")
    if (
        "total_gate_count_at_most" in expected_acceptance
        and expected_resources["total_gate_count"]
        > expected_acceptance["total_gate_count_at_most"]
    ):
        raise VerificationError("derived NCT total gate count exceeds acceptance bound")
    require_equal(
        counts["toffoli_count"],
        expected_acceptance["toffoli_count_exactly"],
        "accepted Toffoli count",
    )
    if layer_toffoli_depth > expected_acceptance["toffoli_depth_at_most"]:
        raise VerificationError("derived NCT Toffoli depth exceeds acceptance bound")
    if layer_depth > expected_acceptance["total_logical_depth_at_most"]:
        raise VerificationError("derived NCT full depth exceeds acceptance bound")
    require_equal(
        record["model"]["measurements"],
        expected_acceptance["measurements_exactly"],
        "derived NCT measurements",
    )

    predecessor_relative = derived_config.get("direct_predecessor_record_path")
    if predecessor_relative is not None:
        comparison = record.get("comparison")
        if not isinstance(comparison, dict):
            raise VerificationError("derived NCT comparison must be an object")
        require_equal(
            comparison.get("predecessor_record_path"),
            predecessor_relative,
            "derived NCT predecessor path",
        )
        predecessor_record = json.loads(
            (ROOT / predecessor_relative).read_text(encoding="utf-8")
        )
        if not isinstance(predecessor_record, dict):
            raise VerificationError("derived NCT predecessor root must be an object")
        predecessor_summary = verify_nct_derived_record(predecessor_record)
        require_equal(
            comparison.get("predecessor"),
            predecessor_record.get("id"),
            "derived NCT predecessor id",
        )
        predecessor_resources = predecessor_record.get("resources")
        if not isinstance(predecessor_resources, dict):
            raise VerificationError("derived NCT predecessor resources must be an object")
        predecessor_vector = {
            name: predecessor_resources[name]
            for name in (
                "logical_qubits",
                "x_count",
                "cnot_count",
                "toffoli_count",
                "total_gate_count",
                "toffoli_depth",
                "total_logical_depth",
            )
        }
        require_equal(
            comparison.get("predecessor_resource_vector"),
            predecessor_vector,
            "derived NCT predecessor resource vector",
        )
        comparable_metrics = (
            "logical_qubits",
            "clean_ancillas",
            "dirty_ancillas",
            "zero_initialized_output_qubits",
            "x_count",
            "cnot_count",
            "toffoli_count",
            "total_gate_count",
            "toffoli_depth",
            "total_logical_depth",
            "measurement_rounds",
            "classical_control_operations",
        )
        for name in comparable_metrics:
            if expected_resources[name] > predecessor_resources[name]:
                raise VerificationError(
                    f"derived NCT candidate worsens predecessor {name}: "
                    f"{expected_resources[name]} > {predecessor_resources[name]}"
                )
        if counts["cnot_count"] >= predecessor_summary["cnot_count"]:
            raise VerificationError(
                "derived NCT candidate does not strictly improve predecessor CNOT count"
            )
        require_equal(
            comparison.get("cnot_reduction"),
            predecessor_summary["cnot_count"] - counts["cnot_count"],
            "derived NCT CNOT reduction",
        )
        require_equal(
            comparison.get("total_gate_reduction"),
            predecessor_resources["total_gate_count"] - expected_resources["total_gate_count"],
            "derived NCT total-gate reduction",
        )
        require_equal(
            comparison.get("logical_depth_reduction"),
            predecessor_resources["total_logical_depth"] - layer_depth,
            "derived NCT logical-depth reduction",
        )

    return {
        "id": record.get("id"),
        "kind": "nct",
        "logical_qubits": config["width"],
        **counts,
        "toffoli_depth": layer_toffoli_depth,
        "total_logical_depth": layer_depth,
    }


KEYED_AES_WIDTH = 68
KEYED_AES_SBOX_OUTPUT_WIRES = (4, 2, 0, 1, 3, 5, 6, 7)
KEYED_AES_SBOX_RECORD = "ir/results/quantum/aes_sbox_repository_width9_829toffoli.json"
KEYED_AES_SBOX_QASM = "ir/results/quantum/aes_sbox_repository_width9_829toffoli.qasm"
KEYED_AES_MIX_RECORD = "ir/baselines/quantum/aes_mixcolumns_repository_105cnot_depth10.json"
KEYED_AES_RECORDS: dict[str, dict[str, Any]] = {
    "aes_keyed_subbytes_mixcolumns_column_3669cnot": {
        "role": "baseline",
        "qasm_path": "ir/baselines/quantum/aes_keyed_subbytes_mixcolumns_column_3669cnot.qasm",
        "tail_cnot_count": 117,
        "expected_resources": {
            "x_count": 932,
            "cnot_count": 3669,
            "toffoli_count": 3316,
            "total_gate_count": 7917,
            "toffoli_depth": 789,
            "total_logical_depth": 1592,
        },
    },
    "aes_keyed_subbytes_mixcolumns_column_3668cnot": {
        "role": "candidate",
        "qasm_path": "ir/results/quantum/aes_keyed_subbytes_mixcolumns_column_3668cnot.qasm",
        "tail_cnot_count": 116,
    },
}


def keyed_aes_physical_state_wire(logical_lsb0_wire: int) -> int:
    byte, exponent = divmod(logical_lsb0_wire, 8)
    return 8 * byte + KEYED_AES_SBOX_OUTPUT_WIRES[7 - exponent]


def keyed_aes_expected_boundary() -> dict[str, Any]:
    return {
        "operation": "isometry",
        "basis_semantics": (
            "|a>|0^4>|k> -> |MixColumns(SubBytes(a)) xor k>|0^4>|k>"
        ),
        "state_input_physical_wires": list(range(32)),
        "state_input_byte_order": ["s0", "s1", "s2", "s3"],
        "state_input_bit_order_within_byte": "msb0",
        "state_input_wire_definition": (
            "q[8*j+i] is AES input coordinate x_i of byte s[j]"
        ),
        "shiftrows_boundary": (
            "declared free input-byte placement; s0,s1,s2,s3 are already one post-ShiftRows column"
        ),
        "sbox_output_msb0_local_wires": list(KEYED_AES_SBOX_OUTPUT_WIRES),
        "state_output_logical_lsb0_physical_wires": [
            keyed_aes_physical_state_wire(wire) for wire in range(32)
        ],
        "state_output_byte_order": ["t0", "t1", "t2", "t3"],
        "state_output_bit_order_within_byte": "lsb0",
        "round_key_input_wires": list(range(36, 68)),
        "round_key_output_wires": list(range(36, 68)),
        "round_key_bit_order_within_byte": "lsb0",
        "round_key_wire_definition": (
            "q[36+8*j+k] is coefficient x^k of arbitrary round-key byte k[j]"
        ),
        "round_key_preserved": True,
        "clean_workspace_wires": list(range(32, 36)),
        "clean_workspace_initial_state": "zero",
        "clean_workspace_final_state": "zero",
        "terminal_permutation": "explicit_nonidentity_state_coordinate_mapping",
        "all_circuit_wires": list(range(KEYED_AES_WIDTH)),
    }


def keyed_aes_expected_model() -> dict[str, Any]:
    return {
        "logical_qubits": KEYED_AES_WIDTH,
        "physical_qubits": None,
        "state_input_qubits": 32,
        "round_key_input_qubits": 32,
        "output_qubits": 64,
        "clean_ancillas": 4,
        "dirty_ancillas": 0,
        "gate_set": ["X", "CNOT", "Toffoli"],
        "connectivity": "all_to_all",
        "measurements": 0,
        "classical_feed_forward": False,
        "compilation_level": "logical_nct_pre_clifford_t_and_pre_device_mapping",
        "noise_model": None,
        "fault_tolerance_model": None,
    }


def keyed_aes_objective_bounds() -> dict[str, int]:
    return {
        "logical_qubits_at_most": 68,
        "clean_ancillas_at_most": 4,
        "dirty_ancillas": 0,
        "x_count_at_most": 932,
        "cnot_count_at_most": 3668,
        "toffoli_count_at_most": 3316,
        "toffoli_depth_at_most": 789,
        "total_logical_depth_at_most": 1592,
        "measurements": 0,
    }


def parse_keyed_aes_tail_layers(raw_layers: Any) -> list[list[tuple[int, int]]]:
    if not isinstance(raw_layers, list) or len(raw_layers) != 13:
        raise VerificationError("keyed AES tail must contain exactly 13 layers")
    layers: list[list[tuple[int, int]]] = []
    for layer_index, raw_layer in enumerate(raw_layers):
        if not isinstance(raw_layer, list):
            raise VerificationError(f"keyed AES tail layer {layer_index} is not a list")
        used: set[int] = set()
        layer: list[tuple[int, int]] = []
        for raw_gate in raw_layer:
            if (
                not isinstance(raw_gate, list)
                or len(raw_gate) != 2
                or any(not isinstance(wire, int) for wire in raw_gate)
            ):
                raise VerificationError(
                    f"keyed AES tail layer {layer_index} has a malformed CNOT"
                )
            control, target = raw_gate
            if not 0 <= control < 32 or not 0 <= target < 32 or control == target:
                raise VerificationError(
                    f"keyed AES tail layer {layer_index} has an invalid CNOT"
                )
            if control in used or target in used:
                raise VerificationError(
                    f"keyed AES tail layer {layer_index} reuses a qubit"
                )
            used.update((control, target))
            layer.append((control, target))
        layers.append(layer)
    return layers


def keyed_aes_tail_rows(layers: list[list[tuple[int, int]]]) -> list[int]:
    rows = [1 << wire for wire in range(32)]
    for layer in layers:
        before = rows[:]
        for control, target in layer:
            rows[target] = before[target] ^ before[control]
    return rows


def keyed_aes_map_sbox_gate(
    byte: int, gate: tuple[str, tuple[int, ...]]
) -> tuple[str, tuple[int, ...]]:
    name, wires = gate
    mapped = tuple(32 + byte if wire == 8 else 8 * byte + wire for wire in wires)
    return name, mapped


def keyed_aes_component_data() -> dict[str, Any]:
    sbox_record = json.loads((ROOT / KEYED_AES_SBOX_RECORD).read_text(encoding="utf-8"))
    verify_nct_repository_record(sbox_record)
    mix_record = json.loads((ROOT / KEYED_AES_MIX_RECORD).read_text(encoding="utf-8"))
    verify_mixcolumns_record(mix_record)

    sbox_gates, _ = parse_nct_qasm(
        ROOT / KEYED_AES_SBOX_QASM, 9, require_layers=False
    )
    last_toffoli = max(
        index for index, (name, _) in enumerate(sbox_gates) if name == "Toffoli"
    )
    prefix = sbox_gates[: last_toffoli + 1]
    suffix = sbox_gates[last_toffoli + 1 :]
    require_equal(
        suffix,
        [
            ("CNOT", (4, 3)),
            ("CNOT", (0, 4)),
            ("CNOT", (4, 1)),
            ("X", (0,)),
        ],
        "width-nine S-box terminal affine suffix",
    )
    if any(8 in wires for _, wires in suffix):
        raise VerificationError("S-box suffix unexpectedly touches the workspace")

    mix_layers: list[list[tuple[int, int]]] = []
    for raw_layer in mix_record["layers"]:
        layer = [
            (
                keyed_aes_physical_state_wire(control),
                keyed_aes_physical_state_wire(target),
            )
            for control, target in raw_layer
        ]
        mix_layers.append(layer)
    baseline_layers = [
        [(8 * byte + 4, 8 * byte + 3) for byte in range(4)],
        [(8 * byte + 0, 8 * byte + 4) for byte in range(4)],
        [(8 * byte + 4, 8 * byte + 1) for byte in range(4)],
        *mix_layers,
    ]
    if sum(map(len, baseline_layers)) != 117:
        raise VerificationError("baseline keyed AES tail does not contain 117 CNOTs")
    parse_keyed_aes_tail_layers(
        [[list(gate) for gate in layer] for layer in baseline_layers]
    )

    constants = [0] * 32
    for byte in range(4):
        for name, wires in suffix:
            mapped = keyed_aes_map_sbox_gate(byte, (name, wires))[1]
            if name == "CNOT":
                constants[mapped[1]] ^= constants[mapped[0]]
            elif name == "X":
                constants[mapped[0]] ^= 1
            else:
                raise VerificationError("S-box affine suffix contains a nonlinear gate")
    for layer in mix_layers:
        before = constants[:]
        for control, target in layer:
            constants[target] = before[target] ^ before[control]
    constant_wires = [wire for wire, value in enumerate(constants) if value]
    require_equal(
        constant_wires,
        [0, 8, 16, 24],
        "derived keyed AES affine-tail constant",
    )
    return {
        "prefix": prefix,
        "suffix": suffix,
        "mix_layers": mix_layers,
        "baseline_layers": baseline_layers,
        "baseline_rows": keyed_aes_tail_rows(baseline_layers),
        "baseline_constant_wires": constant_wires,
    }


def verify_keyed_aes_column_record(record: dict[str, Any]) -> dict[str, Any]:
    require_equal(
        record.get("schema"), "quantum-nct-keyed-aes-column-ir/v1", "schema"
    )
    record_id = record.get("id")
    if record_id not in KEYED_AES_RECORDS:
        raise VerificationError(f"unsupported keyed AES column record: {record_id!r}")
    config = KEYED_AES_RECORDS[record_id]
    require_equal(
        record.get("target"),
        "aes_keyed_subbytes_mixcolumns_column",
        "keyed AES target",
    )
    verify_provenance(record)
    require_equal(record.get("boundary"), keyed_aes_expected_boundary(), "keyed AES boundary")
    require_equal(record.get("model"), keyed_aes_expected_model(), "keyed AES model")
    require_equal(
        record.get("objective_bounds"),
        keyed_aes_objective_bounds(),
        "keyed AES objective bounds",
    )

    components = keyed_aes_component_data()
    construction = record.get("construction")
    if not isinstance(construction, dict):
        raise VerificationError("keyed AES construction must be an object")
    require_equal(construction.get("role"), config["role"], "construction role")
    require_equal(
        construction.get("qasm_path"), config["qasm_path"], "construction QASM path"
    )
    require_equal(
        construction.get("qasm_sha256"),
        sha256(ROOT / config["qasm_path"]),
        "construction QASM hash",
    )
    require_equal(
        construction.get("sbox_record_path"),
        KEYED_AES_SBOX_RECORD,
        "construction S-box record",
    )
    require_equal(
        construction.get("sbox_qasm_path"),
        KEYED_AES_SBOX_QASM,
        "construction S-box QASM",
    )
    require_equal(construction.get("sbox_instances"), 4, "S-box instance count")
    require_equal(
        construction.get("mixcolumns_record_path"),
        KEYED_AES_MIX_RECORD,
        "construction MixColumns record",
    )
    require_equal(construction.get("tail_cnot_depth"), 13, "tail CNOT depth")
    require_equal(
        construction.get("tail_cnot_count"),
        config["tail_cnot_count"],
        "tail CNOT count",
    )
    tail_layers = parse_keyed_aes_tail_layers(construction.get("tail_layers"))
    require_equal(
        sum(map(len, tail_layers)), config["tail_cnot_count"], "tail layer gate count"
    )
    require_equal(
        keyed_aes_tail_rows(tail_layers),
        components["baseline_rows"],
        "joint affine-tail matrix",
    )
    require_equal(
        construction.get("tail_matrix_rows"),
        [f"0x{row:08x}" for row in components["baseline_rows"]],
        "declared tail matrix rows",
    )
    require_equal(
        construction.get("tail_output_constant_physical_wires"),
        components["baseline_constant_wires"],
        "tail affine constant",
    )
    key_pairs = [
        [36 + logical_wire, keyed_aes_physical_state_wire(logical_wire)]
        for logical_wire in range(32)
    ]
    require_equal(
        construction.get("add_round_key_cnot_pairs"),
        key_pairs,
        "variable AddRoundKey shell",
    )

    qasm_gates, _ = parse_nct_qasm(
        ROOT / config["qasm_path"], KEYED_AES_WIDTH, require_layers=False
    )
    prefix_gates = [
        keyed_aes_map_sbox_gate(byte, gate)
        for byte in range(4)
        for gate in components["prefix"]
    ]
    key_gates = [("CNOT", tuple(pair)) for pair in key_pairs]
    if config["role"] == "baseline":
        expected_gates = [
            *prefix_gates,
            *[
                keyed_aes_map_sbox_gate(byte, gate)
                for byte in range(4)
                for gate in components["suffix"]
            ],
            *[
                ("CNOT", gate)
                for layer in components["mix_layers"]
                for gate in layer
            ],
            *key_gates,
        ]
        require_equal(tail_layers, components["baseline_layers"], "baseline tail layers")
    else:
        expected_gates = [
            *prefix_gates,
            *[("CNOT", gate) for layer in tail_layers for gate in layer],
            *[("X", (wire,)) for wire in components["baseline_constant_wires"]],
            *key_gates,
        ]
    require_equal(qasm_gates, expected_gates, "complete keyed AES QASM composition")

    counts = nct_gate_counts(qasm_gates)
    full_depth, toffoli_depth = ordered_nct_depths(qasm_gates, KEYED_AES_WIDTH)
    expected_resources = {
        "logical_qubits": KEYED_AES_WIDTH,
        "physical_qubits": None,
        "clean_ancillas": 4,
        "dirty_ancillas": 0,
        "zero_initialized_output_qubits": 0,
        "total_gate_count": sum(counts.values()),
        **counts,
        "t_count": None,
        "total_logical_depth": full_depth,
        "cnot_depth": None,
        "toffoli_depth": toffoli_depth,
        "t_depth": None,
        "measurement_rounds": 0,
        "classical_control_operations": 0,
        "topology_overhead": None,
    }
    require_equal(record.get("resources"), expected_resources, "keyed AES resources")

    if config["role"] == "baseline":
        for name, expected in config["expected_resources"].items():
            require_equal(expected_resources[name], expected, f"baseline {name}")
        if "comparison" in record:
            raise VerificationError("baseline record must not contain a comparison")
    else:
        bounds = keyed_aes_objective_bounds()
        bounded = {
            "logical_qubits_at_most": expected_resources["logical_qubits"],
            "clean_ancillas_at_most": expected_resources["clean_ancillas"],
            "x_count_at_most": expected_resources["x_count"],
            "cnot_count_at_most": expected_resources["cnot_count"],
            "toffoli_count_at_most": expected_resources["toffoli_count"],
            "toffoli_depth_at_most": expected_resources["toffoli_depth"],
            "total_logical_depth_at_most": expected_resources["total_logical_depth"],
        }
        for name, actual in bounded.items():
            if actual > bounds[name]:
                raise VerificationError(
                    f"keyed AES candidate exceeds {name}: {actual} > {bounds[name]}"
                )
        require_equal(expected_resources["dirty_ancillas"], bounds["dirty_ancillas"], "dirty ancillas")
        require_equal(record["model"]["measurements"], bounds["measurements"], "measurements")

        baseline_relative = "ir/baselines/quantum/aes_keyed_subbytes_mixcolumns_column_3669cnot.json"
        baseline_record = json.loads((ROOT / baseline_relative).read_text(encoding="utf-8"))
        baseline_summary = verify_keyed_aes_column_record(baseline_record)
        comparison = record.get("comparison")
        if not isinstance(comparison, dict):
            raise VerificationError("candidate comparison must be an object")
        require_equal(
            comparison.get("predecessor"),
            baseline_record.get("id"),
            "candidate predecessor id",
        )
        require_equal(
            comparison.get("predecessor_record_path"),
            baseline_relative,
            "candidate predecessor path",
        )
        require_equal(
            comparison.get("predecessor_resource_vector"),
            baseline_record.get("resources"),
            "candidate predecessor resources",
        )
        baseline_resources = baseline_record["resources"]
        for name in (
            "logical_qubits",
            "clean_ancillas",
            "dirty_ancillas",
            "x_count",
            "cnot_count",
            "toffoli_count",
            "total_gate_count",
            "toffoli_depth",
            "total_logical_depth",
            "measurement_rounds",
            "classical_control_operations",
        ):
            if expected_resources[name] > baseline_resources[name]:
                raise VerificationError(
                    f"keyed AES candidate worsens {name}: "
                    f"{expected_resources[name]} > {baseline_resources[name]}"
                )
        if counts["cnot_count"] >= baseline_summary["cnot_count"]:
            raise VerificationError("keyed AES candidate does not reduce CNOT count")
        require_equal(
            comparison.get("cnot_reduction"),
            baseline_resources["cnot_count"] - counts["cnot_count"],
            "candidate CNOT reduction",
        )
        require_equal(
            comparison.get("total_gate_reduction"),
            baseline_resources["total_gate_count"] - expected_resources["total_gate_count"],
            "candidate total-gate reduction",
        )
        require_equal(
            comparison.get("logical_depth_change"),
            full_depth - baseline_resources["total_logical_depth"],
            "candidate logical-depth change",
        )

    return {
        "id": record_id,
        "kind": "nct",
        "logical_qubits": KEYED_AES_WIDTH,
        **counts,
        "toffoli_depth": toffoli_depth,
        "total_logical_depth": full_depth,
    }


def verify_record(path: Path) -> dict[str, Any]:
    record = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(record, dict):
        raise VerificationError("record root must be an object")
    schema = record.get("schema")
    if schema == "quantum-circuit-ir/v1":
        return verify_mixcolumns_record(record)
    if schema == "quantum-affine-circuit-ir/v1":
        return verify_affine_record(record)
    if schema == "quantum-ascon-linear-copy-source-ir/v1":
        return verify_ascon_linear_copy_record(record)
    if schema == "quantum-ascon-linear-inplace-derived-ir/v1":
        return verify_ascon_linear_embedded_record(record)
    if schema == "quantum-ascon-linear-inplace-rewrite-ir/v1":
        return verify_ascon_linear_embedded_record(record)
    if schema == "quantum-ascon-round-core-derived-ir/v1":
        return verify_ascon_round_core_record(record)
    if schema == "quantum-nct-source-ir/v1":
        return verify_nct_record(record)
    if schema == "quantum-nct-diagram-source-ir/v1":
        return verify_nct_diagram_record(record)
    if schema == "quantum-nct-specialized-ir/v1":
        return verify_nct_specialized_record(record)
    if schema == "quantum-nct-repository-ir/v1":
        return verify_nct_repository_record(record)
    if schema == "quantum-nct-derived-ir/v1":
        return verify_nct_derived_record(record)
    if schema == "quantum-nct-keyed-aes-column-ir/v1":
        return verify_keyed_aes_column_record(record)
    raise VerificationError(f"unsupported quantum IR schema: {schema!r}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("paths", nargs="*", type=Path)
    args = parser.parse_args()
    paths = args.paths or sorted(
        path for directory in DEFAULT_IR_DIRS for path in directory.glob("*.json")
    )
    if not paths:
        print("no quantum IR records found", file=sys.stderr)
        return 2
    failed = False
    for supplied in paths:
        path = supplied if supplied.is_absolute() else ROOT / supplied
        try:
            result = verify_record(path)
            if result.get("kind") == "dynamic_qand":
                print(
                    f"verified {path.relative_to(ROOT)}: "
                    f"{result['logical_qubits']} qubits, "
                    f"{result['t_count']} T/Tdagger, "
                    f"T depth {result['t_depth']}, "
                    f"{result['measurements']} measurements, "
                    f"full depth {result['total_logical_depth']}"
                )
            elif result.get("kind") == "nct":
                weighted_text = ""
                if "source_weighted_full_depth" in result:
                    weighted_text = (
                        f", source-weighted depth {result['source_weighted_full_depth']}"
                    )
                print(
                    f"verified {path.relative_to(ROOT)}: {result['logical_qubits']} qubits, "
                    f"{result['x_count']} X, {result['cnot_count']} CNOT, "
                    f"{result['toffoli_count']} Toffoli, Toffoli depth "
                    f"{result['toffoli_depth']}, full depth "
                    f"{result['total_logical_depth']}{weighted_text}"
                )
            else:
                depth_text = f"CNOT depth {result['cnot_depth']}"
                if result["total_logical_depth"] != result["cnot_depth"]:
                    depth_text += f", full depth {result['total_logical_depth']}"
                print(
                    f"verified {path.relative_to(ROOT)}: "
                    f"{result['cnot_count']} CNOT, {depth_text}"
                )
        except (OSError, json.JSONDecodeError, VerificationError) as exc:
            failed = True
            print(f"FAILED {path}: {exc}", file=sys.stderr)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
