# DitaFlow Format Specification

**Version:** 1.0.0
**Status:** Draft
**File extension:** `.dtf` / `.dtf.json`
**Encoding:** UTF-8

---

## 1. Overview

DitaFlow (`.dtf`) is the canonical JSON representation of the DITA Information Model.
The format enables fully lossless, bidirectional conversion between DITA XML (1.3 and
2.0) and an editor- and database-friendly JSON structure.

### Design goals

| Goal | Meaning |
|------|---------|
| Semantic equivalence | Every DITA element and attribute has a direct DTF counterpart |
| Lossless round-trip | DITA → DTF → DITA produces a semantically identical document (see §9) |
| Specialization support | Specialized topics and domains are fully represented |
| Branch filtering | `ditavalref` and keyscopes are first-class concepts |
| Editor compatibility | DTF nodes map directly onto ProseMirror/Tiptap nodes |
| DB-native | Storable as PostgreSQL JSONB without transformation |

### Coverage philosophy: structural, not enumerative

DitaFlow does not aim for "100% DITA compatibility" by hand-modeling every element in
every DITA domain. Instead, three primitives give full coverage by construction:

1. **`classChain`** is copied verbatim from the source `class` attribute on import and
   written back verbatim on export. Any specialization — known to the converter or
   not — survives the round trip because the converter never needs to *recompute* it.
2. **`attrs._ext`** captures any attribute not individually typed in `DtfAttrs` —
   including standard DITA attributes that simply haven't been given their own field
   (e.g. `domains`, `spectitle`, `keycol`, module-specific attributes), not just
   attributes that are unknown to DITA. See §7.
3. **The generic element node** (`type` / `classChain` / `baseType` / `attrs` /
   `content`) represents any element that doesn't require a non-uniform child shape.

Only structurally distinctive constructs get a bespoke node shape: the topic envelope,
the map envelope, topicref trees, tables (CALS and simple), images, conref/conkeyref,
keydef, and ditavalref. Everything else — including specializations the converter has
no specific knowledge of, and DITA 2.0 additions not yet individually modeled — falls
through to the generic node and round-trips correctly. Extending coverage of a new
domain is additive (a registry entry, see §8), not an architectural change.

---

## 2. Document envelope

Every DTF file is a JSON object with the following required fields:

```json
{
  "dtf": "ditaflow",
  "dtfVersion": "1.0.0",
  "ditaVersion": "1.3",
  "doctype": "task",
  "classChain": ["- topic/topic task/task "],
  "baseDoctype": "topic",
  "root": { ... }
}
```

### Field reference

| Field | Type | Required | Description |
|------|-----|---------|--------------|
| `dtf` | `"ditaflow"` | yes | Format identifier |
| `dtfVersion` | `"1.0.0"` | yes | Format version |
| `ditaVersion` | `"1.3"` \| `"2.0"` | yes | Target DITA specification version |
| `doctype` | string | yes | Root element name (e.g. `"task"`, `"bookmap"`) |
| `classChain` | string[] | yes | Full DITA class chain for the root element |
| `baseDoctype` | `"topic"` \| `"map"` | yes | Document family |
| `root` | TopicNode \| MapNode | yes | Root node |
| `processingInstructions` | PI[] | no | Preserved XML PIs |
| `meta` | DocumentMeta | no | Import metadata |

### Version awareness

`ditaVersion` selects which element/attribute tables the specialization registry and
validator apply (DITA 2.0 changes some defaults and adds/removes a small number of
elements relative to 1.3). This is a **data-table difference, not a structural one** —
the node model (`classChain` / `attrs` / `_ext`) is identical across versions, so a
converter upgrade to support a new DITA 2.0 element is a registry addition, not a
schema change.

---

## 3. The classChain principle

The `classChain` field is the central mechanism for lossless round-tripping of
specializations.

### Background

In DITA XML, every element carries a `class` attribute encoding its full inheritance
chain:

```xml
<step class="- topic/li task/step ">
<codeblock class="+ topic/pre pr-d/codeblock ">
<apiOperation class="+ topic/section reference/section apiRef-d/apiOperation ">
```

### DTF representation

DTF stores this chain as an array, where each entry corresponds to one level of
inheritance:

