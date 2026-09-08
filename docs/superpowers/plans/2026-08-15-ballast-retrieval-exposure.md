# Ballast Retrieval Exposure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Repair Ballast backlog repository routing, then add a deterministic, report-only retrieval exposure diagnostic that compares retrieved source-slot share with corpus chunk share.

**Architecture:** DX-8 first fixes the vendored backlog tool so `repo-path ballast` resolves the repository root in both a primary checkout and a linked worktree. EVAL-24 adds pure information-theory and canonical-hash functions under `ballast.eval.metrics`, then a standalone CLI wires the existing deterministic hashing retriever to the fixed golden set. The output is an isolated strict-JSON artifact and never enters eval history, production RAG, or the merge gate.

**Tech Stack:** Python 3.11, pytest, Pydantic golden records, repository-native `HashingEmbedder`, `InMemoryVectorStore`, and `Retriever`.

**Spec:** `specs/BACKLOG.md` items `DX-8` and `EVAL-24`, committed at `91f3225` on this branch.

## Global Constraints

- Use profile name `hashing-baseline-v1`, `HashingEmbedder(dim=4096)`, `InMemoryVectorStore`, corpus chunk size `256`, overlap `40`, and direct `Retriever.retrieve(question, k=4)` exactly once per parsed golden record in file order.
- Source identity is `Retrieved.chunk.source.strip()`. Corpus expectation counts chunks and retrieval observation counts returned top-k slots; repeated source IDs count once per slot.
- Corpus hash rows contain exactly `chunk_id`, `source`, `url`, `title`, `heading_path`, and `text`, sorted by `chunk_id`. Golden hash rows use parsed records in file order. Both use compact sorted-key UTF-8 JSONL with LF terminators.
- JSD and Shannon entropy use base 2. Effective sources equal `2 ** entropy_bits`. Strict JSON uses `allow_nan=False`.
- Blank source IDs or zero retrieved slots return `status: not_estimable` with a reason. Unexpected execution errors return `status: failed`, write a strict artifact, and make only the standalone CLI exit nonzero.
- The CLI requires `--output PATH`; stdout contains no logs. `not_estimable` exits zero because it is a valid diagnostic state. `failed` exits one. This ruling does not change `ballast.eval.gate`.
- Preserve raw `Chunk.source` in the corpus hash and strip it only for exposure distribution identity.
- Never call an LLM, gateway hook, generation, document grader, query transform, retry, hybrid fusion, reranker, or production pipeline.
- Never write the corpus, existing eval results, thresholds, or gate exit behavior. `retrieval_exposure.py` itself never reads or writes `eval/history.jsonl`, and no `retrieval_exposure` field may enter that ledger. One exception was owner-authorized on 2026-08-16: the canonical 89-case `ballast.eval.run_cli` prerequisite baseline refresh may append exactly one ordinary existing-schema history entry so the default freshness gate can evaluate this code branch; it does not authorize a second paid run or any exposure-data integration. Never read owner or personal data.
- Follow strict TDD: add each behavior test, run it and observe the expected failure, implement only enough to pass, then run the focused suite again.

---

### Task 1: DX-8 portable backlog repository routing

**Files:**

- Modify: `specs/_shared/tooling/backlog.py`
- Create: `tests/test_backlog_tool.py`
- Modify after green: `specs/BACKLOG.md`

**Interfaces:**

- Consumes: `SITE_ROOT = Path(__file__).resolve().parents[3]`.
- Produces: `repo_path(repo: str) -> str`; `render()` and the `repo-path` CLI use this one resolver.

- [ ] **Step 1: Write the failing resolver tests**

Load the script through `importlib.util.spec_from_file_location` because the
vendored `specs/_shared/tooling` directories are not Python packages. Add
direct behavior tests that name the broken mapping:

```python
import importlib.util
from pathlib import Path


TOOL_PATH = Path(__file__).parents[1] / "specs" / "_shared" / "tooling" / "backlog.py"


def _load_backlog(path: Path = TOOL_PATH):
    spec = importlib.util.spec_from_file_location("ballast_backlog_under_test", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_repo_path_ballast_is_repository_root() -> None:
    backlog = _load_backlog()
    expected = Path(backlog.__file__).resolve().parents[3]
    assert Path(backlog.repo_path("ballast")) == expected


def test_repo_path_specs_is_repository_specs_directory() -> None:
    backlog = _load_backlog()
    expected = Path(backlog.__file__).resolve().parents[3] / "specs"
    assert Path(backlog.repo_path("specs")) == expected


def test_repo_path_unknown_stays_empty() -> None:
    backlog = _load_backlog()
    assert backlog.repo_path("not-a-repo") == ""
```

