# CryptoCircuit Verified IR

CryptoCircuit is a minimal publication artifact for independently checking
verified AES and Ascon circuit improvements. Each entry contains the complete
result IR, the complete directly comparable previous-best IR, and standalone
Python checkers. The repository deliberately excludes papers, research notes,
search and synthesis code, solver receipts, logs, and generated reports.

Snapshot: **2026-08-29**.

“Previous best” below means the directly comparable predecessor frozen in this
snapshot under the same function boundary, bit order, primitive basis, metric,
and stated hard bounds. It is not an unqualified claim about every circuit
model or later literature. Every result is a verified construction and hence an
upper bound unless a separate checked lower-bound artifact is explicitly
provided; this repository does not distribute such proof artifacts.

## Check everything

Python 3.9 or newer is sufficient; the checkers use only the standard library.

```sh
git clone https://github.com/chongxuren/cryptocircuit.git
cd cryptocircuit
python3 check/verify_all.py
```

The command rejects missing or unexpected tracked repository files, verifies
every IR program independently against its frozen target, recomputes gate counts and
depths, checks quantum boundary and ancilla conditions, and checks every stated
result/predecessor comparison. A successful run ends with:

```text
PASS all: pairs=25 classical_records=39 quantum_pair_records=9
```

The narrower checkers can also be run directly:

```sh
python3 check/verify_classical.py
python3 check/verify_quantum.py
```

## Published classical pairs

