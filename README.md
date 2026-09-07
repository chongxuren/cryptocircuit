# CryptoCircuit Verified IR

CryptoCircuit is the AES/Ascon-only IR companion to Tables 2 and 3 of
*Proof-Aware Reductions for Verified Cryptographic Circuit Synthesis*, dated
8 September 2026.
The final paper PDF has SHA-256
`8b5f72a20feecb9c59e8c32389f75829d215d35b780ecdbb41288180c3c7621a`.
This repository contains complete circuit IR, complete directly comparable
predecessor IR, and standalone standard-library checkers. It does not contain
the paper, PDFs, research notes, search code, solver logs, receipts, or
unpublished candidates.

The two tables below reproduce paper Tables 2 and 3 row-for-row and
column-for-column; paper citation markers are omitted and local IR links are
added where this repository publishes a checked pair. The PICCOLO and SM4 rows
and the proof-only AES MixColumns retained-copy row are included for table
alignment, but remain unlinked because this repository admits only complete
AES/Ascon result/predecessor IR pairs.

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
PASS all: table_comparisons=28 checkpoint_comparisons=9 classical_records=39 quantum_records=27 supporting_theorem_records=2
```

The narrower semantic checkers can also be run directly:

```sh
python3 -B check/verify_classical.py
python3 -B check/verify_quantum.py
```

## Paper Table 2: Classical circuit results

Values are comparable only within the fixed model of their row.

| Component | Target | Model | Prior | New |
|---|---|---|---:|---:|
| PICCOLO 4-bit S-box | Prove #AND and AND depth exactly | Free-affine binary XOR-AND straight-line programs; `msb0` lookup table | 4 nonlinear gates at depth 2, source construction | exact 4 AND; exact AND depth 2 by SKINNY transfer |
| AES S-box | Minimize total gates | `AND2/XOR2/XNOR2`; unit cost; no depth bound | [112, depth 25](ir/baselines/classical/aes_sbox_tay_112gate.json) | [109, depth 34](ir/results/classical/aes_sbox_equiv_g19_t3_109gate.json) |
| AES S-box | Minimize cells in a fixed-middle shell family | Maximov-Ekdahl mixed cells; unit cost; no depth bound | [102, depth 24](ir/baselines/classical/aes_sbox_maximov_102gate.json) | [101, depth 32](ir/results/classical/aes_sbox_maximov_equiv_g05_t2_101gate.json) |
| AES S-box | Minimize total cells | Feng rich-cell library; unit cost; no depth bound | [93, depth 22](ir/baselines/classical/aes_sbox_feng_93gate.json) | [84, depth 29](ir/results/classical/aes_sbox_feng_equiv_g53_t6_84gate.json) |
| AES forward/inverse S-box | Minimize cells subject to depth <= 25 | Unit-cost `XOR`, `XNOR`, `NAND`, `NOR`, `MUX`, and `NMUX` cells | [126, depth 25, repository intermediate](ir/baselines/classical/aes_combined_sbox_mixed_odc_window_126gate.json) | [125, depth 25](ir/results/classical/aes_combined_sbox_context_quotient_125gate.json) |
| AES S-box | Minimize gates subject to depth <= 14 | Fan-in-two `XOR/XNOR/NAND/NOR`; unit cost | [128, depth 14](ir/baselines/classical/aes_sbox_slice_depth14.json) | [126, depth 14](ir/results/classical/aes_sbox_slice_depth14_126gate.json) |
| AES S-box | Minimize gates subject to depth <= 13 | Fan-in-two `XOR/XNOR/NAND/NOR`; unit cost | [136, depth 13](ir/baselines/classical/aes_sbox_slice_depth13.json) | [135, depth 13](ir/results/classical/aes_sbox_slice_depth13_135gate.json) |
| AES S-box | Minimize gates subject to depth <= 12 | Fan-in-two `XOR/XNOR/NAND/NOR`; unit cost | [149, depth 12](ir/baselines/classical/aes_sbox_slice_depth12.json) | [148, depth 12](ir/results/classical/aes_sbox_slice_depth12_148gate.json) |
| AES S-box | Reduce depth below 12; report gate count | Fan-in-two `XOR/XNOR/NAND/NOR`; unit cost | [149, depth 12](ir/baselines/classical/aes_sbox_slice_depth12.json) | [173, depth 11](ir/results/classical/aes_sbox_slice_global_depth11_173gate.json) |
| AES S-box | Minimize gates subject to depth <= 10 | Fan-in-two `XOR/XNOR/NAND/NOR`; unit cost | [2738, depth 10, source-derived](ir/baselines/classical/aes_sbox_jia_2026_dualrail_2738gate_depth10.json) | [216, depth 10](ir/results/classical/aes_sbox_slice_bilinear_depth10_216gate.json) |
| AES MixColumns | Minimize #XOR subject to depth <= 3 | `XOR2` only; fan-out and permutations free | [99, depth 3](ir/baselines/classical/aes_mixcolumns_shi_99xor_depth3.json) | [97, depth 3](ir/results/classical/aes_mixcolumns_97xor_depth3.json) |
| AES MixColumns | Minimize gates subject to depth <= 3 | Unit-cost `XOR2/XOR3/XOR4`; fan-out and permutations free | [44, depth 3](ir/baselines/classical/aes_mixcolumns_44xor_mixed_fanin_depth3.json) | [42, depth 3](ir/results/classical/aes_mixcolumns_42xor_mixed_fanin_depth3.json) |
| AES MixColumns selector | Minimize gates at nonlinear depth <= 1 | 33-input Boolean circuit; unit-cost `AND2/XOR2/XNOR2` | [166, depth 9, repository intermediate](ir/baselines/classical/aes_selector_mixcolumns_rank16_166gate.json) | [161, depth 9; exact 16 AND](ir/results/classical/aes_selector_mixcolumns_rank16_161gate.json) |
| Ascon inverse S-box | Minimize #XOR at exactly 6 AND | Binary `AND2/XOR2`; complement free | [13 XOR, depth 17, repository intermediate](ir/baselines/classical/ascon_inverse_sbox_6and_13xor_depth17.json) | [12 XOR, depth 19](ir/results/classical/ascon_inverse_sbox_6and_12xor_depth19.json) |
| Ascon inverse diffusion | Minimize #XOR; report depth for all five maps | `XOR2` only; rotations, fan-out, and permutations free | [1920, 2048, 2048, 2048, 2176; depths 5, 6, 6, 6, 6](ir/baselines/classical/ascon_sigma0_inverse_tezcan_balanced_1920xor.json) | [5 x 512; depths 6, 7, 6, 7, 7](ir/results/classical/ascon_sigma0_inverse_8word_512xor.json) |
| SM4 `T` transform | Minimize gates subject to depth <= 23 | Binary XAG; complement free; 136 nonlinear gates | 644, depth 23, source-derived | 580, depth 23 |
| SM4 `T'` transform | Minimize gates subject to depth <= 21 | Binary XAG; complement free; 136 nonlinear gates | 580, depth 21, source-derived | 556, depth 21 |
| SM4 S-box | Minimize gates at exactly 41 nonlinear gates | Binary XAG; complement free | 107, depth 25 | 106, depth 25 |
| SM4 S-box | Minimize gates subject to at most 32 nonlinear gates | Binary XAG; complement free | 120, depth 27 | 110, depth 27 |