Add a temporary-layout test that loads a copied module from
`<tmp>/specs/_shared/tooling/backlog.py` and asserts the same two paths. It
catches any future return to a machine-specific literal.

- [ ] **Step 2: Run the focused test and observe RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_backlog_tool.py -q
```

Expected: failure because `repo_path` does not exist or `ballast` resolves to
the nonexistent nested `<repo>/ballast` directory.

- [ ] **Step 3: Implement the single resolver**

Use one helper for the CLI and renderer:

```python
REPO_PATHS = {
    "specs": str(SITE_ROOT / "specs"),
    "ballast": str(SITE_ROOT),
}


def repo_path(repo: str) -> str:
    return REPO_PATHS.get(repo, "")
```

Replace direct `REPO_PATHS.get(...)` calls in `render()` and the `repo-path`
command with `repo_path(...)`. Do not change any other backlog behavior.

- [ ] **Step 4: Run GREEN and exercise both CLI paths**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_backlog_tool.py -q
.\.venv\Scripts\python.exe specs\_shared\tooling\backlog.py repo-path ballast
.\.venv\Scripts\python.exe specs\_shared\tooling\backlog.py repo-path specs
```

Expected: tests pass; the first CLI prints the worktree root and the second
prints its `specs` child.

- [ ] **Step 5: Close DX-8 and commit**

Change only DX-8 to `status: done`, `pr: local`, and record the focused test in
its one-line note. Stage exact paths and commit:

```powershell
git add -- specs/_shared/tooling/backlog.py tests/test_backlog_tool.py specs/BACKLOG.md
git commit -m "fix: make backlog repository routing portable"
```

### Task 2: Pure exposure metrics and canonical hashes

**Files:**

- Create: `src/ballast/eval/metrics/exposure.py`
- Create: `tests/test_retrieval_exposure.py`

**Interfaces:**

- Consumes: `ballast.core.types.Chunk` and `ballast.eval.schema.GoldenRecord`.
- Produces:
  - `canonical_jsonl_sha256(rows: Sequence[Mapping[str, object]]) -> str`
  - `corpus_sha256(chunks: Sequence[Chunk]) -> str`
  - `golden_sha256(records: Sequence[GoldenRecord]) -> str`
  - `shannon_entropy_bits(shares: Mapping[str, float]) -> float`
  - `jensen_shannon_divergence_bits(expected: Mapping[str, float], observed: Mapping[str, float]) -> float`
  - `build_exposure_metrics(corpus_sources: Sequence[str], retrieved_sources: Sequence[str]) -> dict[str, object]`

- [ ] **Step 1: Write failing hand-derived information-theory tests**

Use literals rather than the production functions to derive expectations:

```python
def test_identical_distributions_have_zero_jsd() -> None:
    assert jensen_shannon_divergence_bits(
        {"a": 0.5, "b": 0.5}, {"a": 0.5, "b": 0.5}
    ) == pytest.approx(0.0)


def test_disjoint_singletons_have_one_bit_jsd() -> None:
    assert jensen_shannon_divergence_bits({"a": 1.0}, {"b": 1.0}) == pytest.approx(1.0)


def test_two_equal_sources_have_two_effective_sources() -> None:
    report = build_exposure_metrics(["a", "b"], ["a", "b"])
    assert report["corpus_entropy_bits"] == pytest.approx(1.0)
    assert report["corpus_effective_sources"] == pytest.approx(2.0)
```

Also pin: distributions sum to one; effective values stay between one and the
union source count; duplicate retrieved IDs count as separate slots; per-source
rows are sorted and contain expected/observed share plus delta.

- [ ] **Step 2: Run the metric tests and observe RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_retrieval_exposure.py -q -k "jsd or entropy or slot or distribution"
```

Expected: import failure because `exposure.py` is absent.

- [ ] **Step 3: Implement minimal finite metric functions**

Use `math.log2`, never NumPy scalars:

```python
def shannon_entropy_bits(shares: Mapping[str, float]) -> float:
    return -sum(p * math.log2(p) for p in shares.values() if p > 0.0)


