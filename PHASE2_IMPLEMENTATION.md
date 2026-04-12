# Phase 2 Implementation -- Semantic Labels and Relationships

> **Status**: Redesigned (documentation)
> **Prerequisite**: Phase 1 must be complete (all nodes exist with `CodeNode` label, `kind`, `detail`, and CONTAINS edges written to Neo4j).
> **Core rule**: Phase 2 does NOT create new nodes. It only adds labels, properties, and relationships to existing nodes.

---

## Design Principles

1. **No new nodes.** Phase 2 operates exclusively on the node set created by Phase 1.
2. **Tiered processing.** Labels and relationships are classified into three tiers by how they are identified. Tiers are processed in order with explicit write points between them.
3. **Use Neo4j strengths.** Rather than caching the full graph in Python dicts/lists, run read queries against Neo4j to fetch the context needed for each tier. Write results back after each independent batch.
4. **Transactional memcache.** Every write batch is recorded in a write-ahead log. On failure, the entire Phase 2 transaction is reversed using compensating queries.
5. **Strategy Pattern with Common Rule Registry.** Base logic lives in one file. Language-specific rules live in per-language strategy files. Common rules handle ~70% of labels (kind-based mapping); languages extend with regex patterns.
6. **Parallelism where safe.** Tier 1 and Tier 3 use multi-threaded processing internally. Tier 2 is strictly sequential (DAG-ordered).

---

## Tier System Overview

