#!/usr/bin/env python3
"""Verify the complete CryptoCircuit IR-only publication."""

from __future__ import annotations

import hashlib
import json
import re
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
NON_FILE_PATH_KEYS = {"dependency_critical_path"}

README_TABLE_SPECS = {
    "## Paper Table 2: Classical circuit results": (
        19,
        "11f01e3134943e9663acf32e79d4c6280098c07e6ee60ebb97f002bc85e42f58",
    ),
    "## Paper Table 3: Logical quantum and reversible results": (
        10,
        "e216d7f622f5c8d93155c31bc3eed9a818cefa733a24016558d7b9980fc834f9",
    ),
}


def classical_result(name: str) -> str:
    return f"ir/results/classical/{name}.json"


def classical_baseline(name: str) -> str:
    return f"ir/baselines/classical/{name}.json"


def quantum_result(name: str) -> str:
    return f"ir/results/quantum/{name}.json"


def quantum_baseline(name: str) -> str:
    return f"ir/baselines/quantum/{name}.json"


# label, kind, result, baseline, strictly smaller metrics, unchanged hard bounds
TABLE_COMPARISONS = [
    ("AES S-box Tay shell", "classical", classical_result("aes_sbox_equiv_g19_t3_109gate"), classical_baseline("aes_sbox_tay_112gate"), ("total",), ("nonlinear", "nonlinear_depth")),
    ("AES S-box Maximov shell", "classical", classical_result("aes_sbox_maximov_equiv_g05_t2_101gate"), classical_baseline("aes_sbox_maximov_102gate"), ("total",), ("nonlinear", "nonlinear_depth")),
    ("AES S-box Feng basis", "classical", classical_result("aes_sbox_feng_equiv_g53_t6_84gate"), classical_baseline("aes_sbox_feng_93gate"), ("total",), ("nonlinear", "nonlinear_depth")),
    ("AES combined S-box", "classical", classical_result("aes_combined_sbox_context_quotient_125gate"), classical_baseline("aes_combined_sbox_mixed_odc_window_126gate"), ("total", "linear"), ("nonlinear", "depth", "nonlinear_depth")),
    ("AES S-box depth 14", "classical", classical_result("aes_sbox_slice_depth14_126gate"), classical_baseline("aes_sbox_slice_depth14"), ("total", "linear"), ("nonlinear", "depth", "nonlinear_depth")),
    ("AES S-box depth 13", "classical", classical_result("aes_sbox_slice_depth13_135gate"), classical_baseline("aes_sbox_slice_depth13"), ("total", "linear"), ("nonlinear", "depth", "nonlinear_depth")),
    ("AES S-box depth 12", "classical", classical_result("aes_sbox_slice_depth12_148gate"), classical_baseline("aes_sbox_slice_depth12"), ("total", "linear"), ("nonlinear", "depth", "nonlinear_depth")),
    ("AES S-box depth 11 tradeoff", "classical", classical_result("aes_sbox_slice_global_depth11_173gate"), classical_baseline("aes_sbox_slice_depth12"), ("depth",), ("nonlinear_depth",)),
    ("AES S-box depth 10", "classical", classical_result("aes_sbox_slice_bilinear_depth10_216gate"), classical_baseline("aes_sbox_jia_2026_dualrail_2738gate_depth10"), ("total", "linear", "nonlinear"), ("depth", "nonlinear_depth")),
    ("AES MixColumns binary depth 3", "classical", classical_result("aes_mixcolumns_97xor_depth3"), classical_baseline("aes_mixcolumns_shi_99xor_depth3"), ("total", "linear"), ("depth", "nonlinear_depth")),
    ("AES MixColumns mixed depth 3", "classical", classical_result("aes_mixcolumns_42xor_mixed_fanin_depth3"), classical_baseline("aes_mixcolumns_44xor_mixed_fanin_depth3"), ("total", "linear"), ("depth", "nonlinear_depth")),
    ("AES MixColumns selector", "classical", classical_result("aes_selector_mixcolumns_rank16_161gate"), classical_baseline("aes_selector_mixcolumns_rank16_166gate"), ("total", "linear"), ("nonlinear", "and2", "depth", "nonlinear_depth")),
    ("Ascon inverse S-box", "classical", classical_result("ascon_inverse_sbox_6and_12xor_depth19"), classical_baseline("ascon_inverse_sbox_6and_13xor_depth17"), ("total", "linear"), ("nonlinear", "nonlinear_depth")),
    ("Ascon inverse diffusion Sigma0", "classical", classical_result("ascon_sigma0_inverse_8word_512xor"), classical_baseline("ascon_sigma0_inverse_tezcan_balanced_1920xor"), ("total", "linear"), ("nonlinear", "nonlinear_depth")),
    ("Ascon inverse diffusion Sigma1", "classical", classical_result("ascon_sigma1_inverse_8word_512xor"), classical_baseline("ascon_sigma1_inverse_tezcan_balanced_2048xor"), ("total", "linear"), ("nonlinear", "nonlinear_depth")),
    ("Ascon inverse diffusion Sigma2", "classical", classical_result("ascon_sigma2_inverse_8word_512xor"), classical_baseline("ascon_sigma2_inverse_tezcan_balanced_2048xor"), ("total", "linear"), ("nonlinear", "depth", "nonlinear_depth")),
    ("Ascon inverse diffusion Sigma3", "classical", classical_result("ascon_sigma3_inverse_8word_512xor"), classical_baseline("ascon_sigma3_inverse_tezcan_balanced_2048xor"), ("total", "linear"), ("nonlinear", "nonlinear_depth")),
    ("Ascon inverse diffusion Sigma4", "classical", classical_result("ascon_sigma4_inverse_8word_512xor"), classical_baseline("ascon_sigma4_inverse_tezcan_balanced_2176xor"), ("total", "linear"), ("nonlinear", "nonlinear_depth")),
    ("Ascon Toffoli-depth-one isometry", "quantum", quantum_result("ascon_sbox_repository_toffoli_depth1_42cnot_depth19"), quantum_baseline("ascon_sbox_huang_zhang_lin_toffoli_depth1_nct"), ("total_gate_count", "cnot_count", "total_logical_depth"), ("logical_qubits", "clean_ancillas", "dirty_ancillas", "x_count", "toffoli_count", "toffoli_depth")),
    ("Specialized Ascon S-box", "quantum", quantum_result("ascon_sbox_round_constant_x2_specialized_16gate_nct"), quantum_baseline("ascon_sbox_round_constant_x2_specialized_17gate_nct"), ("total_gate_count", "x_count"), ("logical_qubits", "cnot_count", "toffoli_count", "toffoli_depth", "total_logical_depth")),
    ("Ascon linear layer 1525/45", "quantum", quantum_result("ascon_linear_local_rewrite_inplace_1525cnot_depth45"), quantum_baseline("ascon_linear_commutation_rescheduled_inplace_1595cnot_depth45"), ("total_gate_count", "cnot_count"), ("logical_qubits", "dirty_ancillas", "cnot_depth", "total_logical_depth")),
    ("Ascon linear layer 1502/46 Pareto", "quantum", quantum_result("ascon_linear_local_rewrite_inplace_1502cnot_depth46"), quantum_baseline("ascon_linear_commutation_rescheduled_inplace_1595cnot_depth45"), ("total_gate_count", "cnot_count"), ("logical_qubits", "dirty_ancillas")),
    ("Ascon round core 2549/56", "quantum", quantum_result("ascon_round_core_guo_linear_rewrite_2549gate_depth56"), quantum_baseline("ascon_round_core_guo_xzlbz_2619gate_depth56"), ("total_gate_count", "cnot_count"), ("logical_qubits", "dirty_ancillas", "x_count", "toffoli_count", "toffoli_depth", "total_logical_depth")),
    ("Ascon round core 2526/57 Pareto", "quantum", quantum_result("ascon_round_core_guo_linear_rewrite_2526gate_depth57"), quantum_baseline("ascon_round_core_guo_xzlbz_2619gate_depth56"), ("total_gate_count", "cnot_count"), ("logical_qubits", "dirty_ancillas", "x_count", "toffoli_count", "toffoli_depth")),
    ("AES width-nine S-box isometry", "quantum", quantum_result("aes_sbox_repository_width9_829toffoli"), quantum_baseline("aes_sbox_huang_zhang_lin_width9_nct"), ("total_gate_count", "cnot_count", "toffoli_count", "toffoli_depth", "total_logical_depth"), ("logical_qubits", "clean_ancillas", "dirty_ancillas", "x_count")),
    ("AES output suffix count point", "quantum", quantum_result("aes_sbox_output_suffix_repository_51cnot_depth11"), quantum_baseline("aes_sbox_jiang_output_suffix_direct_68cnot_depth12"), ("total_gate_count", "x_count", "cnot_count", "cnot_depth", "total_logical_depth"), ("logical_qubits", "clean_ancillas", "dirty_ancillas")),
    ("AES output suffix depth point", "quantum", quantum_result("aes_sbox_output_suffix_repository_53cnot_cnotdepth10_fdepth11"), quantum_baseline("aes_sbox_jiang_output_suffix_direct_68cnot_depth12"), ("total_gate_count", "cnot_count", "cnot_depth", "total_logical_depth"), ("logical_qubits", "clean_ancillas", "dirty_ancillas", "x_count")),
    ("Keyed AES column", "quantum", quantum_result("aes_keyed_subbytes_mixcolumns_column_3668cnot"), quantum_baseline("aes_keyed_subbytes_mixcolumns_column_3669cnot"), ("total_gate_count", "cnot_count"), ("logical_qubits", "clean_ancillas", "dirty_ancillas", "x_count", "toffoli_count", "toffoli_depth", "total_logical_depth")),
]

