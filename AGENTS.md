# CryptoCircuit Publication Repository Rules

## Purpose

This repository is a minimal, independently checkable publication of circuit
results. It is not a research workspace, paper archive, search-code release, or
general circuit corpus.

Only AES and Ascon results that satisfy every rule below may be published here.

## Allowed contents

Apart from Git metadata, the repository may contain only:

- `AGENTS.md`, containing these repository rules;
- `README.md`, documenting the published pairs and exact verification commands;
- `ir/results/`, containing complete machine-readable IR for results constructed
  by the project;
- `ir/baselines/`, containing complete machine-readable IR for the directly
  comparable previous best circuits; and
- `check/`, containing only the standalone scripts needed to validate the IR,
  recompute its metrics, compare each result with its baseline, and run all
  checks easily.

Do not add papers, PDFs, manuscripts, research notes, literature surveys,
optimization or synthesis code, circuit generators, solver inputs, proof-search
logs, receipts, benchmark dumps, vendored dependencies, binaries, caches,
rendered assets, or unrelated examples.

## Admission requirements

Every published result must:

1. implement a frozen AES or Ascon function and boundary;
2. have a complete machine-readable IR in `ir/results/`;
3. have a complete, source-faithful, directly comparable previous-best IR in
   `ir/baselines/` under the same function, bit order, representation, gate
   basis, cost/depth model, and hard bounds;
4. include provenance and evidence metadata in the IR itself;
5. pass the standalone checker, including independent functional equivalence
   and metric recomputation;
6. strictly improve at least one declared objective without worsening a hard
   bound; and
7. be listed in `README.md` with exact commands and evidence status.

If a predecessor is incomplete, reconstructed without source support, or not
checkable under the same model, do not publish the result pair here. A solver
timeout or unchecked UNSAT result is not an optimality proof.

## Model separation

Keep classical irreversible, reversible, logical-quantum, compiled-device, and
fault-tolerant records separate. Never rank or combine incomparable metrics.
Quantum records additionally must freeze the implemented unitary or oracle,
qubit order, gate set, ancilla initialization and cleanup, measurement and
feed-forward policy, connectivity assumptions, and metric level.

## Verification and changes

- Checking scripts must use the Python standard library unless the README names
  and pins an unavoidable dependency.
- A clean checkout must be verifiable with one documented command.
- Checkers must reject malformed or unsupported IR rather than silently skipping
  it.
- Every file-valued IR reference must be repository-relative and resolve to a
  tracked file in this repository. Never retain paths into another checkout,
  home directory, temporary directory, or excluded research artifact.
- Excluded source evidence may be identified by a non-path locator, stable URL,
  and digest, but it must not be required to run the published checks.
- Recompute functions and metrics from the straight-line program; do not trust
  headline counts stored in the IR.
- Keep result/baseline pairing explicit and deterministic.
- Before every commit, run the complete checker and audit the repository tree
  against the allowed-content list above.
- Make focused, non-force commits. Never commit an unverified or partially
  admitted result.