## Paper Table 3: Logical quantum and reversible results

Every row is pre-device-mapping and uses all-to-all logical connectivity. The
IR fixes qubit order, ancilla initialization and cleanup, measurement and
feed-forward policy, and the complete resource vector.

| Component | Target | Model | Prior | New |
|---|---|---|---:|---:|
| Ascon S-box | Minimize #CNOT at Toffoli depth 1 | 15-qubit isometry; `X/CNOT/Toffoli`; 5 Toffoli | [95 CNOT, full depth 56](ir/baselines/quantum/ascon_sbox_huang_zhang_lin_toffoli_depth1_nct.json) | [42 CNOT, full depth 19](ir/results/quantum/ascon_sbox_repository_toffoli_depth1_42cnot_depth19.json) |
| Ascon S-box | Minimize #Toffoli exactly | 5-qubit permutation; no ancilla; `X/CNOT/Toffoli` | [7-Toffoli witness](ir/baselines/quantum/ascon_sbox_huang_zhang_lin_width5_nct.json) | exact minimum 7 Toffoli |
| Specialized Ascon S-box | Minimize total gates and #Toffoli | 5-qubit `S(x0,x1,x2 xor 1,x3,x4)`; no ancilla; logical NCT | [17 gates, 7 Toffoli, depths 11/53](ir/baselines/quantum/ascon_sbox_round_constant_x2_specialized_17gate_nct.json) | [16 gates; exact 7 Toffoli; depths 11/53](ir/results/quantum/ascon_sbox_round_constant_x2_specialized_16gate_nct.json) |
| Ascon retained-copy linear layer | Minimize CNOTs at depth <= 3 and bound depth <= 4 | 640-wire `(x,0^320) -> (L(x),x)`; CNOT only; fixed terminal order | [960 CNOT, depth 3](ir/baselines/quantum/ascon_linear_oh_et_al_copy_960cnot_depth3.json) | exact 960 CNOT at depth <= 3; 480-960 at depth <= 4 |
| AES MixColumns retained copy | Prove depth/count lower bounds | 64-wire `(x,0^32) -> (MixColumns(x),x)`; CNOT only; fixed order; depth <= 4 for count | No same-boundary circuit; 32-wire in-place target is incomparable | depth >= 4; if depth <= 4, at least 70 CNOT |
| Ascon linear layer | Minimize CNOTs; report depth | 320-qubit in-place CNOT unitary; free declared input placement; no ancilla | [1,595 CNOT, depth 45, repository reschedule](ir/baselines/quantum/ascon_linear_commutation_rescheduled_inplace_1595cnot_depth45.json) | [1,525/45](ir/results/quantum/ascon_linear_local_rewrite_inplace_1525cnot_depth45.json); [1,502/46 Pareto](ir/results/quantum/ascon_linear_local_rewrite_inplace_1502cnot_depth46.json) |
| Ascon `p_L` after `p_S` core | Minimize gates subject to depth <= 56 | 320-qubit in-place logical NCT; free declared input placement; no ancilla | [2,619 gates, depth 56, source-composed](ir/baselines/quantum/ascon_round_core_guo_xzlbz_2619gate_depth56.json) | [2,549/56](ir/results/quantum/ascon_round_core_guo_linear_rewrite_2549gate_depth56.json); [2,526/57 Pareto](ir/results/quantum/ascon_round_core_guo_linear_rewrite_2526gate_depth57.json) |
| AES S-box | Minimize #Toffoli | 9-qubit isometry; one clean qubit; `X/CNOT/Toffoli` | [833 Toffoli, full depth 1594](ir/baselines/quantum/aes_sbox_huang_zhang_lin_width9_nct.json) | [829 Toffoli, full depth 1581](ir/results/quantum/aes_sbox_repository_width9_829toffoli.json) |
| AES output suffix | Minimize #CNOT | 26-qubit affine accumulation; `CNOT/X`; no ancilla | [68 CNOT, 4 X, depth 12](ir/baselines/quantum/aes_sbox_jiang_output_suffix_direct_68cnot_depth12.json) | [51 CNOT, 3 X, depth 11](ir/results/quantum/aes_sbox_output_suffix_repository_51cnot_depth11.json); [53-CNOT depth-10 tradeoff](ir/results/quantum/aes_sbox_output_suffix_repository_53cnot_cnotdepth10_fdepth11.json) |
| Keyed AES column | Minimize #CNOT | 68-qubit SubBytes-MixColumns-AddRoundKey isometry; 4 clean qubits; logical NCT | [3,669 CNOT, depth 1592, repository composition](ir/baselines/quantum/aes_keyed_subbytes_mixcolumns_column_3669cnot.json) | [3,668 CNOT, depth 1592](ir/results/quantum/aes_keyed_subbytes_mixcolumns_column_3668cnot.json) |