CHECKPOINT_COMPARISONS = [
    ("AES Feng direct checkpoint", "classical", classical_result("aes_sbox_feng_equiv_g53_t6_84gate"), classical_baseline("aes_sbox_feng_equiv_g53_t6_85gate"), ("total", "linear"), ("nonlinear", "depth", "nonlinear_depth")),
    ("AES depth-14 direct checkpoint", "classical", classical_result("aes_sbox_slice_depth14_126gate"), classical_baseline("aes_sbox_slice_depth14_127gate"), ("total", "linear"), ("nonlinear", "depth", "nonlinear_depth")),
    ("Ascon inverse source checkpoint", "classical", classical_baseline("ascon_inverse_sbox_6and_13xor_depth17"), classical_baseline("ascon_inverse_sbox_mcoptimal_binary_6and_32xor"), ("total", "linear"), ("nonlinear", "nonlinear_depth")),
    ("Ascon isometry 42-CNOT checkpoint", "quantum", quantum_result("ascon_sbox_repository_toffoli_depth1_42cnot_depth19"), quantum_baseline("ascon_sbox_repository_toffoli_depth1_43cnot_depth19"), ("total_gate_count", "cnot_count"), ("logical_qubits", "clean_ancillas", "dirty_ancillas", "x_count", "toffoli_count", "toffoli_depth", "total_logical_depth")),
    ("Ascon isometry 43-CNOT checkpoint", "quantum", quantum_baseline("ascon_sbox_repository_toffoli_depth1_43cnot_depth19"), quantum_baseline("ascon_sbox_repository_toffoli_depth1_44cnot_depth19"), ("total_gate_count", "cnot_count"), ("logical_qubits", "clean_ancillas", "dirty_ancillas", "x_count", "toffoli_count", "toffoli_depth", "total_logical_depth")),
    ("Ascon linear Pareto direct checkpoint", "quantum", quantum_result("ascon_linear_local_rewrite_inplace_1502cnot_depth46"), quantum_result("ascon_linear_local_rewrite_inplace_1525cnot_depth45"), ("total_gate_count", "cnot_count"), ("logical_qubits", "dirty_ancillas")),
    ("Ascon round-core direct checkpoint", "quantum", quantum_result("ascon_round_core_guo_linear_rewrite_2549gate_depth56"), quantum_baseline("ascon_round_core_guo_linear_rewrite_2550gate_depth56"), ("total_gate_count", "cnot_count"), ("logical_qubits", "dirty_ancillas", "x_count", "toffoli_count", "toffoli_depth", "total_logical_depth")),
    ("Ascon round-core Pareto direct checkpoint", "quantum", quantum_result("ascon_round_core_guo_linear_rewrite_2526gate_depth57"), quantum_result("ascon_round_core_guo_linear_rewrite_2549gate_depth56"), ("total_gate_count", "cnot_count"), ("logical_qubits", "dirty_ancillas", "x_count", "toffoli_count", "toffoli_depth")),
    ("AES suffix direct checkpoint", "quantum", quantum_result("aes_sbox_output_suffix_repository_51cnot_depth11"), quantum_baseline("aes_sbox_output_suffix_repository_52cnot_depth11"), ("total_gate_count", "cnot_count"), ("logical_qubits", "clean_ancillas", "dirty_ancillas", "x_count", "cnot_depth", "total_logical_depth")),
]