def jensen_shannon_divergence_bits(expected, observed):
    keys = sorted(set(expected) | set(observed))
    midpoint = {key: (expected.get(key, 0.0) + observed.get(key, 0.0)) / 2.0 for key in keys}
    return 0.5 * _kl_bits(expected, midpoint) + 0.5 * _kl_bits(observed, midpoint)
```

Build shares from integer counts, report actual slot count, and calculate
effective sources with `2.0 ** entropy_bits`.

- [ ] **Step 4: Add failing tri-state tests**

```python
@pytest.mark.parametrize(
    ("corpus", "retrieved", "reason"),
    [
        ([""], ["a"], "blank_corpus_source"),
        (["a"], [""], "blank_retrieved_source"),
        (["a"], [], "zero_retrieved_slots"),
    ],
)
def test_non_estimable_inputs_are_explicit(corpus, retrieved, reason) -> None:
    report = build_exposure_metrics(corpus, retrieved)
    assert report["status"] == "not_estimable"
    assert report["reason"] == reason
    assert "jensen_shannon_divergence_bits" not in report
```

Run the parametrized test and observe failure before adding the validation
branches.

- [ ] **Step 5: Implement tri-state branches and rerun GREEN**

Return JSON-compatible dictionaries only. Do not drop or rename a blank source
silently. Run all pure metric tests and confirm they pass.

- [ ] **Step 6: Write failing canonical-hash tests**

Construct parsed-equivalent rows with different key order/JSON whitespace and
CRLF/LF source text, plus semantically changed and reordered records. Assert:

```python
assert golden_sha256(records_a) == golden_sha256(records_equivalent)
assert golden_sha256(records_a) != golden_sha256(records_reordered)
assert corpus_sha256(chunks_a) != corpus_sha256(chunks_with_changed_text)
```

Pin corpus sorting by `chunk_id`, exact six hash fields, compact sorted keys,
UTF-8, and one LF terminator per row.

- [ ] **Step 7: Implement canonical hashing and rerun the complete focused file**

Use:

```python
encoded = "".join(
    json.dumps(row, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False) + "\n"
    for row in rows
).encode("utf-8")
return hashlib.sha256(encoded).hexdigest()
```

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_retrieval_exposure.py -q
```

- [ ] **Step 8: Commit the pure metric unit**

```powershell
git add -- src/ballast/eval/metrics/exposure.py tests/test_retrieval_exposure.py
git commit -m "feat: add retrieval exposure metrics"
```

### Task 3: Deterministic standalone retrieval exposure CLI

**Files:**

- Create: `scripts/retrieval_exposure.py`
- Modify: `tests/test_retrieval_exposure.py`

**Interfaces:**

- Consumes: `load_golden`, `chunk_corpus`, `HashingEmbedder`, `InMemoryVectorStore`, `Retriever`, and Task 2 metrics/hashes.
- Produces:
  - `collect_retrieved_sources(records: Sequence[GoldenRecord], retriever: Retriever) -> list[str]`
  - `run_exposure(corpus_dir: Path, golden_path: Path) -> dict[str, object]`
  - CLI `--corpus`, `--golden`, and required `--output`.

- [ ] **Step 1: Write the failing real-component integration test**

Build four small real `Chunk` values, index them with the real
`HashingEmbedder(dim=4096)` and `InMemoryVectorStore`, and delegate through a
recording wrapper around the real `Retriever`. Use two real `GoldenRecord`
questions. Assert calls are exactly:

```python
assert recording.calls == [(records[0].question, 4), (records[1].question, 4)]
assert len(retrieved_sources) == 8
```

This catches query transforms, retries, wrong ordering, and deduplication of
top-k slots without mocking retrieval behavior.

- [ ] **Step 2: Run the integration test and observe RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_retrieval_exposure.py -q -k "calls_direct_retriever_once"
```

Expected: import failure because the standalone collector is absent.

- [ ] **Step 3: Implement the direct collector and fixed profile wiring**

The only retrieval loop is:

```python
for record in records:
    hits = retriever.retrieve(record.question, k=4)
    retrieved_sources.extend(hit.chunk.source.strip() for hit in hits)
