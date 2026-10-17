# network-ci-pipeline

<img src="https://img.shields.io/badge/Python-3.10%2B-blue?style=flat-square&logo=python&logoColor=white" alt="Python 3.10+">
<img src="https://img.shields.io/badge/tests-183%20passing-brightgreen?style=flat-square" alt="Tests">
<img src="https://img.shields.io/badge/coverage-95%25-green?style=flat-square" alt="Coverage">
<img src="https://img.shields.io/badge/dependencies-zero%20runtime-brightgreen?style=flat-square" alt="Dependencies">
<img src="https://img.shields.io/badge/license-MIT-yellow?style=flat-square" alt="License">
<img src="https://img.shields.io/badge/platform-independent-blue?style=flat-square" alt="Platform">

Local CI pipeline that validates network configuration files before applying to equipment: syntax, business rules, golden config, simulated connectivity test, and report. The package has zero runtime dependencies and does not talk to any equipment.

## Problem / Why it exists

Network configuration scripts break in production, and almost always for three errors none of them catch: a typo, a command without the final deny, and a VLAN declared twice. None is hard to detect. All are impossible to detect after the damage.

This pipeline exists to be the place where those errors happen without consequence: it is a gate that prevents an invalid configuration from reaching the equipment. The strongest argument for whoever automates infrastructure is not "I automated", it is "I have a gate that prevents this from reaching the equipment".

Nothing here is real. SW-CORE-LAB does not exist. The configurations use Cisco-like syntax written for this project, and there is no SSH, SNMP, socket or device SDK anywhere.

## What it does

Reads a switch .cfg file and says what is wrong with it, stopping at the first stage that fails. Exit code is 0 when the candidate can proceed to merge, and non-zero when it cannot.

The stages run in this order:

1. syntax — does the file make sense as text? (vocabulary, types, limits)
2. rules — would it make sense in the lab? (inventory coherence)
3. golden — does it stay structurally complete? (presence of what cannot be missing, against the reference configuration)
4. tests — does the path exist? (addressing arithmetic, path logic)
5. report — what happened? (text for humans, JSON for machines)

Output for a candidate with a syntax error:

```
========================================================================
NETWORK CI - dados/candidatos/switch-ruins-sintaxe.cfg
========================================================================

STAGES
  syntax     1 error(s), 0 warning(s)
  rules      did not run (previous stage failed)
  golden     did not run (previous stage failed)
  tests      did not run (not requested: use --origem and --destino)

INTERRUPTED AT: syntax
The following stages depend on this one and were not executed.
Fix the finding above and run again.

FINDINGS
  [ERROR ] VALOR_INVALIDO
  where: line 56
  what: invalid port mode: 'trun'; accepted: access, dot1q-tunnel, dynamic, trunk
  how to fix: in Gi0/2, 'trun' almost always means 'trunk'

========================================================================
RESULT: FAILED
1 error(s) block the merge. The candidate cannot be applied.
```

All five candidates at once:

```
python -m netci pipeline dados/candidatos --golden dados/golden/switch-core.cfg
```

```
APPROVED            0 error(s)  0 warning(s)  switch-ok-1.cfg
APPROVED WITH WARNINGS  0 error(s)  1 warning(s)  switch-ok-2.cfg
APPROVED            0 error(s)  0 warning(s)  switch-ok-3.cfg
FAILED            3 error(s)  0 warning(s)  switch-ruins-regras.cfg
FAILED            1 error(s)  0 warning(s)  switch-ruins-sintaxe.cfg
```

Two severities, declared in each rule's code and inherited by the report:

| Severity | Effect |
| ERROR | blocks the merge |
| WARNING | does not block, deviation the reviewer needs to see |

The golden config does not compare equality. If it did, every legitimate change would fail and the team would learn to approve without reading. The comparison is about what cannot be missing in any healthy configuration: enable secret, line vty block with password, deny ip any any at the end of the ACL, spanning-tree mode and at least one trunk. What exists only in the golden is not a finding: an extra VLAN is a warning and passes, a missing interface is not an error.

## Stack

- Python 3.10+
- Standard library only: argparse, dataclasses, ipaddress, pathlib. No network, SSH or device SDK library.
- Development: pytest>=7.4, pytest-cov>=4.1
- Packaging: setuptools, `pip install -e ".[dev]"`
- CI: GitHub Actions, windows-latest, Python 3.11 (.github/workflows/ci.yml)