EXTRA_RECORDS = {
    classical_baseline("aes_combined_sbox_maximov_127gate"),
    quantum_baseline("aes_mixcolumns_repository_105cnot_depth10"),
    quantum_baseline("aes_sbox_output_suffix_repository_53cnot_depth11"),
    quantum_baseline("ascon_linear_local_rewrite_inplace_1526cnot_depth45"),
    quantum_baseline("ascon_sbox_guo_et_al_width5_16gate_nct"),
    quantum_baseline("ascon_sbox_huang_zhang_lin_width5_nct"),
    quantum_baseline("ascon_linear_oh_et_al_copy_960cnot_depth3"),
}

QASM_FILES = {
    "ir/baselines/quantum/aes_keyed_subbytes_mixcolumns_column_3669cnot.qasm",
    "ir/baselines/quantum/aes_sbox_huang_zhang_lin_width9_layers.qasm",
    "ir/baselines/quantum/aes_sbox_huang_zhang_lin_width9_raw.qasm",
    "ir/baselines/quantum/ascon_sbox_guo_et_al_width5_16gate_nct.qasm",
    "ir/baselines/quantum/ascon_sbox_huang_zhang_lin_toffoli_depth1_layers.qasm",
    "ir/baselines/quantum/ascon_sbox_huang_zhang_lin_toffoli_depth1_raw.qasm",
    "ir/baselines/quantum/ascon_sbox_huang_zhang_lin_width5_layers.qasm",
    "ir/baselines/quantum/ascon_sbox_huang_zhang_lin_width5_raw.qasm",
    "ir/baselines/quantum/ascon_sbox_round_constant_x2_specialized_17gate_nct.qasm",
    "ir/results/quantum/aes_keyed_subbytes_mixcolumns_column_3668cnot.qasm",
    "ir/results/quantum/aes_sbox_repository_width9_829toffoli.qasm",
    "ir/results/quantum/ascon_sbox_round_constant_x2_specialized_16gate_nct.qasm",
}

