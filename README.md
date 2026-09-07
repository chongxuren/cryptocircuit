# CryptoCircuit Verified IR

CryptoCircuit is the AES/Ascon-only IR companion to Tables 1 and 2 of
*Circuit Improvements for Cryptographic Components*, dated 7 September 2026.
The final paper PDF has SHA-256
`2e883a9c2c508d51717d8be4d85a59f21c6fcf9297f90092fb42a1089c453fbd`.
This repository contains complete circuit IR, complete directly comparable
predecessor IR, and standalone standard-library checkers. It does not contain
the paper, PDFs, research notes, search code, solver logs, receipts, or
unpublished candidates.

The paper's classical table also has four SM4 rows. They are intentionally not
duplicated here because this publication repository admits only AES and Ascon.
The AES and Ascon rows below otherwise reproduce the final PDF table values.

Each comparison fixes the function boundary, bit order, primitive basis, cost
rule, and stated depth or workspace bound. Results from different rows are not
ranked against one another. Every construction is an upper bound unless a
separate exact result is identified. The two exact Ascon rows include their
upper-bound witnesses here; their lower-bound proof artifacts remain in the
paper/research workspace and are not part of this IR-only release.

## Check everything

Python 3.9 or newer is sufficient; the checkers use only the standard library.

```sh
python3 -B check/verify_all.py
```

The command inventories the release, rejects paths into another checkout,
replays every straight-line program against its independently encoded target,
recomputes all reported resources, and checks both the final-table comparisons
and the direct repository checkpoints. A successful run ends with:

```text
PASS all: table_comparisons=28 checkpoint_comparisons=7 classical_records=38 quantum_records=26 supporting_theorem_records=2
```

The narrower semantic checkers can also be run directly:

```sh
python3 -B check/verify_classical.py
python3 -B check/verify_quantum.py
```

## Classical AES and Ascon results