```json
{
  "type": "step",
  "classChain": ["- topic/li task/step "],
  "baseType": "li"
}
```

```json
{
  "type": "apiOperation",
  "classChain": ["+ topic/section reference/section apiRef-d/apiOperation "],
  "baseType": "section"
}
```

### Rules

1. `classChain` is copied directly from the DITA `class` attribute on import — no
   transformation, no recomputation from a registry lookup.
2. `baseType` is the last base element in the chain (the most generic type).
3. On export, `classChain[0]` is written back as the `class` attribute verbatim.
4. Unknown specializations are passed through transparently — the converter does not
   need a registry entry for an element to round-trip it correctly (see §1).

---

## 4. Node types

### 4.1 Text nodes

The simplest node. Corresponds to an XML text node.

```json
{ "type": "text", "text": "Hello world" }
```

With marks (purely formatting inline markup):

```json
{
  "type": "text",
  "text": "important term",
  "marks": [{ "type": "b" }, { "type": "i" }]
}
```

**Marks vs. nodes — collapsing rule.** Only `b`, `i`, `u`, `sup`, `sub`, `tt` are
*candidates* for representation as marks. An element collapses into a mark **only if
its entire content is text (optionally already carrying other marks) with no element
children** — e.g. `<b>important</b>` becomes a marked text node. If such an element
contains any child element — e.g. `<b><xref href="..."/></b>` — marks cannot represent
it (a mark cannot carry non-text content), so it is kept as a generic `DtfElementNode`
with its own `content` array instead. This same rule is why all other semantic inline
elements (`xref`, `keyword`, `ph`, `cite`, `term`, `fn`) are *always* modeled as
`DtfElementNode`, never as marks: they are commonly nested and ProseMirror marks cannot
nest.

### 4.2 Element nodes

The universal container for all DITA elements.

```json
{
  "type": "note",
  "classChain": ["- topic/note "],
  "baseType": "note",
  "attrs": {
    "note_type": "caution",
    "audience": "admin"
  },
  "content": [
    { "type": "text", "text": "Do not skip this step." }
  ]
}
```

### 4.3 Conref nodes

An explicit node type for content references — not an attribute on a generic element
node, but its own type, so editors and resolvers can filter for them directly.

```json
{
  "type": "conref",
  "classChain": ["- topic/p "],
  "baseType": "p",
  "conref": "../shared/warnings.dtf#common-warnings/no-root-note",
  "attrs": {},
  "resolved": null
}
```

For key-based conrefs:

```json
{
  "type": "conref",
  "classChain": ["- topic/li "],
  "baseType": "li",
  "conkeyref": "shared-content/warranty-note",
  "attrs": {},
  "resolved": null
}
```

The `resolved` field holds the copied nodes once resolved; it stays `null` until
resolution happens.

### 4.4 Image nodes

```json
{
  "type": "image",
  "classChain": ["- topic/image "],
  "baseType": "image",
  "attrs": {
    "href": "../images/install-step1.png",
    "format": "png",
    "placement": "break",
    "width": "600px"
  },
  "alt": [
    { "type": "text", "text": "Screenshot of the installation wizard" }
  ]
}
```

### 4.5 Processing instructions and comments

```json
{ "type": "pi", "target": "ish-replace-vars", "data": "name=\"product\"" }
{ "type": "comment", "text": " Reviewer: verify this warning " }
```

---

## 5. Topic structure