## Repository-specific evidence links

The consolidated Ascon inverse-diffusion row expands to five independently
checked result/baseline pairs: [`Sigma_0`](ir/results/classical/ascon_sigma0_inverse_8word_512xor.json),
[`Sigma_1`](ir/results/classical/ascon_sigma1_inverse_8word_512xor.json),
[`Sigma_2`](ir/results/classical/ascon_sigma2_inverse_8word_512xor.json),
[`Sigma_3`](ir/results/classical/ascon_sigma3_inverse_8word_512xor.json), and
[`Sigma_4`](ir/results/classical/ascon_sigma4_inverse_8word_512xor.json), with
their corresponding [`Sigma_0`](ir/baselines/classical/ascon_sigma0_inverse_tezcan_balanced_1920xor.json),
[`Sigma_1`](ir/baselines/classical/ascon_sigma1_inverse_tezcan_balanced_2048xor.json),
[`Sigma_2`](ir/baselines/classical/ascon_sigma2_inverse_tezcan_balanced_2048xor.json),
[`Sigma_3`](ir/baselines/classical/ascon_sigma3_inverse_tezcan_balanced_2048xor.json), and
[`Sigma_4`](ir/baselines/classical/ascon_sigma4_inverse_tezcan_balanced_2176xor.json)
baselines.

The standalone verifier also retains direct checkpoints that are discussed in
the paper text rather than separate overview rows: the AES Feng
[85-cell checkpoint](ir/baselines/classical/aes_sbox_feng_equiv_g53_t6_85gate.json),
the AES depth-14 [127-gate checkpoint](ir/baselines/classical/aes_sbox_slice_depth14_127gate.json),
the inverse-Ascon [32-XOR source comparator](ir/baselines/classical/ascon_inverse_sbox_mcoptimal_binary_6and_32xor.json),
the Ascon isometry [43-CNOT](ir/baselines/quantum/ascon_sbox_repository_toffoli_depth1_43cnot_depth19.json)
and [44-CNOT](ir/baselines/quantum/ascon_sbox_repository_toffoli_depth1_44cnot_depth19.json)
checkpoints, the combined-AES [127-cell source comparator](ir/baselines/classical/aes_combined_sbox_maximov_127gate.json),
the Ascon round-core [2,550-gate checkpoint](ir/baselines/quantum/ascon_round_core_guo_linear_rewrite_2550gate_depth56.json),
and the AES suffix [52-CNOT checkpoint](ir/baselines/quantum/aes_sbox_output_suffix_repository_52cnot_depth11.json).

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