| Component and model | PDF prior | PDF new | Verified comparison |
|---|---:|---:|---|
| AES forward S-box; unit-cost `AND2/XOR2/XNOR2`; count objective | [112 gates, depth 25](ir/baselines/classical/aes_sbox_tay_112gate.json) | [109 gates, depth 34](ir/results/classical/aes_sbox_equiv_g19_t3_109gate.json) | 3 fewer gates; depth is not a hard bound |
| AES forward S-box; Maximov-Ekdahl mixed-cell fixed-middle shell family; count objective | [102 cells, depth 24](ir/baselines/classical/aes_sbox_maximov_102gate.json) | [101 cells, depth 32](ir/results/classical/aes_sbox_maximov_equiv_g05_t2_101gate.json) | 1 fewer cell; depth is not a hard bound |
| AES forward S-box; Feng rich-cell library; count objective | [93 cells, depth 22](ir/baselines/classical/aes_sbox_feng_93gate.json) | [84 cells, depth 29](ir/results/classical/aes_sbox_feng_equiv_g53_t6_84gate.json) | 9 fewer than the source circuit and 1 fewer than the [85-cell direct checkpoint](ir/baselines/classical/aes_sbox_feng_equiv_g53_t6_85gate.json); depth is not a hard bound |
| AES combined forward/inverse S-box; six-cell library; depth at most 25 | [126 cells, 47 nonlinear, depth 25](ir/baselines/classical/aes_combined_sbox_mixed_odc_window_126gate.json) | [125 cells, 47 nonlinear, depth 25](ir/results/classical/aes_combined_sbox_context_quotient_125gate.json) | 1 fewer linear and total cell; the [127-cell source comparator](ir/baselines/classical/aes_combined_sbox_maximov_127gate.json) is retained |
| AES forward S-box; strict fan-in-two `XOR/XNOR/NAND/NOR`; depth at most 14 | [128 gates, depth 14](ir/baselines/classical/aes_sbox_slice_depth14.json) | [126 gates, depth 14](ir/results/classical/aes_sbox_slice_depth14_126gate.json) | 2 fewer gates; also 1 fewer than the [127-gate direct checkpoint](ir/baselines/classical/aes_sbox_slice_depth14_127gate.json) |
| AES forward S-box; same strict basis; depth at most 13 | [136 gates, depth 13](ir/baselines/classical/aes_sbox_slice_depth13.json) | [135 gates, depth 13](ir/results/classical/aes_sbox_slice_depth13_135gate.json) | 1 fewer linear and total gate |
| AES forward S-box; same strict basis; depth at most 12 | [149 gates, depth 12](ir/baselines/classical/aes_sbox_slice_depth12.json) | [148 gates, depth 12](ir/results/classical/aes_sbox_slice_depth12_148gate.json) | 1 fewer linear and total gate |
| AES forward S-box; same strict basis; reduce depth below 12 | [149 gates, depth 12](ir/baselines/classical/aes_sbox_slice_depth12.json) | [173 gates, depth 11](ir/results/classical/aes_sbox_slice_global_depth11_173gate.json) | 1 fewer level for 24 more gates |
| AES forward S-box; same strict basis; depth at most 10 | [2738 gates, depth 10, source-derived](ir/baselines/classical/aes_sbox_jia_2026_dualrail_2738gate_depth10.json) | [216 gates, depth 10](ir/results/classical/aes_sbox_slice_bilinear_depth10_216gate.json) | 2522 fewer gates at the same depth |
| AES MixColumns; `XOR2`; depth at most 3 | [99 XORs, depth 3](ir/baselines/classical/aes_mixcolumns_shi_99xor_depth3.json) | [97 XORs, depth 3](ir/results/classical/aes_mixcolumns_97xor_depth3.json) | 2 fewer XORs at the same depth |
| AES MixColumns; unit-cost `XOR2/XOR3/XOR4`; depth at most 3 | [44 gates, depth 3](ir/baselines/classical/aes_mixcolumns_44xor_mixed_fanin_depth3.json) | [42 gates, depth 3](ir/results/classical/aes_mixcolumns_42xor_mixed_fanin_depth3.json) | 2 fewer gates at the same depth |
| AES MixColumns/InvMixColumns selector; 33-input unit-cost `AND2/XOR2/XNOR2`; nonlinear depth at most 1 | [166 gates, depth 9](ir/baselines/classical/aes_selector_mixcolumns_rank16_166gate.json) | [161 gates, depth 9; exactly 16 ANDs](ir/results/classical/aes_selector_mixcolumns_rank16_161gate.json) | 5 fewer XORs; same exact 16-AND nonlinear layer |
| Ascon inverse S-box; exactly 6 ANDs; complement free | [32 XORs, depth 16](ir/baselines/classical/ascon_inverse_sbox_mcoptimal_binary_6and_32xor.json) | [13 XORs, depth 17](ir/results/classical/ascon_inverse_sbox_6and_13xor_depth17.json) | 19 fewer XORs; one-level tradeoff |
| Ascon inverse diffusion `Sigma_0` through `Sigma_4`; `XOR2`; rotations, fan-out, and permutations free | [1920/2048/2048/2048/2176 XORs; depths 5/6/6/6/6](ir/baselines/classical/ascon_sigma0_inverse_tezcan_balanced_1920xor.json) | [512/512/512/512/512 XORs; depths 6/7/6/7/7](ir/results/classical/ascon_sigma0_inverse_8word_512xor.json) | The five independently checked result records are [`Sigma_0`](ir/results/classical/ascon_sigma0_inverse_8word_512xor.json), [`Sigma_1`](ir/results/classical/ascon_sigma1_inverse_8word_512xor.json), [`Sigma_2`](ir/results/classical/ascon_sigma2_inverse_8word_512xor.json), [`Sigma_3`](ir/results/classical/ascon_sigma3_inverse_8word_512xor.json), and [`Sigma_4`](ir/results/classical/ascon_sigma4_inverse_8word_512xor.json); the corresponding baselines are checked separately |

## Logical quantum and reversible AES and Ascon results

All rows are all-to-all logical circuits before device mapping or
Clifford+$T$ decomposition. The IR fixes qubit order, ancilla initialization
and cleanup, measurement and feed-forward policy, and the complete resource
vector.