A task topic in DTF. Note the required `title` field — every DITA topic requires a
`<title>` as its first child, so `title` is mandatory on every topic node (unlike the
map's `title`, which DITA itself treats as optional):

```json
{
  "dtf": "ditaflow",
  "dtfVersion": "1.0.0",
  "ditaVersion": "1.3",
  "doctype": "task",
  "classChain": ["- topic/topic task/task "],
  "baseDoctype": "topic",
  "root": {
    "type": "task",
    "classChain": ["- topic/topic task/task "],
    "baseType": "topic",
    "attrs": {
      "id": "install-configure",
      "xml:lang": "en-US",
      "audience": "admin",
      "product": "Server"
    },
    "content": [],
    "title": {
      "type": "title",
      "classChain": ["- topic/title "],
      "baseType": "title",
      "attrs": {},
      "content": [
        { "type": "text", "text": "Configure the installation" }
      ]
    },
    "shortdesc": {
      "type": "shortdesc",
      "classChain": ["- topic/shortdesc task/shortdesc "],
      "baseType": "shortdesc",
      "attrs": {},
      "content": [
        { "type": "text", "text": "Configure the installation for your environment." }
      ]
    },
    "body": {
      "type": "taskbody",
      "classChain": ["- topic/body task/taskbody "],
      "baseType": "body",
      "attrs": {},
      "content": [
        {
          "type": "prereq",
          "classChain": ["- topic/section task/prereq "],
          "baseType": "section",
          "attrs": {},
          "content": [ { "type": "text", "text": "..." } ]
        },
        {
          "type": "steps",
          "classChain": ["- topic/ol task/steps "],
          "baseType": "ol",
          "attrs": {},
          "content": [
            {
              "type": "step",
              "classChain": ["- topic/li task/step "],
              "baseType": "li",
              "attrs": { "importance": "required" },
              "content": [
                {
                  "type": "cmd",
                  "classChain": ["- topic/ph task/cmd "],
                  "baseType": "ph",
                  "attrs": {},
                  "content": [
                    { "type": "text", "text": "Create the directory." }
                  ]
                }
              ]
            }
          ]
        }
      ]
    }
  }
}
```

---

## 6. Map structure with branch filtering and keyscopes

```json
{
  "dtf": "ditaflow",
  "dtfVersion": "1.0.0",
  "ditaVersion": "1.3",
  "doctype": "bookmap",
  "classChain": ["- map/map bookmap/bookmap "],
  "baseDoctype": "map",
  "root": {
    "type": "bookmap",
    "classChain": ["- map/map bookmap/bookmap "],
    "baseType": "map",
    "attrs": { "id": "product-manual", "xml:lang": "en-US" },
    "content": [],
    "keyscope": ["manual"],
    "topicrefs": [
      {
        "type": "chapter",
        "classChain": ["- map/topicref bookmap/chapter "],
        "baseType": "topicref",
        "attrs": {},
        "content": [],
        "href": "topics/installation.dtf",
        "keyscope": ["server-edition"],
        "_keyscopePath": ["manual", "manual.server-edition"],
        "ditavalrefs": [
          {
            "type": "ditavalref",
            "classChain": ["- map/topicref ditavalref-d/ditavalref "],
            "baseType": "ditavalref",
            "attrs": {},
            "content": [],
            "inlinedDitaval": {
              "version": "1.0",
              "props": [
                { "att": "product", "val": "Server", "action": "include" },
                { "att": "product", "action": "exclude" }
              ],
              "defaultAction": "include"
            },
            "dvrKeyscopePrefix": "server-"
          }
        ],
        "children": [
          {
            "type": "topicref",
            "classChain": ["- map/topicref "],
            "baseType": "topicref",
            "attrs": {},
            "content": [],
            "href": "topics/install-configure.dtf",
            "keyscope": [],
            "_keyscopePath": ["manual", "manual.server-edition"]
          }
        ]
      }
    ]
  }
}
```

### Keyscope resolution rules

1. `_keyscopePath` is a computed field set during import/processing.
2. Each keyscope name is joined to its parent scope with `.`: `"manual.server-edition"`.
3. Key resolution searches from the narrowest to the widest scope (local scope first,
   then parent scopes).
4. `_keyscopePath` is **not** serialized on DTF→DITA export — it is a processing
   artifact, not part of the DITA data model.

---

## 7. attrs._ext — transparent extension attributes

`attrs._ext` is the catch-all for **any attribute not present as a typed field in
`DtfAttrs`** — this includes attributes that are unknown to DITA *and* standard DITA
attributes that simply haven't been given an individual typed field (e.g. `domains` on
a map root, `spectitle`, `keycol`, module-specific attributes from a domain the
converter hasn't special-cased). This distinction matters: `_ext` is not an error
bucket for malformed input, it is the primary mechanism by which DitaFlow achieves full
DITA coverage without enumerating every attribute of every domain (see §1).

```json
{
  "attrs": {
    "id": "my-topic",
    "_ext": {
      "ish:ishref": "GUID-1234",
      "custom:priority": "high",
      "data-cms-id": "abc123"
    }
  }
}
```

These attributes are written back unchanged onto the XML element on export. No data is
lost, even for proprietary CMS extensions (Ixiasoft, SDL Tridion, etc.) or DITA
attributes the converter has not individually modeled yet.

---

## 8. Specialization plugin interface

New specializations are registered via a registry:

```typescript
const registry = new DtfSpecialisationRegistry();

registry.register({
  elementName: "apiOperation",
  ditaClass: "+ topic/section reference/section apiRef-d/apiOperation ",
  baseElement: "section",
  module: "apiRef-d",
  allowsContent: true,
  isInline: false,
  attrsSchema: {
    "api-type": { type: "string", enum: ["rest", "soap", "graphql"] }
  }
});
```

The converter and editor use the registry for:
- Attribute validation specific to a specialization
- Editor toolbar: which elements are allowed in which context

The registry is **not** required for correct round-tripping. An unregistered
specialization still imports and exports correctly via `classChain` (§3) and `_ext`
(§7) — registering it only adds validation and editor affordances, per §1.

---

## 9. Round-trip guarantees

DitaFlow's round-trip guarantee is **semantic identity**, not byte-for-byte identity.
DITA → DTF → DITA must produce a document that is structurally and semantically
identical to, and processed identically by any standard DITA tool as, the original —
but is not guaranteed to be byte-identical to the original file.

### Canonical comparison rules

The reference comparison between an original and a reconstructed document is:

| Aspect | Rule |
|--------|------|
| Element tree | Identical element names and identical nesting/order |
| Attributes | Identical attribute names and values; attribute **order** is not compared |
| Text content | Identical, character for character, for every text node |
| Inter-element whitespace | Whitespace that occurs only between elements in an element-only content model (e.g. between `<li>` siblings of `<ol>`) is **not** preserved — it is insignificant per the DITA content model and is normalized to a consistent pretty-printed form on export |
| Whitespace inside text-bearing content | Preserved exactly, because it lives inside a text node (e.g. inside `<p>`, `<codeblock>`, `<pre>`) and is therefore part of the document's semantic content |
| Attribute whitespace | Whitespace between attributes inside a start tag is not compared (semantically irrelevant) |
| BOM | Normalized to UTF-8 without BOM |

### What is lossless

| Element | Guarantee |
|---------|-----------|
| All DITA elements | ✓ fully |
| All DITA attributes | ✓ fully |
| Unknown/unmodeled attributes (`_ext`) | ✓ fully |
| Specializations (via `classChain`), registered or not | ✓ fully |
| Processing instructions | ✓ fully |
| XML comments | ✓ fully |
| Branch filtering (`ditavalref`) | ✓ fully |
| Keyscopes | ✓ fully |
| CALS tables incl. `colspec`/`spanspec` | ✓ fully |
| Mixed content (text and inline markup interleaved) | ✓ fully |

### What is not round-trip-preserved (by design)

| Aspect | Rationale |
|--------|-----------|
| Original pretty-printing / inter-element whitespace | Insignificant per the DITA content model; see comparison rules above |
| XML namespace declarations on non-root elements | Rare, not idiomatic DITA |
| Attribute order | XML standard: attribute order carries no meaning |
| BOM (Byte Order Mark) | Normalized to UTF-8 without BOM |

---

## 10. Versioning

DitaFlow documents are forward-compatible:
- `dtfVersion` is incremented on breaking changes.
- Unknown fields are ignored (not discarded — i.e. round-tripped through a generic
  store if encountered inside a node's `_ext`/`content`, dropped only at the document
  envelope level if truly unrecognized).
- The converter always writes the current version.
- Older documents can be brought up to date with a migration script.

---

## 11. File conventions

| Convention | Rule |
|------------|------|
| File extension | `.dtf` (preferred) or `.dtf.json` |
| Encoding | UTF-8, no BOM |
| Line ending | LF (`\n`) |
| Indentation (stored) | Minified (no whitespace) |
| Indentation (debug/export) | 2 spaces |
| File name | Matches the `id` attribute of the root topic/map |

---

*DitaFlow Specification — © 2025 — Version 1.0.0 Draft*