## How it works

The pipeline module decides the stage order and stops at the first stage that finds an ERROR. No stage knows the others exist.

| Module | Responsibility |
| parser.py | Reads the file into commands, interface blocks and line blocks |
| achado.py | Single type for all stages, with severity |
| sintaxe.py | Stage 1 — vocabulary, types and limits |
| regras.py | Stage 2 — inventory coherence |
| golden.py | Stage 3 — presence of what is structural |
| testes.py | Stage 4 — addressing arithmetic |
| pipeline.py | Stage order and stop rule |
| relatorio.py | Text for humans, JSON for machines |
| cli.py | validar, pipeline, regras |

Stop rule: the pipeline stops at the first stage with ERROR. The exception is the rules stage, which runs even when syntax fails. Duplicate VLAN and misspelled trunk are concurrent errors, not dependent ones: the second finding exists independent of the first, so it is worth running. If the second is a consequence of the first, the pipeline stops.

Findings come in severity order, not line order: whoever has forty warnings and one error needs to see the error first. A stage that appears as not run says why, in two distinct cases: previous stage failed, or not requested.

## How to run

Installation:

```
pip install -e ".[dev]"
```

Validate a candidate:

```
python -m netci validar dados/candidatos/switch-ruins-sintaxe.cfg --golden dados/golden/switch-core.cfg
```

Validate all candidates in a folder:

```
python -m netci pipeline dados/candidatos --golden dados/golden/switch-core.cfg
```

List the 24 rules by stage:

```
python -m netci regras
```

Run the tests:

```
python -m pytest
```

The suite has 183 passing tests and 95 percent coverage. The 70 percent floor is enforced in pyproject.toml; below it the build fails.

## Project structure

```
network-ci-pipeline/
├── src/netci/            source code of the netci package
├── dados/candidatos/     five .cfg files to validate
├── dados/golden/         reference configuration switch-core.cfg
├── tests/                183 tests (parser, stages, pipeline, report, CLI, encoding gate)
├── tools/                verificar_aceite.py, verificar_encoding.py, gerar_exemplo.py
├── docs/                 regras-de-ci-em-rede.md, o-que-bloquear-em-ci.md
├── exemplos/relatorio-ci.md  example report generated by the pipeline
├── .github/workflows/ci.yml  CI on GitHub Actions
├── pyproject.toml        package config, 70 percent coverage floor
├── requirements.txt      development dependencies
└── LICENSE               MIT
```

## Trade-offs and decisions

- Stopping at the first ERROR costs information (a report with one problem instead of seven), but prevents a syntax error from becoming false business problems in later stages.
- The rules stage runs after syntax fails because the problems are concurrent, not dependent: fixing one does not make the other disappear.
- Golden config is not strict equality: legitimate changes (new VLAN, extra interface) cannot fail; what is missing only in the reference is a warning, not an error.
- Blocks are delimited by indentation, not by exit. Equipment configuration rarely closes a block with exit, and requiring exit would fail real configuration.
- Exit code 0 also with warnings: warning does not block the merge. Only ERROR returns 1; read error returns 2.
- One candidate per run. The pipeline command runs a folder, but evaluates each file independently, with no comparison between candidates.

## Known limitations

- The syntax is fictional Cisco-like. The files are plausible, not real output of any product. A real device requires a rewritten parser.
- Does not talk to equipment: no SSH, SNMP, socket or SDK. Does not verify the device accepts the configuration, whether the hardware supports the request, or system version compatibility.
- The connectivity test does not simulate packet inspection. Any deny does not close the path; only deny ip any any closes. It is IPv4 address arithmetic, not runtime data.
- The ACL is evaluated at ingress, globally. The lab does not model direction, application interface, or evaluation order.
- The vocabulary is closed and small. A command outside the list becomes an error. For equipment from several vendors, the list would need to grow and the error-vs-warning decision for unknown lines would have to be revisited for each new device.
- One candidate per run. There is no batch validation beyond the pipeline, nor comparison between candidates.
- A file can pass here and be rejected at the device's first commit.

## License

MIT.

## Author

Kelvin Oliveira