SUPPORT_FILES = {
    "AGENTS.md",
    "README.md",
    "check/verify_all.py",
    "check/verify_classical.py",
    "check/verify_quantum.py",
    *EXTRA_RECORDS,
    *QASM_FILES,
}


def expected_files() -> set[str]:
    files = set(SUPPORT_FILES)
    for comparison in [*TABLE_COMPARISONS, *CHECKPOINT_COMPARISONS]:
        files.add(comparison[2])
        files.add(comparison[3])
    return files


def audit_inventory() -> None:
    actual = set()
    for path in ROOT.rglob("*"):
        relative = path.relative_to(ROOT)
        if relative.parts[0] == ".git" or path.name == ".DS_Store":
            continue
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


def audit_json_value(value: Any, record_relative: str, trail: tuple[str, ...], local_paths: set[str]) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            child_trail = (*trail, key)
            location = f"{record_relative}:{'.'.join(child_trail)}"
            if key in FORBIDDEN_JSON_KEYS:
                raise RuntimeError(f"forbidden out-of-repository key at {location}")
            if isinstance(child, str):
                normalized = child.replace("\\", "/")
                if "://" not in normalized and any(prefix in normalized for prefix in FORBIDDEN_WORKSPACE_PREFIXES):
                    raise RuntimeError(f"research-workspace path at {location}: {child}")
                if any(marker in normalized for marker in LOCAL_ABSOLUTE_MARKERS):
                    raise RuntimeError(f"absolute local path at {location}: {child}")
            if key == "path" or (
                key.endswith("_path") and key not in NON_FILE_PATH_KEYS
            ):
                if not isinstance(child, str) or not child:
                    raise RuntimeError(f"file-valued key must be a nonempty string at {location}")
                relative = Path(child)
                if relative.is_absolute() or ".." in relative.parts:
                    raise RuntimeError(f"non-local file reference at {location}: {child}")
                resolved = (ROOT / relative).resolve()
                if ROOT.resolve() not in resolved.parents or not resolved.is_file():
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
        audit_json_value(json.loads(path.read_text(encoding="utf-8")), relative, (), local_paths)
    print(f"PASS self-contained JSON: records={len(records)} local_file_references={len(local_paths)}")