| Frozen component and model | Directly comparable previous best | Result | Verified comparison |
|---|---:|---:|---|
| AES forward S-box; Tay binary `XOR2`/`XNOR2`/`AND2`; count objective | [112 gates, depth 25](ir/baselines/classical/aes_sbox_tay_112gate.json) | [109 gates, depth 34](ir/results/classical/aes_sbox_equiv_g19_t3_109gate.json) | 3 fewer gates; count-only tradeoff |
| AES forward S-box; Maximov mixed-cell basis; count objective | [102 cells, depth 24](ir/baselines/classical/aes_sbox_maximov_102gate.json) | [101 cells, depth 32](ir/results/classical/aes_sbox_maximov_equiv_g05_t2_101gate.json) | 1 fewer cell; count-only tradeoff |
| AES forward S-box; Feng rich-cell basis; count objective | [93 cells, depth 22](ir/baselines/classical/aes_sbox_feng_93gate.json) | [85 cells, depth 29](ir/results/classical/aes_sbox_feng_equiv_g53_t6_85gate.json) | 8 fewer cells; count-only tradeoff |
| AES combined forward/inverse S-box; `msb0`; mixed-cell basis; depth at most 25 | [127 cells, 48 nonlinear, depth 25](ir/baselines/classical/aes_combined_sbox_maximov_127gate.json) | [126 cells, 47 nonlinear, depth 25](ir/results/classical/aes_combined_sbox_mixed_odc_window_126gate.json) | 1 fewer cell and nonlinear cell |
| AES forward S-box; strict fan-in-two SLICE basis; depth at most 14 | [128 gates, depth 14](ir/baselines/classical/aes_sbox_slice_depth14.json) | [127 gates, depth 14](ir/results/classical/aes_sbox_slice_depth14_127gate.json) | 1 fewer linear gate |
| AES forward S-box; strict fan-in-two SLICE basis; depth objective | [149 gates, depth 12](ir/baselines/classical/aes_sbox_slice_depth12.json) | [173 gates, depth 11](ir/results/classical/aes_sbox_slice_global_depth11_173gate.json) | 1 fewer level for 24 more gates |
| AES forward S-box; strict fan-in-two SLICE basis; depth at most 10 | [999 gates, depth 10](ir/baselines/classical/aes_sbox_disjoint_cover_depth10_999gate.json) | [216 gates, depth 10](ir/results/classical/aes_sbox_slice_bilinear_depth10_216gate.json) | 783 fewer gates |
| AES MixColumns; `lsb0`; logical `XOR2`; depth at most 3 | [99 XOR, depth 3](ir/baselines/classical/aes_mixcolumns_shi_99xor_depth3.json) | [97 XOR, depth 3](ir/results/classical/aes_mixcolumns_97xor_depth3.json) | 2 fewer XOR |
| AES InvMixColumns; `lsb0`; logical `XOR2`; depth at most 8 | [137 XOR, depth 8](ir/baselines/classical/aes_invmixcolumns_137xor_depth8.json) | [135 XOR, depth 8](ir/results/classical/aes_invmixcolumns_135xor_depth8.json) | 2 fewer XOR |
| AES equivalent-inverse column; binary basis; depth at most 25 | [677 gates, depth 25](ir/baselines/classical/aes_equivalent_inverse_column_latency_decomposed_677gate.json) | [675 gates, depth 25](ir/results/classical/aes_equivalent_inverse_column_latency_decomposed_675gate.json) | 2 fewer linear gates |
| AES forward keyed column; binary basis; count/depth Pareto track | [556 gates, depth 42](ir/baselines/classical/aes_forward_column_count_decomposed_556gate.json) | [560 gates, depth 35](ir/results/classical/aes_forward_column_equiv_gb7_t5_560gate.json) | 7 fewer levels for 4 more gates |
| AES forward keyed column; binary basis; count/depth Pareto track | [556 gates, depth 42](ir/baselines/classical/aes_forward_column_count_decomposed_556gate.json) | [564 gates, depth 29](ir/results/classical/aes_forward_column_equiv_gbc_t0_564gate.json) | 13 fewer levels for 8 more gates |
| Ascon 5-bit S-box; free-complement mixed Boolean basis; depth at most 4 | [16 gates, depth 4](ir/baselines/classical/ascon_sbox_slice_depth4.json) | [15 gates, depth 4](ir/results/classical/ascon_sbox_15gate_depth4.json) | 1 fewer linear gate |
| Ascon standardized `p_L` after `p_S`; 320-bit `lsb0`; mixed Boolean basis | [1664 gates, depth 7](ir/baselines/classical/ascon_ps_pl_nist_1664gate_depth7.json) | [1600 gates, depth 6](ir/results/classical/ascon_ps_pl_1600gate_depth6.json) | 64 fewer gates and 1 fewer level |
| Ascon inverse S-box; free-complement binary XAG; XOR objective with 6 AND | [32 XOR + 6 AND, depth 16](ir/baselines/classical/ascon_inverse_sbox_mcoptimal_binary_6and_32xor.json) | [13 XOR + 6 AND, depth 17](ir/results/classical/ascon_inverse_sbox_6and_13xor_depth17.json) | 19 fewer XOR; 1-level tradeoff |
| Ascon inverse diffusion `Sigma_0`; logical `XOR2` | [512 XOR, depth 8](ir/baselines/classical/ascon_sigma0_inverse_factorized_512xor.json) | [512 XOR, depth 6](ir/results/classical/ascon_sigma0_inverse_8word_512xor.json) | same count, 2 fewer levels |
| Ascon inverse diffusion `Sigma_1`; logical `XOR2` | [576 XOR, depth 9](ir/baselines/classical/ascon_sigma1_inverse_paired_factor_576xor.json) | [512 XOR, depth 7](ir/results/classical/ascon_sigma1_inverse_8word_512xor.json) | 64 fewer XOR and 2 fewer levels |
| Ascon inverse diffusion `Sigma_2`; logical `XOR2` | [576 XOR, depth 9](ir/baselines/classical/ascon_sigma2_inverse_paired_factor_576xor.json) | [512 XOR, depth 6](ir/results/classical/ascon_sigma2_inverse_8word_512xor.json) | 64 fewer XOR and 3 fewer levels |
| Ascon inverse diffusion `Sigma_3`; logical `XOR2` | [576 XOR, depth 9](ir/baselines/classical/ascon_sigma3_inverse_paired_factor_576xor.json) | [512 XOR, depth 7](ir/results/classical/ascon_sigma3_inverse_8word_512xor.json) | 64 fewer XOR and 2 fewer levels |
| Ascon inverse diffusion `Sigma_4`; logical `XOR2` | [576 XOR, depth 9](ir/baselines/classical/ascon_sigma4_inverse_paired_factor_576xor.json) | [512 XOR, depth 7](ir/results/classical/ascon_sigma4_inverse_8word_512xor.json) | 64 fewer XOR and 2 fewer levels |