```

`run_exposure` must instantiate exactly:

```python
chunks = chunk_corpus(corpus_dir, max_tokens=256, overlap_tokens=40)
embedder = HashingEmbedder(dim=4096)
store = InMemoryVectorStore()
store.upsert((chunk, embedder.embed(chunk.text)) for chunk in chunks)
retriever = Retriever(store=store, embedder=embedder)
```

The payload has the single top-level key `retrieval_exposure`; its nested block
includes profile/config, hashes, query count, actual slot count, exclusions,
status/reason, metrics, and sorted per-source values.

- [ ] **Step 4: Rerun the integration test and observe GREEN**

Run the same focused test, then the whole `tests/test_retrieval_exposure.py`.

- [ ] **Step 5: Write failing CLI strictness tests**

Run the script in a subprocess against a tiny temp corpus and golden file.
Assert that:

- `--output` is required;
- the file parses with `json.loads` and has exactly one top-level key;
- serialized output contains no `NaN` or `Infinity`;
- a valid `not_estimable` artifact exits zero;
- an injected invalid corpus path writes a `failed` artifact and exits one;
- stdout is empty and diagnostics go to stderr only.

In the same RED step, create a temp `eval/history.jsonl`, record its bytes and
`gate.main()` return code, run the missing CLI artifact writer beside it, and
assert the history bytes, parsed entries, and gate exit code stay identical.
This test fails before the CLI writer exists and catches any later attempt to
append the exposure block to history or nest it under existing `metrics`.

- [ ] **Step 6: Implement minimal CLI I/O and rerun GREEN**

Use `json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False) + "\n"` and `Path.write_text(..., encoding="utf-8", newline="\n")`. Catch execution exceptions only at the CLI boundary and record their exception class plus a sanitized reason; do not conceal programming errors inside metric functions.

- [ ] **Step 7: Commit the standalone CLI**

```powershell
git add -- scripts/retrieval_exposure.py tests/test_retrieval_exposure.py
git commit -m "feat: add deterministic retrieval exposure report"
```

### Task 4: Full verification and local-lane closeout

**Files:**

- Modify after all gates: `specs/BACKLOG.md`

**Interfaces:**

- Consumes: Task 3 standalone artifact.
- Produces: fresh whole-repository proof that the standalone exposure artifact leaves existing result readers and `ballast.eval.gate` behavior unchanged. Apart from the one owner-authorized ordinary baseline entry described above, `eval/history.jsonl` remains unchanged and contains no retrieval-exposure payload.

- [ ] **Step 1: Run focused and repository-wide gates**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_backlog_tool.py tests/test_retrieval_exposure.py -q
.\.venv\Scripts\python.exe -m ballast.eval.gate
.\.venv\Scripts\python.exe scripts\local_ci.py
git diff --check 5191980013c1a6fec299b93ae34dead844101583..HEAD
```

Expected: focused tests pass; gate exit remains green; local CI passes secret
scan, dependency audit, ruff, mypy, full pytest, and eval gate.

- [ ] **Step 2: Run one deterministic production-corpus report**

Write to an ignored or temporary path, not eval history:

```powershell
$artifact = Join-Path $env:TEMP "ballast-retrieval-exposure.json"
.\.venv\Scripts\python.exe scripts\retrieval_exposure.py --corpus corpus --golden eval\golden.jsonl --output $artifact
Get-Content -Raw -LiteralPath $artifact | .\.venv\Scripts\python.exe -m json.tool
```

Record only status, query count, slot count, hashes, and metric bounds in the
implementation report. Do not make an answer-quality or model-bias claim.

- [ ] **Step 3: Close EVAL-24 and commit exact paths**

Set EVAL-24 to `status: done`, `pr: local`, and add a one-line note with the
commit and gate evidence. Then:

```powershell
git add -- specs/BACKLOG.md
git commit -m "backlog: close retrieval exposure diagnostic"
```

- [ ] **Step 4: Final branch review**

Generate the SDD review package from base `5191980013c1a6fec299b93ae34dead844101583`
to HEAD. Require task-level spec and quality approval, then a whole-branch
review. The final review must confirm no diff in production RAG, existing eval
runner/gate code, dependency manifests, or corpus content; the only history diff
must be the one owner-authorized ordinary baseline entry, with no
`retrieval_exposure` field.