def visible_markdown_cell(cell: str) -> str:
    cell = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", cell)
    cell = cell.replace("`", "").replace("**", "")
    return " ".join(cell.split())


def paper_table_digest(readme: str, heading: str) -> tuple[int, str]:
    section_start = readme.find(heading)
    if section_start < 0:
        raise RuntimeError(f"README is missing paper-table heading: {heading}")
    section = readme[section_start + len(heading) :]
    next_heading = section.find("\n## ")
    if next_heading >= 0:
        section = section[:next_heading]
    table_lines = [line for line in section.splitlines() if line.startswith("|")]
    if len(table_lines) < 2:
        raise RuntimeError(f"README has no Markdown table below: {heading}")
    if not re.fullmatch(r"\|(?:\s*:?-+:?\s*\|){5}", table_lines[1]):
        raise RuntimeError(f"README has a malformed five-column separator below: {heading}")

    normalized_rows = []
    for line in [table_lines[0], *table_lines[2:]]:
        cells = [visible_markdown_cell(cell) for cell in line.strip("|").split("|")]
        if len(cells) != 5:
            raise RuntimeError(
                f"README paper-table row has {len(cells)} columns instead of 5: {line}"
            )
        normalized_rows.append("\t".join(cells))
    if normalized_rows[0] != "Component\tTarget\tModel\tPrior\tNew":
        raise RuntimeError(f"README paper-table columns changed below: {heading}")
    payload = "\n".join(normalized_rows).encode("utf-8")
    return len(normalized_rows) - 1, hashlib.sha256(payload).hexdigest()


def audit_readme_alignment() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    required_literals = {
        "Tables 2 and 3",
        "8b5f72a20feecb9c59e8c32389f75829d215d35b780ecdbb41288180c3c7621a",
        "column-for-column",
        "PICCOLO and SM4 rows",
        "proof-only AES MixColumns retained-copy row",
    }
    missing_literals = sorted(text for text in required_literals if text not in readme)

    table_failures = []
    paper_row_count = 0
    for heading, (expected_rows, expected_digest) in README_TABLE_SPECS.items():
        actual_rows, actual_digest = paper_table_digest(readme, heading)
        paper_row_count += actual_rows
        if actual_rows != expected_rows or actual_digest != expected_digest:
            table_failures.append(
                {
                    "heading": heading,
                    "expected_rows": expected_rows,
                    "actual_rows": actual_rows,
                    "expected_digest": expected_digest,
                    "actual_digest": actual_digest,
                }
            )

    comparison_paths = {comparison[2] for comparison in TABLE_COMPARISONS}
    for comparison in CHECKPOINT_COMPARISONS:
        comparison_paths.update((comparison[2], comparison[3]))
    missing_paths = sorted(path for path in comparison_paths if path not in readme)

    markdown_targets = re.findall(r"\[[^\]]+\]\(([^)]+)\)", readme)
    broken_links = sorted(
        target
        for target in markdown_targets
        if "://" not in target and not (ROOT / target).is_file()
    )

    classical_count = len(list(ROOT.glob("ir/*/classical/*.json")))
    quantum_count = len(list(ROOT.glob("ir/*/quantum/*.json")))
    expected_summary = (
        f"PASS all: table_comparisons={len(TABLE_COMPARISONS)} "
        f"checkpoint_comparisons={len(CHECKPOINT_COMPARISONS)} "
        f"classical_records={classical_count} quantum_records={quantum_count} "
        "supporting_theorem_records=2"
    )
    if expected_summary not in readme:
        missing_literals.append(expected_summary)

    if missing_literals or table_failures or missing_paths or broken_links:
        raise RuntimeError(
            "README alignment mismatch: "
            f"missing_literals={missing_literals}, table_failures={table_failures}, "
            f"missing_paths={missing_paths}, broken_links={broken_links}"
        )
    print(
        "PASS README alignment: "
        f"paper_rows={paper_row_count} comparison_paths={len(comparison_paths)} "
        f"local_links={len(markdown_targets)}"
    )