## Published quantum and reversible pairs

These are logical, all-to-all results before device mapping. Physical qubits,
routing overhead, noise, and fault-tolerance cost are not modeled. The complete
resource vectors and precise unitary or isometry boundaries are in the IR.

| Frozen component and logical model | Directly comparable previous best | Result | Verified comparison |
|---|---:|---:|---|
| Ascon forward S-box isometry; 15 qubits; 5 clean workspace qubits; logical `X`/CNOT/Toffoli; Toffoli depth 1 | [95 CNOT, 5 Toffoli, full depth 56](ir/baselines/quantum/ascon_sbox_huang_zhang_lin_toffoli_depth1_nct.json) | [47 CNOT, 5 Toffoli, full depth 19](ir/results/quantum/ascon_sbox_repository_toffoli_depth1_47cnot_depth19.json) | 48 fewer CNOT and 37 fewer levels |
| AES forward S-box isometry; 9 qubits; 1 clean ancilla; logical `X`/CNOT/Toffoli | [832 Toffoli, Toffoli depth 792, full depth 1591](ir/baselines/quantum/aes_sbox_repository_width9_832toffoli.json) | [829 Toffoli, Toffoli depth 789, full depth 1581](ir/results/quantum/aes_sbox_repository_width9_829toffoli.json) | 3 fewer Toffoli and 10 fewer levels; the [833-Toffoli source IR](ir/baselines/quantum/aes_sbox_huang_zhang_lin_width9_nct.json) is also included |
| AES S-box affine output-accumulation unitary; 26 arbitrary boundary qubits; logical CNOT/`X` | [68 CNOT, 4 X, full depth 12](ir/baselines/quantum/aes_sbox_jiang_output_suffix_direct_68cnot_depth12.json) | [53 CNOT, 3 X, full depth 11](ir/results/quantum/aes_sbox_output_suffix_repository_53cnot_depth11.json) | 15 fewer CNOT, 1 fewer X, and 1 fewer level |
| Same AES affine output unitary; CNOT-depth Pareto point | [68 CNOT, CNOT/full depth 12](ir/baselines/quantum/aes_sbox_jiang_output_suffix_direct_68cnot_depth12.json) | [53 CNOT, CNOT depth 10, full depth 11](ir/results/quantum/aes_sbox_output_suffix_repository_53cnot_cnotdepth10_fdepth11.json) | 15 fewer CNOT and 2 fewer CNOT levels |
| AES MixColumns unitary; 32 qubits; no ancilla; all-to-all logical CNOT | [107 CNOT, depth 10](ir/baselines/quantum/aes_mixcolumns_xu_sun_107cnot_depth10.json) | [105 CNOT, depth 10](ir/results/quantum/aes_mixcolumns_repository_105cnot_depth10.json) | 2 fewer CNOT |

## Repository layout and provenance

```text
ir/results/       project-constructed result IR
ir/baselines/     directly comparable previous-best and supporting source IR
check/            standalone semantic, metric, comparison, and inventory checks
AGENTS.md         admission and maintenance rules
README.md         this index and verification guide
```

Classical JSON files contain complete straight-line programs. Quantum JSON
files contain complete layer schedules or point to QASM files stored alongside
them. The verifier recomputes target semantics and resources from those
programs rather than trusting their headline metrics.

Source PDFs and research-only evidence are intentionally absent. The IR retains
non-path evidence locators, page numbers, URLs where available, and SHA-256
identities, but no dead research-workspace paths. Every file-valued JSON
reference resolves inside this repository and is rehashed by the checker.

No separate license file is included because the repository policy permits only
IR, checkers, `AGENTS.md`, and this README. In the absence of an explicit
license, normal copyright restrictions apply.
