#!/usr/bin/env python3
"""Verify the published logical quantum and reversible circuit IR records.

Several deliberately narrow schema families are supported: fixed 32-qubit AES
MixColumns CNOT circuits, the 26-qubit AES S-box affine-output boundary over
CNOT/X, source-pinned AES/Ascon NCT circuits, and target-specific
repository-derived NCT circuits at pinned source boundaries. The verifier
checks retained provenance hashes when the referenced artifact is included,
fixed wire order, ancilla initialization and cleanup,
complete disjoint-layer schedules when supplied, independently declared
basis-state semantics, and full logical resource vectors. It does not infer
device routing, noise, fidelity, or fault-tolerant cost.
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
        if re.fullmatch(r"[0-9a-f]{64}", expected_hash) is None:
            raise VerificationError(f"provenance file {index} has invalid SHA-256")
        path = ROOT / relative
        if not path.is_file():
            raise VerificationError(f"provenance file is not included: {relative}")
        actual_hash = sha256(path)
        if actual_hash != expected_hash:
            raise VerificationError(
                f"provenance hash mismatch for {relative}: {actual_hash} != {expected_hash}"
            )
    if not isinstance(provenance.get("evidence_locator"), str):
        raise VerificationError("provenance.evidence_locator must be a string")


def parse_layers(raw_layers: Any) -> list[list[tuple[int, int]]]:
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
            if not 0 <= control < QUBITS or not 0 <= target < QUBITS:
                raise VerificationError(f"layer {layer_index} gate {gate_index} is out of range")
            if control == target:
                raise VerificationError(f"layer {layer_index} gate {gate_index} is a self-CNOT")
            if control in used or target in used:
                raise VerificationError(f"layer {layer_index} reuses a qubit")
            used.update((control, target))
            layer.append((control, target))
        layers.append(layer)
    return layers


def circuit_rows(layers: list[list[tuple[int, int]]]) -> list[int]:
    rows = [1 << index for index in range(QUBITS)]
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

NCT_REPOSITORY_CONFIGS: dict[str, dict[str, Any]] = {
    "ascon_sbox_repository_width5_7toffoli_34cnot_depth41": {
        "target": "ascon_sbox_forward_minimal_width_nct",
        "source_record_path": "ir/baselines/quantum/ascon_sbox_huang_zhang_lin_width5_nct.json",
        "candidate_qasm_path": "ir/results/quantum/ascon_sbox_repository_width5_7toffoli_34cnot_depth41.qasm",
        "acceptance_bounds": {
            "logical_qubits_at_most": 5,
            "clean_ancillas_at_most": 0,
            "dirty_ancillas": 0,
            "x_count_at_most": 8,
            "cnot_count_at_most": 34,
            "toffoli_count_at_most": 7,
            "toffoli_depth_at_most": 7,
            "total_logical_depth_at_most": 41,
            "measurements": 0,
        },
        "strict_source_improvement_metrics": (
            "x_count",
            "cnot_count",
            "total_gate_count",
            "total_logical_depth",
        ),
    },
    "aes_sbox_repository_width9_832toffoli": {
        "target": "aes_sbox_forward_minimal_width_nct",
        "source_record_path": "ir/baselines/quantum/aes_sbox_huang_zhang_lin_width9_nct.json",
        "candidate_qasm_path": "ir/baselines/quantum/aes_sbox_repository_width9_832toffoli.qasm",
        "acceptance_bounds": {
            "logical_qubits_at_most": 9,
            "clean_ancillas_at_most": 1,
            "dirty_ancillas": 0,
            "x_count_at_most": 233,
            "cnot_count_at_most": 885,
            "toffoli_count_at_most": 832,
            "toffoli_depth_at_most": 793,
            "total_logical_depth_at_most": 1594,
            "measurements": 0,
        },
        "strict_source_improvement_metrics": ("toffoli_count",),
    },
    "aes_sbox_repository_width9_881cnot_833toffoli": {
        "target": "aes_sbox_forward_minimal_width_nct",
        "source_record_path": "ir/baselines/quantum/aes_sbox_huang_zhang_lin_width9_nct.json",
        "candidate_qasm_path": "ir/results/quantum/aes_sbox_repository_width9_881cnot_833toffoli.qasm",
        "acceptance_bounds": {
            "logical_qubits_at_most": 9,
            "clean_ancillas_at_most": 1,
            "dirty_ancillas": 0,
            "x_count_at_most": 233,
            "cnot_count_at_most": 881,
            "toffoli_count_at_most": 833,
            "toffoli_depth_at_most": 793,
            "total_logical_depth_at_most": 1591,
            "measurements": 0,
        },
        "strict_source_improvement_metrics": (
            "cnot_count",
            "total_gate_count",
            "total_logical_depth",
        ),
    },
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
        "strict_source_improvement_metrics": (
            "cnot_count",
            "toffoli_count",
            "total_gate_count",
            "toffoli_depth",
            "total_logical_depth",
        ),
    },
    "aes_sbox_repository_width9_828toffoli": {
        "target": "aes_sbox_forward_minimal_width_nct",
        "source_record_path": "ir/baselines/quantum/aes_sbox_huang_zhang_lin_width9_nct.json",
        "direct_predecessor_record_path": "ir/baselines/quantum/aes_sbox_repository_width9_829toffoli.json",
        "candidate_qasm_path": "ir/results/quantum/aes_sbox_repository_width9_828toffoli.qasm",
        "acceptance_bounds": {
            "logical_qubits_at_most": 9,
            "clean_ancillas_at_most": 1,
            "dirty_ancillas": 0,
            "x_count_at_most": 233,
            "cnot_count_at_most": 883,
            "toffoli_count_at_most": 828,
            "toffoli_depth_at_most": 789,
            "total_logical_depth_at_most": 1581,
            "measurements": 0,
        },
        "strict_source_improvement_metrics": ("toffoli_count",),
        "strict_direct_improvement_metrics": (
            "x_count",
            "cnot_count",
            "toffoli_count",
            "total_gate_count",
            "toffoli_depth",
            "total_logical_depth",
        ),
    },
}

NCT_DERIVED_TARGETS = {"ascon_sbox_forward_toffoli_depth1_nct"}


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
    verify_nct_record(source_record)
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
    source_resources = source.get("resources")
    if not isinstance(source_resources, dict):
        raise VerificationError("source predecessor resources must be an object")
    for name in repository_config.get("strict_source_improvement_metrics", ()):
        if expected_resources[name] >= source_resources[name]:
            raise VerificationError(
                f"candidate does not strictly improve source {name}: "
                f"{expected_resources[name]} >= {source_resources[name]}"
            )
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
        for name in repository_config.get("strict_direct_improvement_metrics", ()):
            if expected_resources[name] >= direct_resources[name]:
                raise VerificationError(
                    f"candidate does not strictly improve direct predecessor {name}: "
                    f"{expected_resources[name]} >= {direct_resources[name]}"
                )

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
    target = record.get("target")
    if target not in NCT_DERIVED_TARGETS:
        raise VerificationError(f"unsupported derived NCT target: {target!r}")
    config = NCT_SOURCE_CONFIGS[target]
    verify_provenance(record)
    require_equal(record.get("boundary"), nct_expected_boundary(target, config), "NCT boundary")
    require_equal(record.get("model"), nct_expected_model(config), "NCT model")

    construction = record.get("construction")
    if not isinstance(construction, dict):
        raise VerificationError("derived NCT construction must be an object")
    require_equal(
        construction.get("source_preparation_cnot_count"),
        38,
        "source preparation count",
    )
    require_equal(
        construction.get("replacement_preparation_cnot_count"),
        14,
        "replacement preparation count",
    )
    if record.get("id") == "ascon_sbox_repository_toffoli_depth1_44cnot_depth19":
        require_equal(
            construction.get("source_middle_preserved_verbatim"),
            False,
            "source middle preservation declaration",
        )
        require_equal(
            construction.get("predecessor_middle_cnot_count"),
            19,
            "predecessor middle count",
        )
        require_equal(
            construction.get("replacement_middle_cnot_count"),
            16,
            "replacement middle count",
        )
    else:
        require_equal(
            construction.get("source_middle_preserved_verbatim"),
            True,
            "source middle preservation declaration",
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

    if record.get("id") == "ascon_sbox_repository_toffoli_depth1_44cnot_depth19":
        cnot_bound = 46
        depth_bound = 19
    else:
        cnot_bound = 94
        depth_bound = 56
    expected_acceptance = {
        "logical_qubits": 15,
        "clean_ancillas": 5,
        "zero_initialized_output_qubits": 5,
        "dirty_ancillas": 0,
        "x_count_at_most": 1,
        "cnot_count_at_most": cnot_bound,
        "toffoli_count_exactly": 5,
        "toffoli_depth_at_most": 1,
        "total_logical_depth_at_most": depth_bound,
        "measurements_exactly": 0,
    }
    require_equal(record.get("acceptance_bounds"), expected_acceptance, "acceptance bounds")
    if counts["x_count"] > expected_acceptance["x_count_at_most"]:
        raise VerificationError("derived NCT X count exceeds acceptance bound")
    if counts["cnot_count"] > expected_acceptance["cnot_count_at_most"]:
        raise VerificationError("derived NCT CNOT count exceeds acceptance bound")
    require_equal(
        counts["toffoli_count"],
        expected_acceptance["toffoli_count_exactly"],
        "accepted Toffoli count",
    )
    if layer_toffoli_depth > expected_acceptance["toffoli_depth_at_most"]:
        raise VerificationError("derived NCT Toffoli depth exceeds acceptance bound")
    if layer_depth > expected_acceptance["total_logical_depth_at_most"]:
        raise VerificationError("derived NCT full depth exceeds acceptance bound")

    return {
        "id": record.get("id"),
        "kind": "nct",
        "logical_qubits": config["width"],
        **counts,
        "toffoli_depth": layer_toffoli_depth,
        "total_logical_depth": layer_depth,
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
    if schema == "quantum-nct-source-ir/v1":
        return verify_nct_record(record)
    if schema == "quantum-nct-repository-ir/v1":
        return verify_nct_repository_record(record)
    if schema == "quantum-nct-derived-ir/v1":
        return verify_nct_derived_record(record)
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
            if result.get("kind") == "nct":
                print(
                    f"verified {path.relative_to(ROOT)}: {result['logical_qubits']} qubits, "
                    f"{result['x_count']} X, {result['cnot_count']} CNOT, "
                    f"{result['toffoli_count']} Toffoli, Toffoli depth "
                    f"{result['toffoli_depth']}, full depth {result['total_logical_depth']}"
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
