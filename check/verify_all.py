#!/usr/bin/env python3
"""Verify the complete CryptoCircuit publication and every result pair."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

sys.dont_write_bytecode = True

import verify_classical
import verify_quantum


ROOT = Path(__file__).resolve().parents[1]

FORBIDDEN_JSON_KEYS = {"pdf", "construction_receipt_path"}
FORBIDDEN_WORKSPACE_PREFIXES = (
    "papers/",
    "external/",
    "circuits/",
    "src/",
    "notes/",
    "tools/",
    "output/",
    "metadata/",
    "example/",
    "our_results/",
)
LOCAL_ABSOLUTE_MARKERS = ("/Users/", "/home/", "/tmp/", "/private/tmp/")


def classical_result(name: str) -> str:
    return f"ir/results/classical/{name}.json"


def classical_baseline(name: str) -> str:
    return f"ir/baselines/classical/{name}.json"


def quantum_result(name: str) -> str:
    return f"ir/results/quantum/{name}.json"


def quantum_baseline(name: str) -> str:
    return f"ir/baselines/quantum/{name}.json"


# (label, kind, result, baseline, strictly smaller metrics, unchanged metrics)
PAIRS = [
    ("AES S-box Tay shell", "classical", classical_result("aes_sbox_equiv_g19_t3_109gate"), classical_baseline("aes_sbox_tay_112gate"), ("total",), ("nonlinear", "nonlinear_depth")),
    ("AES S-box Maximov shell", "classical", classical_result("aes_sbox_maximov_equiv_g05_t2_101gate"), classical_baseline("aes_sbox_maximov_102gate"), ("total",), ("nonlinear", "nonlinear_depth")),
    ("AES S-box Feng rich basis", "classical", classical_result("aes_sbox_feng_equiv_g53_t6_85gate"), classical_baseline("aes_sbox_feng_93gate"), ("total",), ("nonlinear", "nonlinear_depth")),
    ("AES combined S-box", "classical", classical_result("aes_combined_sbox_mixed_odc_window_126gate"), classical_baseline("aes_combined_sbox_maximov_127gate"), ("total", "nonlinear"), ("linear", "depth", "nonlinear_depth")),
    ("AES S-box depth 14", "classical", classical_result("aes_sbox_slice_depth14_127gate"), classical_baseline("aes_sbox_slice_depth14"), ("total", "linear"), ("nonlinear", "depth", "nonlinear_depth")),
    ("AES S-box depth 11", "classical", classical_result("aes_sbox_slice_global_depth11_173gate"), classical_baseline("aes_sbox_slice_depth12"), ("depth",), ("nonlinear_depth",)),
    ("AES S-box depth 10", "classical", classical_result("aes_sbox_slice_bilinear_depth10_216gate"), classical_baseline("aes_sbox_disjoint_cover_depth10_999gate"), ("total",), ("depth", "nonlinear_depth")),
    ("AES MixColumns depth 3", "classical", classical_result("aes_mixcolumns_97xor_depth3"), classical_baseline("aes_mixcolumns_shi_99xor_depth3"), ("total",), ("depth", "nonlinear_depth")),
    ("AES InvMixColumns", "classical", classical_result("aes_invmixcolumns_135xor_depth8"), classical_baseline("aes_invmixcolumns_137xor_depth8"), ("total", "linear"), ("depth", "nonlinear_depth")),
    ("AES equivalent-inverse column", "classical", classical_result("aes_equivalent_inverse_column_latency_decomposed_675gate"), classical_baseline("aes_equivalent_inverse_column_latency_decomposed_677gate"), ("total", "linear"), ("nonlinear", "depth", "nonlinear_depth")),
    ("AES forward column depth 35", "classical", classical_result("aes_forward_column_equiv_gb7_t5_560gate"), classical_baseline("aes_forward_column_count_decomposed_556gate"), ("depth",), ("nonlinear", "nonlinear_depth")),
    ("AES forward column depth 29", "classical", classical_result("aes_forward_column_equiv_gbc_t0_564gate"), classical_baseline("aes_forward_column_count_decomposed_556gate"), ("depth",), ("nonlinear", "nonlinear_depth")),
    ("Ascon S-box depth 4", "classical", classical_result("ascon_sbox_15gate_depth4"), classical_baseline("ascon_sbox_slice_depth4"), ("total", "linear"), ("nonlinear", "depth", "nonlinear_depth")),
    ("Ascon pL after pS", "classical", classical_result("ascon_ps_pl_1600gate_depth6"), classical_baseline("ascon_ps_pl_nist_1664gate_depth7"), ("total", "linear", "depth"), ("nonlinear", "nonlinear_depth")),
    ("Ascon inverse S-box XAG", "classical", classical_result("ascon_inverse_sbox_6and_13xor_depth17"), classical_baseline("ascon_inverse_sbox_mcoptimal_binary_6and_32xor"), ("total", "linear"), ("nonlinear", "nonlinear_depth")),
    ("Ascon inverse diffusion Sigma0", "classical", classical_result("ascon_sigma0_inverse_8word_512xor"), classical_baseline("ascon_sigma0_inverse_factorized_512xor"), ("depth",), ("total", "linear", "nonlinear", "nonlinear_depth")),
    ("Ascon inverse diffusion Sigma1", "classical", classical_result("ascon_sigma1_inverse_8word_512xor"), classical_baseline("ascon_sigma1_inverse_paired_factor_576xor"), ("total", "linear", "depth"), ("nonlinear", "nonlinear_depth")),
    ("Ascon inverse diffusion Sigma2", "classical", classical_result("ascon_sigma2_inverse_8word_512xor"), classical_baseline("ascon_sigma2_inverse_paired_factor_576xor"), ("total", "linear", "depth"), ("nonlinear", "nonlinear_depth")),
    ("Ascon inverse diffusion Sigma3", "classical", classical_result("ascon_sigma3_inverse_8word_512xor"), classical_baseline("ascon_sigma3_inverse_paired_factor_576xor"), ("total", "linear", "depth"), ("nonlinear", "nonlinear_depth")),
    ("Ascon inverse diffusion Sigma4", "classical", classical_result("ascon_sigma4_inverse_8word_512xor"), classical_baseline("ascon_sigma4_inverse_paired_factor_576xor"), ("total", "linear", "depth"), ("nonlinear", "nonlinear_depth")),
    ("Ascon S-box Toffoli-depth-1 isometry", "quantum", quantum_result("ascon_sbox_repository_toffoli_depth1_47cnot_depth19"), quantum_baseline("ascon_sbox_huang_zhang_lin_toffoli_depth1_nct"), ("total_gate_count", "cnot_count", "total_logical_depth"), ("logical_qubits", "clean_ancillas", "dirty_ancillas", "x_count", "toffoli_count", "toffoli_depth")),
    ("AES S-box width-9 isometry", "quantum", quantum_result("aes_sbox_repository_width9_829toffoli"), quantum_baseline("aes_sbox_repository_width9_832toffoli"), ("total_gate_count", "toffoli_count", "toffoli_depth", "total_logical_depth"), ("logical_qubits", "clean_ancillas", "dirty_ancillas", "x_count", "cnot_count")),
    ("AES S-box output suffix count point", "quantum", quantum_result("aes_sbox_output_suffix_repository_53cnot_depth11"), quantum_baseline("aes_sbox_jiang_output_suffix_direct_68cnot_depth12"), ("total_gate_count", "x_count", "cnot_count", "cnot_depth", "total_logical_depth"), ("logical_qubits", "clean_ancillas", "dirty_ancillas")),
    ("AES S-box output suffix depth point", "quantum", quantum_result("aes_sbox_output_suffix_repository_53cnot_cnotdepth10_fdepth11"), quantum_baseline("aes_sbox_jiang_output_suffix_direct_68cnot_depth12"), ("total_gate_count", "cnot_count", "cnot_depth", "total_logical_depth"), ("logical_qubits", "clean_ancillas", "dirty_ancillas", "x_count")),
    ("AES MixColumns logical CNOT", "quantum", quantum_result("aes_mixcolumns_repository_105cnot_depth10"), quantum_baseline("aes_mixcolumns_xu_sun_107cnot_depth10"), ("total_gate_count", "cnot_count"), ("logical_qubits", "clean_ancillas", "dirty_ancillas", "cnot_depth", "total_depth")),
]


SUPPORT_FILES = {
    "AGENTS.md",
    "README.md",
    "check/verify_all.py",
    "check/verify_classical.py",
    "check/verify_quantum.py",
    "ir/baselines/quantum/aes_sbox_huang_zhang_lin_width9_nct.json",
    "ir/baselines/quantum/aes_sbox_huang_zhang_lin_width9_raw.qasm",
    "ir/baselines/quantum/aes_sbox_huang_zhang_lin_width9_layers.qasm",
    "ir/baselines/quantum/aes_sbox_repository_width9_832toffoli.qasm",
    "ir/baselines/quantum/ascon_sbox_huang_zhang_lin_toffoli_depth1_raw.qasm",
    "ir/baselines/quantum/ascon_sbox_huang_zhang_lin_toffoli_depth1_layers.qasm",
    "ir/results/quantum/aes_sbox_repository_width9_829toffoli.qasm",
}


def expected_files() -> set[str]:
    files = set(SUPPORT_FILES)
    for _, _, result, baseline, _, _ in PAIRS:
        files.add(result)
        files.add(baseline)
    return files


def audit_inventory() -> None:
    if (ROOT / ".git").is_dir():
        completed = subprocess.run(
            ["git", "ls-files", "-z"],
            cwd=ROOT,
            check=True,
            capture_output=True,
        )
        actual = {
            entry.decode("utf-8")
            for entry in completed.stdout.split(b"\0")
            if entry
        }
    else:
        actual = set()
        for path in ROOT.rglob("*"):
            relative = path.relative_to(ROOT)
            if path.is_symlink():
                raise RuntimeError(f"symbolic links are not permitted: {relative}")
            if path.is_file():
                actual.add(relative.as_posix())
    expected = expected_files()
    missing = sorted(expected - actual)
    unexpected = sorted(actual - expected)
    if missing or unexpected:
        raise RuntimeError(f"inventory mismatch: missing={missing}, unexpected={unexpected}")
    print(f"PASS inventory: {len(actual)} permitted files")


def audit_json_value(
    value: Any,
    record_relative: str,
    trail: tuple[str, ...],
    local_paths: set[str],
) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            child_trail = (*trail, key)
            location = f"{record_relative}:{'.'.join(child_trail)}"
            if key in FORBIDDEN_JSON_KEYS:
                raise RuntimeError(f"forbidden out-of-repository key at {location}")
            if isinstance(child, str):
                normalized = child.replace("\\", "/")
                if "://" not in normalized and any(
                    prefix in normalized for prefix in FORBIDDEN_WORKSPACE_PREFIXES
                ):
                    raise RuntimeError(f"research-workspace path at {location}: {child}")
                if any(marker in normalized for marker in LOCAL_ABSOLUTE_MARKERS):
                    raise RuntimeError(f"absolute local path at {location}: {child}")
            if key == "path" or key.endswith("_path"):
                if not isinstance(child, str) or not child:
                    raise RuntimeError(f"file-valued key must be a nonempty string at {location}")
                relative = Path(child)
                if relative.is_absolute() or ".." in relative.parts:
                    raise RuntimeError(f"non-local file reference at {location}: {child}")
                resolved = (ROOT / relative).resolve()
                root = ROOT.resolve()
                if root not in resolved.parents or not resolved.is_file():
                    raise RuntimeError(f"unresolved file reference at {location}: {child}")
                local_paths.add(relative.as_posix())
            audit_json_value(child, record_relative, child_trail, local_paths)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            audit_json_value(child, record_relative, (*trail, str(index)), local_paths)


def audit_self_contained_json() -> None:
    records = sorted(ROOT.glob("ir/**/*.json"))
    local_paths: set[str] = set()
    for path in records:
        relative = path.relative_to(ROOT).as_posix()
        record = json.loads(path.read_text(encoding="utf-8"))
        audit_json_value(record, relative, (), local_paths)
    print(
        f"PASS self-contained JSON: records={len(records)} "
        f"local_file_references={len(local_paths)}"
    )


def classical_metrics(report: dict[str, Any]) -> dict[str, int]:
    measured = report["metrics"]
    return {
        **measured["counts"],
        "depth": measured["depth"],
        "nonlinear_depth": measured["nonlinear_depth"],
    }


def quantum_metrics(path: Path) -> dict[str, Any]:
    record = json.loads(path.read_text(encoding="utf-8"))
    resources = record.get("resources")
    if not isinstance(resources, dict):
        raise RuntimeError(f"missing quantum resource vector: {path.relative_to(ROOT)}")
    return resources


def compare_pair(
    label: str,
    result: dict[str, Any],
    baseline: dict[str, Any],
    strict: tuple[str, ...],
    equal: tuple[str, ...],
) -> None:
    for metric in strict:
        if metric not in result or metric not in baseline:
            raise RuntimeError(f"{label}: missing comparison metric {metric}")
        if not result[metric] < baseline[metric]:
            raise RuntimeError(
                f"{label}: {metric} is not improved: {result[metric]} >= {baseline[metric]}"
            )
    for metric in equal:
        if metric not in result or metric not in baseline:
            raise RuntimeError(f"{label}: missing hard-bound metric {metric}")
        if result[metric] != baseline[metric]:
            raise RuntimeError(
                f"{label}: hard-bound metric {metric} changed: "
                f"{result[metric]} != {baseline[metric]}"
            )


def main() -> int:
    try:
        audit_inventory()
        audit_self_contained_json()
        classical_cache: dict[str, dict[str, Any]] = {}
        quantum_cache: dict[str, dict[str, Any]] = {}
        for label, kind, result_relative, baseline_relative, strict, equal in PAIRS:
            result_path = ROOT / result_relative
            baseline_path = ROOT / baseline_relative
            if kind == "classical":
                for relative, path in (
                    (result_relative, result_path),
                    (baseline_relative, baseline_path),
                ):
                    if relative not in classical_cache:
                        classical_cache[relative] = classical_metrics(
                            verify_classical.verify_record(path)
                        )
                result_metrics = classical_cache[result_relative]
                baseline_metrics = classical_cache[baseline_relative]
            else:
                for relative, path in (
                    (result_relative, result_path),
                    (baseline_relative, baseline_path),
                ):
                    if relative not in quantum_cache:
                        verify_quantum.verify_record(path)
                        quantum_cache[relative] = quantum_metrics(path)
                result_metrics = quantum_cache[result_relative]
                baseline_metrics = quantum_cache[baseline_relative]
            compare_pair(label, result_metrics, baseline_metrics, strict, equal)
            improvements = ", ".join(
                f"{metric} {baseline_metrics[metric]}->{result_metrics[metric]}"
                for metric in strict
            )
            print(f"PASS pair: {label}: {improvements}")

        # This source-disclosed AES record is supporting baseline IR for the
        # direct 832-to-829 comparison and must also replay independently.
        source_record = ROOT / "ir/baselines/quantum/aes_sbox_huang_zhang_lin_width9_nct.json"
        verify_quantum.verify_record(source_record)
        print(
            "PASS supporting baseline: "
            "aes_sbox_huang_zhang_lin_width9_nct (833 Toffoli)"
        )
        print(
            f"PASS all: pairs={len(PAIRS)} classical_records={len(classical_cache)} "
            f"quantum_pair_records={len(quantum_cache)}"
        )
        return 0
    except (OSError, ValueError, RuntimeError, verify_classical.VerificationError,
            verify_quantum.VerificationError) as error:
        print(f"FAIL: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