def classical_metrics(report: dict[str, Any]) -> dict[str, int]:
    measured = report["metrics"]
    return {**measured["counts"], "depth": measured["depth"], "nonlinear_depth": measured["nonlinear_depth"]}


def quantum_metrics(path: Path) -> dict[str, Any]:
    record = json.loads(path.read_text(encoding="utf-8"))
    resources = record.get("resources")
    if not isinstance(resources, dict):
        raise RuntimeError(f"missing quantum resource vector: {path.relative_to(ROOT)}")
    return resources


def compare_pair(label: str, result: dict[str, Any], baseline: dict[str, Any], strict: tuple[str, ...], equal: tuple[str, ...]) -> None:
    for metric in strict:
        if metric not in result or metric not in baseline or not result[metric] < baseline[metric]:
            raise RuntimeError(f"{label}: {metric} is not strictly improved")
    for metric in equal:
        if metric not in result or metric not in baseline or result[metric] != baseline[metric]:
            raise RuntimeError(f"{label}: hard-bound metric {metric} changed")


def run_comparison(comparison: tuple[Any, ...], classical_cache: dict[str, dict[str, Any]], quantum_cache: dict[str, dict[str, Any]], kind_label: str) -> None:
    label, kind, result_relative, baseline_relative, strict, equal = comparison
    result_metrics = classical_cache[result_relative] if kind == "classical" else quantum_cache[result_relative]
    baseline_metrics = classical_cache[baseline_relative] if kind == "classical" else quantum_cache[baseline_relative]
    compare_pair(label, result_metrics, baseline_metrics, strict, equal)
    improvements = ", ".join(f"{metric} {baseline_metrics[metric]}->{result_metrics[metric]}" for metric in strict)
    print(f"PASS {kind_label}: {label}: {improvements}")


def main() -> int:
    try:
        audit_inventory()
        audit_self_contained_json()
        audit_readme_alignment()

        classical_cache = {
            path.relative_to(ROOT).as_posix(): classical_metrics(verify_classical.verify_record(path))
            for path in sorted(ROOT.glob("ir/*/classical/*.json"))
        }
        quantum_cache: dict[str, dict[str, Any]] = {}
        for path in sorted(ROOT.glob("ir/*/quantum/*.json")):
            verify_quantum.verify_record(path)
            quantum_cache[path.relative_to(ROOT).as_posix()] = quantum_metrics(path)

        for comparison in TABLE_COMPARISONS:
            run_comparison(comparison, classical_cache, quantum_cache, "table comparison")
        for comparison in CHECKPOINT_COMPARISONS:
            run_comparison(comparison, classical_cache, quantum_cache, "checkpoint comparison")

        seven = quantum_cache[quantum_baseline("ascon_sbox_huang_zhang_lin_width5_nct")]
        if seven["toffoli_count"] != 7:
            raise RuntimeError("Ascon width-five witness is not seven Toffolis")
        retained = quantum_cache[quantum_baseline("ascon_linear_oh_et_al_copy_960cnot_depth3")]
        if retained["cnot_count"] != 960 or retained["cnot_depth"] != 3:
            raise RuntimeError("Ascon retained-copy witness is not 960 CNOTs at depth 3")
        print("PASS supporting theorem IR: Ascon seven-Toffoli and retained-copy 960-CNOT witnesses")

        print(
            f"PASS all: table_comparisons={len(TABLE_COMPARISONS)} "
            f"checkpoint_comparisons={len(CHECKPOINT_COMPARISONS)} "
            f"classical_records={len(classical_cache)} quantum_records={len(quantum_cache)} "
            "supporting_theorem_records=2"
        )
        return 0
    except (
        OSError,
        ValueError,
        RuntimeError,
        verify_classical.VerificationError,
        verify_quantum.VerificationError,
    ) as error:
        print(f"FAIL: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
