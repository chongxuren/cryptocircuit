# CryptoCircuit Verified IR

CryptoCircuit is the IR-only companion artifact for the AES and Ascon circuit
results reported through 7 September 2026. It contains complete result circuits,
complete directly comparable predecessor circuits, and standalone Python
checkers. It does not contain the paper, PDFs, research notes, search code,
solver logs, or unpublished candidates.

Each comparison fixes the function boundary, bit order, primitive basis, cost
rule, and any depth or workspace bound. Results from different rows are not
ranked against one another. Every listed construction is an upper bound unless
an exact lower bound is stated separately in the paper.

## Check everything

Python 3.9 or newer is sufficient; the checkers use only the standard library.

```sh
python3 check/verify_all.py
```

The command inventories the release, rejects paths into another checkout,
replays every straight-line program against its independently encoded target,
recomputes all reported resources, and checks every result/predecessor
comparison. A successful run ends with:

```text
PASS all: pairs=18 classical_records=28 quantum_pair_records=7 supporting_quantum_records=1
```

The narrower semantic checkers can also be run directly:

```sh
python3 check/verify_classical.py
python3 check/verify_quantum.py
```

## Classical results

| Component and model | Directly comparable predecessor | Result | Comparison |
|---|---:|---:|---|
| AES forward S-box; unit-cost `AND2/XOR2/XNOR2`; count objective | [112 gates, depth 25](ir/baselines/classical/aes_sbox_tay_112gate.json) | [109 gates, depth 34](ir/results/classical/aes_sbox_equiv_g19_t3_109gate.json) | 3 fewer gates; depth is not a hard bound |
| AES forward S-box; Feng nine-cell library; count objective | [93 cells, depth 22](ir/baselines/classical/aes_sbox_feng_93gate.json) | [85 cells, depth 29](ir/results/classical/aes_sbox_feng_equiv_g53_t6_85gate.json) | 8 fewer cells; depth is not a hard bound |
| AES combined forward/inverse S-box; six-cell library; depth at most 25 | [127 cells, 48 nonlinear](ir/baselines/classical/aes_combined_sbox_maximov_127gate.json) | [126 cells, 47 nonlinear](ir/results/classical/aes_combined_sbox_mixed_odc_window_126gate.json) | 1 fewer total and nonlinear cell |
| AES forward S-box; strict fan-in-two SLICE basis; depth at most 14 | [128 gates](ir/baselines/classical/aes_sbox_slice_depth14.json) | [127 gates](ir/results/classical/aes_sbox_slice_depth14_127gate.json) | 1 fewer linear gate |
| AES forward S-box; strict fan-in-two SLICE basis; depth at most 12 | [149 gates](ir/baselines/classical/aes_sbox_slice_depth12.json) | [148 gates](ir/results/classical/aes_sbox_slice_depth12_148gate.json) | 1 fewer linear gate |
| AES forward S-box; strict fan-in-two SLICE basis; depth at most 10 | [2738 gates, source-derived from Jia et al.](ir/baselines/classical/aes_sbox_jia_2026_dualrail_2738gate_depth10.json) | [216 gates](ir/results/classical/aes_sbox_slice_bilinear_depth10_216gate.json) | 2522 fewer gates at the same depth |
| AES MixColumns; `XOR2`; depth at most 3 | [99 XORs](ir/baselines/classical/aes_mixcolumns_shi_99xor_depth3.json) | [97 XORs](ir/results/classical/aes_mixcolumns_97xor_depth3.json) | 2 fewer XORs at the same depth |
| AES MixColumns; unit-cost `XOR2/XOR3/XOR4`; depth at most 3 | [44 gates](ir/baselines/classical/aes_mixcolumns_44xor_mixed_fanin_depth3.json) | [42 gates](ir/results/classical/aes_mixcolumns_42xor_mixed_fanin_depth3.json) | 2 fewer gates at the same depth |
| Ascon inverse S-box; exactly 6 ANDs; complement free | [32 XORs, depth 16](ir/baselines/classical/ascon_inverse_sbox_mcoptimal_binary_6and_32xor.json) | [13 XORs, depth 17](ir/results/classical/ascon_inverse_sbox_6and_13xor_depth17.json) | 19 fewer XORs; one-level tradeoff |
| Ascon inverse diffusion `Sigma_0`; free rotations; `XOR2` count | [1920 XORs, depth 5](ir/baselines/classical/ascon_sigma0_inverse_tezcan_balanced_1920xor.json) | [512 XORs, depth 6](ir/results/classical/ascon_sigma0_inverse_8word_512xor.json) | 1408 fewer XORs; one-level tradeoff |
| Ascon inverse diffusion `Sigma_1`; same model | [2048 XORs, depth 6](ir/baselines/classical/ascon_sigma1_inverse_tezcan_balanced_2048xor.json) | [512 XORs, depth 7](ir/results/classical/ascon_sigma1_inverse_8word_512xor.json) | 1536 fewer XORs; one-level tradeoff |
| Ascon inverse diffusion `Sigma_2`; same model | [2048 XORs, depth 6](ir/baselines/classical/ascon_sigma2_inverse_tezcan_balanced_2048xor.json) | [512 XORs, depth 6](ir/results/classical/ascon_sigma2_inverse_8word_512xor.json) | 1536 fewer XORs at the same depth |
| Ascon inverse diffusion `Sigma_3`; same model | [2048 XORs, depth 6](ir/baselines/classical/ascon_sigma3_inverse_tezcan_balanced_2048xor.json) | [512 XORs, depth 7](ir/results/classical/ascon_sigma3_inverse_8word_512xor.json) | 1536 fewer XORs; one-level tradeoff |
| Ascon inverse diffusion `Sigma_4`; same model | [2176 XORs, depth 6](ir/baselines/classical/ascon_sigma4_inverse_tezcan_balanced_2176xor.json) | [512 XORs, depth 7](ir/results/classical/ascon_sigma4_inverse_8word_512xor.json) | 1664 fewer XORs; one-level tradeoff |