| Component and model | PDF prior | PDF new | Repository evidence |
|---|---:|---:|---|
| Ascon S-box; 15-qubit initialized isometry; 5 Toffolis at Toffoli depth 1 | [95 CNOTs, full depth 56](ir/baselines/quantum/ascon_sbox_huang_zhang_lin_toffoli_depth1_nct.json) | [43 CNOTs, full depth 19](ir/results/quantum/ascon_sbox_repository_toffoli_depth1_43cnot_depth19.json) | 52 fewer CNOTs and 37 fewer levels; also 1 CNOT below the [44-CNOT direct checkpoint](ir/baselines/quantum/ascon_sbox_repository_toffoli_depth1_44cnot_depth19.json) |
| Ascon S-box; 5-qubit permutation; no ancilla; exact Toffoli objective | [7-Toffoli witness](ir/baselines/quantum/ascon_sbox_huang_zhang_lin_width5_nct.json) | Exact minimum 7 Toffolis in the paper | The complete 7-Toffoli witness is replayed here; the exhaustive six-Toffoli exclusion is intentionally not included |
| Specialized Ascon S-box `S(x0,x1,x2 xor 1,x3,x4)`; 5-qubit logical NCT | [17 gates, logical/source-weighted depths 11/53](ir/baselines/quantum/ascon_sbox_round_constant_x2_specialized_17gate_nct.json) | [16 gates, depths 11/53](ir/results/quantum/ascon_sbox_round_constant_x2_specialized_16gate_nct.json) | 1 fewer `X` and total gate |
| Ascon retained-copy linear layer; 640-wire `(x,0^320) -> (L(x),x)`; CNOT; depth at most 3 | [960 CNOTs, depth 3](ir/baselines/quantum/ascon_linear_oh_et_al_copy_960cnot_depth3.json) | Exact minimum 960 CNOTs in the paper | The complete 960-CNOT construction is replayed here; the structural lower-bound proof is intentionally not included |
| Ascon in-place linear layer; 320 qubits; CNOT; free declared input placement | [1595 CNOTs, depth 45](ir/baselines/quantum/ascon_linear_commutation_rescheduled_inplace_1595cnot_depth45.json) | [1525 CNOTs/depth 45](ir/results/quantum/ascon_linear_local_rewrite_inplace_1525cnot_depth45.json); [1502/depth 46 Pareto](ir/results/quantum/ascon_linear_local_rewrite_inplace_1502cnot_depth46.json) | 70 fewer CNOTs at depth 45; the Pareto point saves 93 CNOTs for one extra level |
| Ascon `p_L` after `p_S` core; 320-qubit in-place logical NCT | [2619 gates, depth 56](ir/baselines/quantum/ascon_round_core_guo_xzlbz_2619gate_depth56.json) | [2549 gates/depth 56](ir/results/quantum/ascon_round_core_guo_linear_rewrite_2549gate_depth56.json); [2526/depth 57 Pareto](ir/results/quantum/ascon_round_core_guo_linear_rewrite_2526gate_depth57.json) | 70 fewer gates at depth 56; the Pareto point saves 93 gates for one extra level; the [2550-gate direct checkpoint](ir/baselines/quantum/ascon_round_core_guo_linear_rewrite_2550gate_depth56.json) is retained |
| AES S-box; 9-qubit isometry; one clean qubit; logical NCT | [833 Toffolis, full depth 1594](ir/baselines/quantum/aes_sbox_huang_zhang_lin_width9_nct.json) | [829 Toffolis, full depth 1581](ir/results/quantum/aes_sbox_repository_width9_829toffoli.json) | 4 fewer Toffolis, 2 fewer CNOTs, and 13 fewer levels |
| AES affine output accumulation; 26 qubits; CNOT/`X`; no ancilla | [68 CNOTs, 4 `X`, depth 12](ir/baselines/quantum/aes_sbox_jiang_output_suffix_direct_68cnot_depth12.json) | [51 CNOTs, 3 `X`, depth 11](ir/results/quantum/aes_sbox_output_suffix_repository_51cnot_depth11.json); [53-CNOT CNOT-depth-10 tradeoff](ir/results/quantum/aes_sbox_output_suffix_repository_53cnot_cnotdepth10_fdepth11.json) | 17 fewer CNOTs, 1 fewer `X`, and 1 fewer full-depth level; also 1 CNOT below the [52-CNOT direct checkpoint](ir/baselines/quantum/aes_sbox_output_suffix_repository_52cnot_depth11.json) |
| Keyed AES SubBytes-MixColumns-AddRoundKey column; 68-qubit logical NCT isometry | [3669 CNOTs, depth 1592](ir/baselines/quantum/aes_keyed_subbytes_mixcolumns_column_3669cnot.json) | [3668 CNOTs, depth 1592](ir/results/quantum/aes_keyed_subbytes_mixcolumns_column_3668cnot.json) | 1 fewer CNOT and total gate; all other frozen coordinates unchanged |

## Repository layout and evidence boundary

```text
ir/results/       complete project-constructed result IR
ir/baselines/     complete directly comparable predecessor and supporting IR
check/            standalone semantic, metric, comparison, and inventory checks
AGENTS.md         admission and maintenance rules
README.md         this table-aligned index
```

Classical JSON files contain complete straight-line programs. Quantum JSON
files contain complete layer schedules or reference QASM stored beside them.
Every file-valued reference resolves inside this repository and is rehashed by
the checker. Excluded source evidence remains identified by non-path locators
and SHA-256 digests, but is not needed to reproduce any circuit check.

No license file is included because this repository permits only IR, checkers,
`AGENTS.md`, and this README. In the absence of an explicit license, normal
copyright restrictions apply.