| Tier | Identification Method | Graph Dependencies | Parallelism | Write Point |
|------|----------------------|--------------------|-------------|-------------|
| Tier 1 | Node `kind` property + source regex | None (reads only node's own props + source) | Parallel (multi-threaded) | After all Tier 1 labels + relationships computed |
| Tier 3 | LSP protocol requests | None (independent of graph labels/edges) | Parallel (multi-threaded) | After all Tier 3 labels + relationships computed |
| Tier 2 | Neo4j read queries on existing graph | Depends on Tier 1 and/or Tier 3 results | Sequential (DAG-ordered) | After each DAG step |

**Execution order:** Tier 1 first, then Tier 3, then Tier 2.
Tier 1 and Tier 3 are data-independent but run sequentially (Tier 1 before Tier 3)
because Tier 1 is fast (regex, no LSP) and its results make Tier 3 more efficient.
Within each tier, files/nodes are processed in parallel threads.

---

## Tier 1 -- Regex / Kind-Based

### Labels Assigned

For each node, read the `kind`, `detail`, `name`, `signature`, and `language` properties
(already stored in Phase 1). Read the source text from storage for regex matching.

**Kind-based label mapping (common to all languages):**

| kind | LSP SymbolKind | Labels Added            |
|------|----------------|-------------------------|
| 2    | Module         | Module                  |
| 5    | Class          | Class                   |
| 6    | Method         | CodeUnit, Method        |
| 7    | Property       | Attribute               |
| 8    | Field          | Attribute               |
| 9    | Constructor    | Instantiator, Constructor |
| 10   | Enum           | Enum                    |
| 11   | Interface      | Interface               |
| 12   | Function       | CodeUnit, Function      |
| 13   | Variable       | Attribute               |
| 14   | Constant       | Attribute               |
| 22   | EnumMember     | Attribute               |
| 23   | Struct         | Class                   |
| 24   | Event          | Event                   |
| 25   | Operator       | CodeUnit, Method        |

**Regex-based labels (language-specific strategy provides patterns):**

| Label                     | Regex Target                          | Source Context Needed  |
|---------------------------|---------------------------------------|-----------------------|
| Destructor                | name: `^~\w+` (C++) or `__del__` (Python) | Node name only    |
| Lambda                    | detail/name: `lambda`, `=>`, `[]() {` | Node detail + source  |
| Abstract                  | `abstract` (Java/TS), `= 0`/`virtual` (C++), `ABC`/`@abstractmethod` (Python) | Source declaration line |
| Internal                  | Default on all nodes (no regex)       | None                  |
| Testing                   | See language-specific patterns below  | Annotations + name    |
| Accept_call_over_network  | See language-specific patterns below  | Annotations + imports |
| Sends_data_over_network   | See language-specific patterns below  | Body + imports        |
| Database                  | See language-specific patterns below  | Annotations + imports |
| InterProcess Communication | See language-specific patterns below | Body + imports        |
| Thread Communication      | See language-specific patterns below  | Body + imports        |
| Forks Threads / Process   | See language-specific patterns below  | Body + imports        |
| Thread                    | See language-specific patterns below  | Class hierarchy + body |

**Language-specific additive labels:**

| Label          | Condition                   | Language  |
|----------------|-----------------------------|-----------|
| JavaClass      | kind == 5 + language "java" | Java only |
| JavaInterface  | kind == 11 + language "java"| Java only |
| JavaEnum       | kind == 10 + language "java"| Java only |

### Properties Set by Tier 1

Extracted from source code via regex on the declaration lines:

| Property         | How Extracted                                          | Example                              |
|------------------|--------------------------------------------------------|--------------------------------------|
| level            | Derived from primary label (see level table in Nodes.txt) | Class -> 2, Method -> 3          |
| return_type      | Regex on declaration: return type token                | `public String getName()` -> "String"|
| parameter_types  | Regex on declaration: parameter type list              | `(int x, String y)` -> ["int","String"] |
| access_modifier  | Regex: `public`/`private`/`protected`/`internal`       | "public"                             |
| modifiers        | Regex: `abstract`, `static`, `final`, `virtual`, `synchronized`, `native`, `volatile` | ["public","static","final"] |
| annotations      | Regex: `@AnnotationName` (Java/Python), `[[attr]]` (C++) | ["@Override","@Test"]             |
| is_static        | Regex: `static` keyword in declaration                 | true / false                         |

### Relationships Built by Tier 1

**INHERITS** and **IMPLEMENTS** are extracted by regex on source declaration lines.
The regex finds the superclass/interface names, then resolves them to existing nodes
by querying Neo4j: `MATCH (n:CodeNode {codebase_id: $cid, name: $target_name}) WHERE n.kind IN [5,11]`.

If multiple nodes match the same name (ambiguous), emit edges to all matches and log a warning.
If no node matches, log a debug message (target may be external; External label handles this in Tier 2).

---

## Tier 3 -- LSP-Based

Tier 3 runs after Tier 1 is written to the graph. It uses LSP protocol requests
that are independent of the semantic labels assigned in Tier 1.

### Labels Assigned

**Object / Instance** (Java and C++ only; NOT Python):

For each node with `kind` in (7, 8, 13, 22) whose CONTAINS parent has `kind == 5`
(class-like), use LSP to determine the field's declared type:

1. `textDocument/hover` at the field's position -> parse type from hover text
2. If hover is insufficient: `textDocument/typeDefinition` at the field's position -> URI stem as type name
3. If the resolved type is a reference type (non-primitive), add labels `Object` and `Instance`
4. Set property `reference_type_detail` to the resolved type string

Primitive type exclusion lists are language-specific:
- Java: `boolean`, `byte`, `char`, `short`, `int`, `long`, `float`, `double`, `void`
- C++: `bool`, `char`, `int`, `short`, `long`, `float`, `double`, `void`, `size_t`, `auto` (when resolves to primitive)

### Properties Set by Tier 3

| Property              | LSP Method                | Description                        |
|-----------------------|---------------------------|------------------------------------|
| reference_type_detail | hover + typeDefinition    | Declared type string for fields    |
| definition_uri        | textDocument/definition   | URI where the symbol is defined    |

### Relationships Built by Tier 3

**CALLS** -- via call hierarchy:

For each node labeled CodeUnit, Function, Method, Lambda, Constructor (kind in 6,9,12):
1. `textDocument/prepareCallHierarchy` at the node's position
2. `callHierarchy/outgoingCalls` on the result
3. For each outgoing call target: resolve URI + line to a node via Neo4j query:
   `MATCH (n:CodeNode {codebase_id: $cid, path: $norm_path}) WHERE n.start_line <= $line AND n.end_line >= $line`
4. Deduplicate (from_id, to_id) pairs; emit CALLS edge

**SETS / GETS** -- via document highlights:

For each node with kind in (7, 8, 13, 14, 22) (Attribute-like):
1. `textDocument/documentHighlight` at the attribute's position
2. For each highlight:
   - kind == 3 (Write) -> find enclosing callable by line range -> SETS edge
   - kind == 2 (Read) -> find enclosing callable by line range -> GETS edge
3. Enclosing callable found via Neo4j query:
   `MATCH (n:CodeNode {codebase_id: $cid, path: $path}) WHERE n.kind IN [6,9,12] AND n.start_line <= $line AND n.end_line >= $line ORDER BY (n.end_line - n.start_line) ASC LIMIT 1`

---

## Tier 2 -- Graph-Dependent (Sequential, DAG-Ordered)

Tier 2 runs after both Tier 1 and Tier 3 are written to Neo4j.
Each step reads from the graph, computes labels/edges, writes back, then proceeds.
This tier is NOT parallelized -- steps execute sequentially in DAG order.

### Step 2a: InnerClass + INSTANTIATES

These two are independent of each other but both depend only on Tier 1 + Phase 1.
They can be computed in the same step and written together.

**InnerClass label:**

```cypher
MATCH (parent:Class)-[:CONTAINS]->(child:Class)
WHERE child.codebase_id = $cid
RETURN child.id
```

For each returned child node, add label `InnerClass`.

**INSTANTIATES relationship:**

```cypher
MATCH (parent:Class)-[:CONTAINS]->(ctor:Constructor)
WHERE ctor.codebase_id = $cid
RETURN ctor.id AS from_id, parent.id AS to_id
```

For each pair, create edge `(ctor)-[:INSTANTIATES]->(parent_class)`.

### Step 2b: OVERRIDES + BELONGS_TO

These depend on INHERITS (Tier 1) and Object (Tier 3) respectively.

**OVERRIDES relationship:**

```cypher
MATCH (childClass)-[:INHERITS]->(parentClass)-[:CONTAINS]->(parentMethod:Method)
WHERE childClass.codebase_id = $cid
WITH childClass, parentMethod
MATCH (childClass)-[:CONTAINS]->(childMethod:Method)
WHERE childMethod.name = parentMethod.name
RETURN childMethod.id AS from_id, parentMethod.id AS to_id
```

Refinements for overload detection:
- Compare `parameter_types` lists (if both are populated) for exact match
- Compare `return_type` for covariant return compatibility
- Check `access_modifier`: override must have same or weaker access restriction
- Skip if parent method has `static` in modifiers (static methods are not overridden)

**BELONGS_TO relationship:**

```cypher
MATCH (obj:Object)
WHERE obj.codebase_id = $cid AND obj.reference_type_detail IS NOT NULL
RETURN obj.id, obj.reference_type_detail
```

For each Object node, extract the simple type name from `reference_type_detail`
(strip generics, arrays, qualifiers), then resolve to a Class node:

```cypher
MATCH (cls:Class {codebase_id: $cid, name: $simple_type_name})
RETURN cls.id
```

If multiple matches: emit edges to all and log warning.
If no match: the type may be external; log debug.

### Step 2c: External + SPAWNS

**External label:**

For each node that has `definition_uri` set (from Tier 3):
- Parse the URI to a file path
- If the path is outside the codebase root directory: add label `External`, remove label `Internal`
- If the path is inside the codebase root: node keeps `Internal` (already set in Tier 1)

```cypher
MATCH (n:CodeNode {codebase_id: $cid})
WHERE n.definition_uri IS NOT NULL
RETURN n.id, n.definition_uri
```

Application logic determines inside/outside by comparing the resolved path
against the codebase root path.

For nodes whose CALLS targets have no matching node in the graph (orphan targets),
those targets represent external calls. If a stub node exists, add External.

**SPAWNS relationship:**

For each node with label `ForksThreadsProcess`:
1. Read the node's source body
2. Regex-extract the thread/process creation pattern:
   - Java: `new Thread(target)`, `executor.submit(callable)`, `new ForkJoinTask()`
   - C++: `std::thread(func)`, `pthread_create(&tid, NULL, func, NULL)`
   - Python: `threading.Thread(target=func)`, `multiprocessing.Process(target=func)`
3. Resolve the target function/class name to a node via Neo4j:
   `MATCH (n:CodeNode {codebase_id: $cid, name: $target_name}) WHERE n.kind IN [5,6,12]`
4. Create `(spawner)-[:SPAWNS]->(target)` edge with properties `line` and `kind` ("thread"/"process")

---

## Tier 2 DAG Summary

```
Phase 1 complete (nodes + CONTAINS in Neo4j)
    |
    v
Tier 1 (parallel) --> write to Neo4j
    |
    v
Tier 3 (parallel) --> write to Neo4j
    |
    v
Step 2a: InnerClass + INSTANTIATES --> write to Neo4j
    |
    v
Step 2b: OVERRIDES + BELONGS_TO --> write to Neo4j
    |
    v
Step 2c: External + SPAWNS --> write to Neo4j
    |
    v
Phase 2 complete
```

---

## Design Pattern: Strategy with Common Rule Registry

### Why Strategy over Decorator

- Languages share most kind-based label mapping (~70% of labels are common across all languages)
- Language-specific logic adds rules rather than wrapping/modifying base logic
- Adding a new language requires one new file, no changes to base or other languages
- Clear rule precedence: common rules run first, language-specific rules extend

### Architecture

```
services/ingestion-worker/src/crawl/
    phase2_base.py              # Pipeline orchestrator: tier execution, write coordination, memcache
    phase2_rules.py             # Rule dataclasses (LabelRule, RelationshipRule) and RuleRegistry

services/ingestion-worker/src/crawl/strategies/
    __init__.py                 # Strategy registry: get_strategy(language)
    common.py                   # Shared rules: kind->label mapping, level assignment
    java.py                     # Java: extends/implements regex, @Test, @RequestMapping, etc.
    cpp.py                      # C++: virtual/=0, destructor ~, gtest macros, socket, etc.
    python.py                   # Python: class(Base), @abstractmethod, pytest, flask, etc.
    js_ts.py                    # JS/TS: extends, arrow functions, jest, express, etc.
```

### Rule Dataclasses

```python
@dataclass
class LabelRule:
    label: str                          # Label to add (e.g. "Abstract")
    tier: int                           # 1, 2, or 3
    kind_filter: set[int] | None        # LSP SymbolKind values this rule applies to (None = all)
    regex_pattern: str | None           # Regex applied to source/detail/name
    regex_target: str                   # "source", "detail", "name", "annotations"
    languages: set[str] | None          # None = all languages
    depends_on: list[str]               # Labels/edges that must exist before this rule runs

@dataclass
class RelationshipRule:
    rel_type: str                       # e.g. "INHERITS", "CALLS"
    tier: int                           # 1, 2, or 3
    from_kind_filter: set[int] | None   # Source node kinds
    to_kind_filter: set[int] | None     # Target node kinds
    regex_pattern: str | None           # For Tier 1: regex on source
    lsp_method: str | None              # For Tier 3: LSP method name
    languages: set[str] | None          # None = all languages
    depends_on: list[str]               # Labels/edges that must exist before this rule runs
```

### Strategy Interface

```python
class LanguageStrategy(ABC):
    @abstractmethod
    def tier1_label_rules(self) -> list[LabelRule]: ...

    @abstractmethod
    def tier1_relationship_rules(self) -> list[RelationshipRule]: ...

    @abstractmethod
    def tier3_label_handlers(self) -> list[Callable]: ...

    @abstractmethod
    def tier3_relationship_handlers(self) -> list[Callable]: ...

    @abstractmethod
    def tier2_handlers(self) -> list[Callable]: ...
```

### Common Strategy (base for all languages)

`common.py` provides kind-based label mapping, level assignment, and Internal default.
All language strategies inherit from `CommonStrategy`:

```python
class CommonStrategy(LanguageStrategy):
    """Shared rules that work for all languages."""
    def tier1_label_rules(self):
        return [
            LabelRule("Class", 1, {5, 23}, None, "kind", None, []),
            LabelRule("Interface", 1, {11}, None, "kind", None, []),
            LabelRule("CodeUnit", 1, {6, 12}, None, "kind", None, []),
            LabelRule("Method", 1, {6}, None, "kind", None, []),
            LabelRule("Function", 1, {12}, None, "kind", None, []),
            LabelRule("Attribute", 1, {7, 8, 13, 14, 22}, None, "kind", None, []),
            LabelRule("Instantiator", 1, {9}, None, "kind", None, []),
            LabelRule("Constructor", 1, {9}, None, "kind", None, []),
            LabelRule("Enum", 1, {10}, None, "kind", None, []),
            LabelRule("Module", 1, {2}, None, "kind", None, []),
            LabelRule("Event", 1, {24}, None, "kind", None, []),
            LabelRule("Internal", 1, None, None, "kind", None, []),
        ]
    # ... tier1_relationship_rules, tier3 handlers, tier2 handlers
```

### Per-Language Strategy (example: Java)

```python
class JavaStrategy(CommonStrategy):
    """Java-specific rules on top of common base."""
    def tier1_label_rules(self):
        base = super().tier1_label_rules()
        return base + [
            LabelRule("JavaClass", 1, {5}, None, "kind", {"java"}, []),
            LabelRule("JavaInterface", 1, {11}, None, "kind", {"java"}, []),
            LabelRule("JavaEnum", 1, {10}, None, "kind", {"java"}, []),
            LabelRule("Abstract", 1, {5, 6}, r"\babstract\b", "source", {"java"}, []),
            LabelRule("Testing", 1, {5, 6}, r"@Test|@Before|@After|@BeforeEach|@AfterEach", "annotations", {"java"}, []),
            LabelRule("Accept_call_over_network", 1, {6}, r"@RequestMapping|@GetMapping|@PostMapping|@PutMapping|@DeleteMapping|@RestController", "annotations", {"java"}, []),
            # ... more Java-specific rules
        ]

    def tier1_relationship_rules(self):
        base = super().tier1_relationship_rules()
        return base + [
            RelationshipRule("INHERITS", 1, {5}, {5, 11}, r"class\s+\w+\s+extends\s+(\w+)", None, {"java"}, []),
            RelationshipRule("IMPLEMENTS", 1, {5}, {11}, r"implements\s+([\w,\s]+)", None, {"java"}, []),
        ]
```

---

## Language-Specific Classification

### Java

**Tier 1 labels:** Class, Interface, Enum, CodeUnit, Method, Function, Attribute, Constructor, Event, Lambda, Abstract, Testing (@Test, @Before, @After, @BeforeEach, @AfterEach), Internal, JavaClass, JavaInterface, JavaEnum, Accept_call_over_network (@RequestMapping, @GetMapping, @PostMapping, @PutMapping, @DeleteMapping), Sends_data_over_network (HttpURLConnection, RestTemplate, WebClient, OkHttpClient), Database (@Repository, @Query, JPA annotations, JDBC), Forks Threads/Process (new Thread(), ExecutorService.submit()), Thread (Runnable.run(), Callable.call())

**Tier 1 relationships:** INHERITS (extends), IMPLEMENTS (implements)

**Tier 3 labels:** Object/Instance (jdtls hover + typeDefinition for reference types)

**Tier 3 relationships:** CALLS (jdtls callHierarchy), SETS/GETS (jdtls documentHighlight)

**Tier 2:** InnerClass, INSTANTIATES, OVERRIDES, BELONGS_TO, External, SPAWNS

### C++

**Tier 1 labels:** Class, Interface (abstract class with pure virtual methods), Enum, CodeUnit, Method, Function, Attribute, Constructor, Destructor (~name), Event, Lambda ([](){}), Abstract (= 0, virtual), Testing (TEST(), TEST_F(), TEST_P(), EXPECT_*, ASSERT_*), Internal, InterProcess Communication (pipe, shm_open, mq_open), Thread Communication (std::mutex, std::condition_variable, sem_wait), Forks Threads/Process (std::thread, fork(), pthread_create)

**Tier 1 relationships:** INHERITS (: public/protected/private Base)

**Tier 3 labels:** Object/Instance (clangd hover for reference types)

**Tier 3 relationships:** CALLS, SETS, GETS

**Tier 2:** InnerClass, INSTANTIATES, OVERRIDES, BELONGS_TO, External, SPAWNS

### Python

**Tier 1 labels:** Class, Module, Enum, CodeUnit, Method, Function, Attribute, Constructor (__init__), Destructor (__del__), Lambda, Abstract (ABC, @abstractmethod), Testing (test_* function names, @pytest.mark.*, unittest.TestCase subclass), Internal, Accept_call_over_network (Flask @app.route, Django urlpatterns, FastAPI @router.get), Sends_data_over_network (requests.*, urllib.request, aiohttp.ClientSession), Database (SQLAlchemy, psycopg2, pymongo, redis), Forks Threads/Process (threading.Thread, multiprocessing.Process, os.fork)

**Tier 1 relationships:** INHERITS (class Foo(Bar) parenthesized base classes)

**Tier 3 labels:** (NO Object/Instance -- dynamic typing makes type labels unreliable)

**Tier 3 relationships:** CALLS, SETS, GETS

**Tier 2:** InnerClass, OVERRIDES, External, SPAWNS

### JavaScript / TypeScript

**Tier 1 labels:** Class, Interface (TS only), Module, Enum (TS only), CodeUnit, Method, Function, Attribute, Constructor, Lambda (arrow =>), Abstract (TS abstract keyword), Testing (describe, it, test, expect from Jest/Mocha/Vitest), Internal, Accept_call_over_network (Express app.get/post/put/delete, Fastify route), Sends_data_over_network (fetch, axios.*, XMLHttpRequest, node-fetch), Database (mongoose, knex, sequelize, prisma, TypeORM)

**Tier 1 relationships:** INHERITS (extends), IMPLEMENTS (TS implements)

**Tier 3 labels:** Object/Instance (TS only; tsserver provides type info)

**Tier 3 relationships:** CALLS, SETS, GETS

**Tier 2:** INSTANTIATES, OVERRIDES, BELONGS_TO, External, SPAWNS

---

## Transactional Memcache (Write-Ahead Log)

Every write to Neo4j during Phase 2 is recorded in an in-memory write-ahead log (WAL).
If any write batch fails, the entire Phase 2 transaction is rolled back using
compensating queries derived from the WAL.

### Data Structures

```python
@dataclass
class WriteBatch:
    batch_id: str                                       # Unique identifier for this batch
    tier: str                                           # "tier1", "tier3", "tier2a", "tier2b", "tier2c"
    labels_added: list[tuple[str, str]]                 # (node_id, label)
    labels_removed: list[tuple[str, str]]               # (node_id, label) -- for Internal->External swap
    properties_set: list[tuple[str, str, Any, Any]]     # (node_id, key, old_value, new_value)
    edges_created: list[tuple[str, str, str]]           # (from_id, to_id, rel_type)

class WriteAheadLog:
    batches: list[WriteBatch]                           # Append-only during Phase 2

    def record(self, batch: WriteBatch): ...
    def rollback_all(self, graph_writer: GraphWriter): ...
    def clear(self): ...
```

### Rollback Procedure

On failure at any write point, `rollback_all` iterates batches in reverse order:

```python
def rollback_all(self, graph_writer):
    for batch in reversed(self.batches):
        # Reverse label additions
        for node_id, label in batch.labels_added:
            graph_writer.remove_label(node_id, label)
            # Cypher: MATCH (n {id: $nid}) REMOVE n:Label

        # Reverse label removals (re-add removed labels)
        for node_id, label in batch.labels_removed:
            graph_writer.add_label(node_id, label)

        # Reverse property changes (restore old values)
        for node_id, key, old_value, new_value in batch.properties_set:
            graph_writer.set_property(node_id, key, old_value)
            # Cypher: MATCH (n {id: $nid}) SET n[$key] = $old_value

        # Reverse edge creations
        for from_id, to_id, rel_type in batch.edges_created:
            graph_writer.delete_edge(from_id, to_id, rel_type)
            # Cypher: MATCH (a {id: $fid})-[r:REL_TYPE]->(b {id: $tid}) DELETE r
```

### Write Points

| Write Point | What Is Written                              | WAL Batch ID |
|-------------|----------------------------------------------|--------------|
| After Tier 1 | All Tier 1 labels + properties + INHERITS/IMPLEMENTS | "tier1" |
| After Tier 3 | Object/Instance labels + reference_type_detail + definition_uri + CALLS/SETS/GETS | "tier3" |
| After Step 2a | InnerClass labels + INSTANTIATES edges      | "tier2a"     |
| After Step 2b | OVERRIDES + BELONGS_TO edges                | "tier2b"     |
| After Step 2c | External labels (+ Internal removal) + SPAWNS edges | "tier2c" |

---

## Graph Writer -- New Query Methods for Tier 2

These read-only methods are added to `graph_writer.py` to support Tier 2 processing.
All methods filter by `codebase_id` to ensure strict codebase isolation.

| Method                                      | Cypher Pattern                                                                                      | Returns           | Used By          |
|---------------------------------------------|-----------------------------------------------------------------------------------------------------|-------------------|------------------|
| `get_nodes_by_label(cid, label)`            | `MATCH (n:Label {codebase_id: $cid}) RETURN n`                                                      | list[dict]        | All Tier 2       |
| `get_node_by_id(nid)`                       | `MATCH (n {id: $nid}) RETURN n`                                                                     | dict or None      | All              |
| `get_contains_parent(nid)`                  | `MATCH (p)-[:CONTAINS]->(n {id: $nid}) RETURN p`                                                    | dict or None      | InnerClass, INSTANTIATES |
| `get_contains_children(nid)`                | `MATCH (n {id: $nid})-[:CONTAINS]->(c) RETURN c ORDER BY c.start_line`                              | list[dict]        | OVERRIDES        |
| `get_nodes_by_name_and_label(cid, name, label)` | `MATCH (n:Label {codebase_id: $cid, name: $name}) RETURN n`                                     | list[dict]        | BELONGS_TO, INHERITS resolution |
| `get_inherits_parents(class_id)`            | `MATCH (c {id: $cid})-[:INHERITS]->(p) RETURN p`                                                    | list[dict]        | OVERRIDES        |
| `get_methods_of_class(class_id)`            | `MATCH (c {id: $cid})-[:CONTAINS]->(m:Method) RETURN m`                                             | list[dict]        | OVERRIDES        |
| `get_class_hierarchy(cid)`                  | `MATCH (c:Class {codebase_id: $cid})-[:INHERITS*]->(p) RETURN c.id, p.id, p.name`                   | list[tuple]       | OVERRIDES (deep) |
| `get_nodes_by_kind_and_parent_kind(cid, kind, parent_kind)` | `MATCH (p {kind: $pk})-[:CONTAINS]->(n {codebase_id: $cid, kind: $k}) RETURN n, p.id AS parent_id` | list[dict] | Object/Instance |

### Write Methods (new for Phase 2)

| Method                                  | Cypher Pattern                                                              |
|-----------------------------------------|-----------------------------------------------------------------------------|
| `add_label(nid, label)`                 | `MATCH (n {id: $nid}) SET n:Label`                                          |
| `remove_label(nid, label)`              | `MATCH (n {id: $nid}) REMOVE n:Label`                                       |
| `set_property(nid, key, value)`         | `MATCH (n {id: $nid}) SET n[$key] = $value`                                 |
| `batch_add_labels(pairs)`               | `UNWIND $pairs AS p MATCH (n {id: p.id}) SET n:Label` (per-label batched)    |
| `batch_set_properties(updates)`         | `UNWIND $updates AS u MATCH (n {id: u.id}) SET n += u.props`                |
| `batch_create_edges(edges, rel_type)`   | `UNWIND $edges AS e MATCH (a {id: e.from}), (b {id: e.to}) MERGE (a)-[:TYPE]->(b)` |
| `delete_edge(from_id, to_id, rel_type)` | `MATCH (a {id: $fid})-[r:TYPE]->(b {id: $tid}) DELETE r`                    |

---

## Execution Flow (Complete)

```
Phase 1 (see PHASE1_IMPLEMENTATION.md):
  Multi-threaded file processing -> nodes (CodeNode + file-type labels) + CONTAINS
  Write to Neo4j

Phase 2:
  Load LanguageStrategy for the codebase language
  Initialize WriteAheadLog

  Tier 1 (multi-threaded, files in parallel):
    For each node: apply kind-based labels from strategy
    For each File-type node: read source, apply regex-based labels from strategy
    For each Class/Interface node: regex-extract INHERITS/IMPLEMENTS targets, resolve to nodes
    Extract properties: return_type, parameter_types, access_modifier, modifiers, annotations, is_static
    Set level from primary label
    -> Write all Tier 1 results to Neo4j (batch)
    -> Record in WAL as "tier1"

  Tier 3 (multi-threaded, nodes in parallel):
    For each Attribute-like node under Class parent (Java/C++ only):
      LSP hover + typeDefinition -> Object/Instance label + reference_type_detail
    For all nodes:
      LSP textDocument/definition -> definition_uri
    For each callable node:
      LSP callHierarchy -> CALLS edges
    For each Attribute node:
      LSP documentHighlight -> SETS/GETS edges
    -> Write all Tier 3 results to Neo4j (batch)
    -> Record in WAL as "tier3"

  Tier 2 (sequential):
    Step 2a:
      Query: Class nodes containing Class children -> add InnerClass label
      Query: Class nodes containing Constructor children -> INSTANTIATES edges
      -> Write to Neo4j
      -> Record in WAL as "tier2a"

    Step 2b:
      Query: INHERITS edges + Method nodes -> match by name/signature -> OVERRIDES edges
      Query: Object nodes + reference_type_detail -> resolve to Class -> BELONGS_TO edges
      -> Write to Neo4j
      -> Record in WAL as "tier2b"

    Step 2c:
      Query: nodes with definition_uri -> check inside/outside codebase -> External label
      Query: ForksThreadsProcess nodes -> resolve target -> SPAWNS edges
      -> Write to Neo4j
      -> Record in WAL as "tier2c"

  If any write fails:
    WAL.rollback_all() -> reverse all Phase 2 changes
    Re-raise error

  On success:
    WAL.clear()
    Phase 2 complete
```

---

## References

- Phase 1 design: `PHASE1_IMPLEMENTATION.md`
- Core system design: `core_system/Retrival_system_README.md`
- Node definitions: `core_system/documentation/Nodes.txt`
- Relationship definitions: `core_system/documentation/Relationships.txt`
- Repository structure: `repository_structure.md`