## Logical quantum and reversible results

These are all-to-all logical circuits before device mapping or
Clifford+$T$ decomposition. The IR fixes qubit order, ancilla initialization
and cleanup, measurement and feed-forward policy, and the complete resource
vector.

| Component and model | Directly comparable predecessor | Result | Comparison |
|---|---:|---:|---|
| Ascon S-box; 15-qubit initialized isometry; 5 Toffolis at Toffoli depth 1 | [95 CNOTs, full depth 56](ir/baselines/quantum/ascon_sbox_huang_zhang_lin_toffoli_depth1_nct.json) | [44 CNOTs, full depth 19](ir/results/quantum/ascon_sbox_repository_toffoli_depth1_44cnot_depth19.json) | 51 fewer CNOTs and 37 fewer levels |
| AES S-box; 9-qubit isometry; one clean qubit | [833 Toffolis, full depth 1594](ir/baselines/quantum/aes_sbox_huang_zhang_lin_width9_nct.json) | [829 Toffolis, full depth 1581](ir/results/quantum/aes_sbox_repository_width9_829toffoli.json) | 4 fewer Toffolis, 2 fewer CNOTs, and 13 fewer levels |
| AES affine output accumulation; 26 qubits; minimize CNOT count | [68 CNOTs, 4 `X`, depth 12](ir/baselines/quantum/aes_sbox_jiang_output_suffix_direct_68cnot_depth12.json) | [53 CNOTs, 3 `X`, depth 11](ir/results/quantum/aes_sbox_output_suffix_repository_53cnot_depth11.json) | 15 fewer CNOTs, 1 fewer `X`, and 1 fewer level |
| Same AES affine output; favor CNOT depth | [68 CNOTs, CNOT/full depth 12](ir/baselines/quantum/aes_sbox_jiang_output_suffix_direct_68cnot_depth12.json) | [53 CNOTs, CNOT depth 10, full depth 11](ir/results/quantum/aes_sbox_output_suffix_repository_53cnot_cnotdepth10_fdepth11.json) | 15 fewer CNOTs and 2 fewer CNOT levels |

The verified [published seven-Toffoli Ascon witness](ir/baselines/quantum/ascon_sbox_huang_zhang_lin_width5_nct.json)
is included as supporting IR for the exact width-five theorem. In keeping with
the IR-only release policy, the exhaustive-search receipt that establishes the
six-Toffoli lower bound is not included here.

## Repository layout

```text
ir/results/       complete project-constructed result IR
ir/baselines/     complete directly comparable predecessor and supporting IR
check/            standalone semantic, metric, comparison, and inventory checks
AGENTS.md         admission and maintenance rules
README.md         this index
```

Classical JSON files contain complete straight-line programs. Quantum JSON
files contain complete layer schedules or reference QASM files stored beside
them. File-valued references are repository-relative and are rehashed by the
checker. No Git command is needed to run the verification.

No license file is included because this repository permits only IR, checkers,
`AGENTS.md`, and this README. In the absence of an explicit license, normal
copyright restrictions apply.
