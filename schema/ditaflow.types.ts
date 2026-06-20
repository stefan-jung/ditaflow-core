/**
 * DitaFlow (.dtf) — Formal Type System
 * Version: 1.0.0
 *
 * DitaFlow is the canonical JSON representation of the DITA Information Model.
 * Every valid DTF document can be losslessly converted to DITA XML 1.3 or 2.0,
 * and every valid DITA XML document can be imported to DTF without data loss.
 *
 * Design invariants:
 *  1. Every DITA element maps to exactly one DTF node type.
 *  2. Every DITA attribute is preserved in the `attrs` object.
 *  3. Unknown attributes survive round-trips via `attrs._ext`.
 *  4. Specialization is tracked via `classChain` — the full DITA class string.
 *  5. Branch Filtering and Keyscopes are first-class fields, never derived.
 *  6. Processing Instructions and XML comments are preserved as typed nodes.
 */

// ---------------------------------------------------------------------------
// 1. Document envelope
// ---------------------------------------------------------------------------

/** Top-level DitaFlow document. Wraps either a Topic or a Map. */
export interface DtfDocument {
  /** Format identifier — always "ditaflow" */
  dtf: "ditaflow";

  /** Format version — semver */
  dtfVersion: "1.0.0";

  /** DITA specification version this document targets */
  ditaVersion: "1.3" | "2.0";

  /**
   * Document type: "topic" family or "map" family.
   * Mirrors the DITA root element name.
   * Examples: "topic", "concept", "task", "reference",
   *           "map", "bookmap", "subjectScheme", "classifyMap",
   *           "learningMap", "learningBookmap"
   */
  doctype: string;

  /**
   * Full DITA class chain for the root element.
   * Mirrors the DITA `class` attribute exactly.
   * Example for a task: ["- topic/topic task/task "]
   * Example for bookmap: ["- map/map bookmap/bookmap "]
   */
  classChain: string[];

  /**
   * Nearest standard DITA base type.
   * One of: "topic" | "map"
   */
  baseDoctype: "topic" | "map";

  /** Optional XML processing instructions from the original file */
  processingInstructions?: DtfProcessingInstruction[];

  /** The root content node (a Topic or Map node) */
  root: DtfTopicNode | DtfMapNode;

  /** Document-level metadata not captured in the root node */
  meta?: DtfDocumentMeta;
}

export interface DtfDocumentMeta {
  /** Original file path or URI, if imported from DITA XML */
  sourceUri?: string;

  /** SHA-256 of the original DITA XML source, for round-trip verification */
  sourceHash?: string;

  /** Timestamp of last import from DITA XML */
  importedAt?: string;

  /** DTD or RNG schema the original document declared */
  originalDoctype?: string;

  /** Any DOCTYPE declaration attributes (PUBLIC, SYSTEM identifiers) */
  doctypeDecl?: {
    name: string;
    publicId?: string;
    systemId?: string;
  };
}

// ---------------------------------------------------------------------------
// 2. Shared node primitives
// ---------------------------------------------------------------------------

/**
 * Every DTF node — whether block, inline, or structural — carries these fields.
 * This mirrors how DITA's universal attributes apply to every element.
 */
export interface DtfBaseNode {
  /**
   * The DITA element name (specialised or base).
   * Examples: "p", "section", "step", "cmd", "codeblock",
   *           "chapter", "topicref", "keydef"
   */
  type: string;

  /**
   * Full DITA class chain as array of strings.
   * Each entry is one level of the inheritance chain.
   * Example for <step>: ["- topic/li task/step "]
   * Example for <codeblock>: ["+ topic/pre pr-d/codeblock "]
   * Preserved exactly for lossless round-trip.
   */
  classChain: string[];

  /**
   * The nearest standard DITA base element type.
   * Enables processing code to treat specialisations generically.
   * Example: a specialised "apiOperation" → baseType "section"
   */
  baseType: string;

  /**
   * All DITA attributes on this element, exactly as they appear in DITA XML.
   * Universal attributes (id, outputclass, translate, xml:lang, dir,
   * importance, status, rev) plus element-specific attributes.
   */
  attrs: DtfAttrs;

  /** Child nodes. Always an array, even for elements with a single child. */
  content: DtfNode[];

  /** Preserved XML comments that appeared immediately before this element */
  precedingComments?: DtfComment[];
}

/**
 * DITA attributes bag.
 * All known DITA attributes are typed; unknown or extension attributes
 * land in `_ext` and are preserved transparently.
 */
export interface DtfAttrs {
  // Universal attributes (DITA 1.3 §2.3 / DITA 2.0 §3.2)
  id?: string;
  conref?: string;
  conrefend?: string;
  conaction?: "mark" | "pushbefore" | "pushafter" | "pushreplace" | "-dita-use-conref-target";
  conkeyref?: string;      // "keyname/elementid" format, per DITA spec
  keyref?: string;
  keys?: string;           // space-separated list
  outputclass?: string;
  translate?: "yes" | "no";
  "xml:lang"?: string;     // BCP-47 language tag
  dir?: "ltr" | "rtl" | "lro" | "rlo";
  importance?: "default" | "deprecated" | "optional" | "required" | "recommended";
  status?: "new" | "changed" | "deleted" | "unchanged";
  rev?: string;

  // Filtering attributes (profiling)
  audience?: string;       // space-separated list of values
  product?: string;
  platform?: string;
  props?: string;          // generalised conditional attribute
  otherprops?: string;

  // Linking attributes
  href?: string;
  format?: string;
  scope?: "local" | "peer" | "external";
  type?: string;           // link type hint

  // Topicref-specific
  navtitle?: string;
  locktitle?: "yes" | "no";
  toc?: "yes" | "no";
  print?: "yes" | "no" | "printonly";
  search?: "yes" | "no";
  chunk?: string;
  collection-type?: "unordered" | "sequence" | "choice" | "family";
  linking?: "none" | "normal" | "sourceonly" | "targetonly";
  keyscope?: string;       // space-separated list of scope names

  // Table attributes
  frame?: "all" | "bottom" | "none" | "sides" | "top" | "topbot";
  colsep?: "0" | "1";
  rowsep?: "0" | "1";
  rowheader?: "firstcol" | "norowheader";

  // Image/object attributes
  height?: string;
  width?: string;
  scale?: string;
  scalefit?: "yes" | "no";
  placement?: "break" | "inline";
  align?: "left" | "right" | "center" | "justify";

  // Note type
  note_type?: "note" | "tip" | "fastpath" | "restriction" | "important"
             | "remember" | "attention" | "caution" | "danger" | "warning"
             | "trouble" | "other";

  // Hazard statement
  hazard?: string;

  /**
   * Extension bucket: any attribute not recognised above is stored here.
   * Preserved verbatim for lossless round-trip.
   * Key: attribute name (including namespace prefix if present)
   * Value: attribute value as string
   */
  _ext?: Record<string, string>;
}

// ---------------------------------------------------------------------------
// 3. Node union type
// ---------------------------------------------------------------------------

export type DtfNode =
  | DtfTextNode
  | DtfElementNode
  | DtfConrefNode
  | DtfImageNode
  | DtfTableNode
  | DtfProcessingInstruction
  | DtfComment;

// ---------------------------------------------------------------------------
// 4. Leaf nodes
// ---------------------------------------------------------------------------

/** Plain text content. Corresponds to XML text nodes. */
export interface DtfTextNode {
  type: "text";
  text: string;
  /** Inline marks applied to this text span */
  marks?: DtfMark[];
}

/** An XML processing instruction, e.g. <?ish-replace-vars?> */
export interface DtfProcessingInstruction {
  type: "pi";
  target: string;  // e.g. "ish-replace-vars"
  data?: string;   // e.g. 'name="product"'
}

/** An XML comment, e.g. <!-- reviewer note --> */
export interface DtfComment {
  type: "comment";
  text: string;
}

// ---------------------------------------------------------------------------
// 5. Inline marks (flat, non-nestable formatting only)
// ---------------------------------------------------------------------------

/**
 * Marks apply to DtfTextNode spans.
 * Only structural formatting with no semantic children is modelled as a Mark.
 * Semantic inline elements (xref, keyword, ph, cite, term, etc.) are
 * DtfElementNodes with their own content array.
 */
export type DtfMark =
  | { type: "b" }                         // <b>
  | { type: "i" }                         // <i>
  | { type: "u" }                         // <u>
  | { type: "sup" }                       // <sup>
  | { type: "sub" }                       // <sub>
  | { type: "tt" }                        // <tt> (DITA 1.3)
  | { type: "line-through" }              // outputclass="line-through"
  | { type: "overline" }                  // outputclass="overline"
  | { type: "hi-d/b" }                    // highlight domain <b>
  | { type: "hi-d/i" }                    // highlight domain <i>
  | { type: "hi-d/line-through" }
  | { type: "hi-d/overline" }
  | { type: "hi-d/sup" }
  | { type: "hi-d/sub" }
  | { type: "hi-d/tt" }
  | { type: "hi-d/u" };

// ---------------------------------------------------------------------------
// 6. Generic element node (covers all DITA block + inline elements)
// ---------------------------------------------------------------------------

/**
 * The universal container for any DITA element not given a specialised
 * DTF interface below. Covers: p, section, div, dl, ol, ul, li, ph,
 * xref, keyword, term, cite, fn, indexterm, required-cleanup, etc.
 *
 * Processing code dispatches on `baseType` for generic handling,
 * and on `type` for specialisation-specific handling.
 */
export interface DtfElementNode extends DtfBaseNode {
  type: string;   // exact DITA element name
}

// ---------------------------------------------------------------------------
// 7. Conref node — explicit, not derived from attrs
// ---------------------------------------------------------------------------

/**
 * A content reference. Kept as an explicit node type rather than an
 * attribute on DtfElementNode so that editors can render it distinctly
 * and the resolver can find all conrefs with a single node-type filter.
 */
export interface DtfConrefNode {
  type: "conref";
  classChain: string[];
  baseType: string;   // base element type being referenced

  /** Direct URI conref: "path/to/file.dtf#topicid/elementid" */
  conref?: string;

  /** Key-based conref: "keyname/elementid" */
  conkeyref?: string;

  /** End of a conref range (conrefend target) */
  conrefend?: string;

  /** conaction for content push: pushbefore | pushafter | pushreplace | mark */
  conaction?: DtfAttrs["conaction"];

  attrs: DtfAttrs;

  /**
   * Resolved snapshot of the referenced content, if pre-resolved.
   * Null means unresolved (will be resolved at render/publish time).
   */
  resolved?: DtfNode[] | null;
}

// ---------------------------------------------------------------------------
// 8. Image node
// ---------------------------------------------------------------------------

export interface DtfImageNode {
  type: "image";
  classChain: string[];
  baseType: "image";
  attrs: DtfAttrs & {
    href?: string;
    keyref?: string;
    scope?: "local" | "peer" | "external";
    format?: string;
  };
  /** Alt text as a DTF content model (allows inline markup per DITA spec) */
  alt?: DtfNode[];
  /** Long description reference */
  longdescref?: { href?: string; keyref?: string; format?: string };
}

// ---------------------------------------------------------------------------
// 9. Table nodes (CALS and simple table)
// ---------------------------------------------------------------------------

export interface DtfTableNode {
  type: "table" | "simpletable";
  classChain: string[];
  baseType: "table" | "simpletable";
  attrs: DtfAttrs;
  title?: DtfNode[];
  desc?: DtfNode[];

  /** CALS table: tgroup elements */
  tgroups?: DtfTgroup[];

  /** Simple table: sthead + strows */
  sthead?: DtfStrow;
  strows?: DtfStrow[];
}

export interface DtfTgroup {
  type: "tgroup";
  classChain: string[];
  baseType: "tgroup";
  attrs: DtfAttrs & { cols: string };
  colspecs?: DtfColspec[];
  spanspecs?: DtfSpanspec[];
  thead?: DtfTableSection;
  tbody: DtfTableSection;
  tfoot?: DtfTableSection;
}

export interface DtfColspec {
  type: "colspec";
  classChain: string[];
  baseType: "colspec";
  attrs: DtfAttrs & {
    colname?: string;
    colnum?: string;
    colwidth?: string;
    align?: string;
    colsep?: "0" | "1";
    rowsep?: "0" | "1";
  };
  content: [];
}

export interface DtfSpanspec {
  type: "spanspec";
  classChain: string[];
  baseType: "spanspec";
  attrs: DtfAttrs & {
    spanname: string;
    namest: string;
    nameend: string;
  };
  content: [];
}

export interface DtfTableSection {
  type: "thead" | "tbody" | "tfoot";
  classChain: string[];
  baseType: "thead" | "tbody" | "tfoot";
  attrs: DtfAttrs;
  rows: DtfRow[];
}

export interface DtfRow {
  type: "row";
  classChain: string[];
  baseType: "row";
  attrs: DtfAttrs;
  entries: DtfEntry[];
}

export interface DtfEntry {
  type: "entry";
  classChain: string[];
  baseType: "entry";
  attrs: DtfAttrs & {
    colname?: string;
    namest?: string;
    nameend?: string;
    spanname?: string;
    morerows?: string;
    rotate?: "0" | "1";
  };
  content: DtfNode[];
}

export interface DtfStrow {
  type: "sthead" | "strow";
  classChain: string[];
  baseType: "sthead" | "strow";
  attrs: DtfAttrs;
  entries: DtfStentry[];
}

export interface DtfStentry {
  type: "stentry";
  classChain: string[];
  baseType: "stentry";
  attrs: DtfAttrs;
  content: DtfNode[];
}

// ---------------------------------------------------------------------------
// 10. Topic nodes
// ---------------------------------------------------------------------------

/**
 * Base topic. All specialised topics (concept, task, reference,
 * learningContent, troubleshooting, etc.) share this structure.
 * Specialised body types (taskbody, conbody, refbody) are captured
 * by the body node's own `type` and `classChain`.
 */
export interface DtfTopicNode extends DtfBaseNode {
  type: string;   // "topic" | "concept" | "task" | "reference" | specialisation
  baseType: "topic";

  /** Topic short description */
  shortdesc?: DtfElementNode;

  /** Abstract (alternative to shortdesc) */
  abstract?: DtfElementNode;

  /** Topic prologue (prolog element) */
  prolog?: DtfPrologNode;

  /** Main body — type varies with specialisation */
  body?: DtfElementNode;

  /** Related links section */
  related_links?: DtfElementNode;

  /** Nested topics */
  nested?: DtfTopicNode[];
}

export interface DtfPrologNode extends DtfBaseNode {
  type: "prolog";
  baseType: "prolog";
  author?: DtfElementNode[];
  source?: DtfElementNode;
  publisher?: DtfElementNode;
  copyright?: DtfElementNode[];
  critdates?: DtfCritdatesNode;
  permissions?: DtfElementNode;
  metadata?: DtfMetadataNode[];
  resourceid?: DtfElementNode[];
  data?: DtfElementNode[];
}

export interface DtfCritdatesNode extends DtfBaseNode {
  type: "critdates";
  baseType: "critdates";
  created?: { date: string; golive?: string; expiry?: string };
  revised?: Array<{ modified: string; golive?: string; expiry?: string }>;
}

export interface DtfMetadataNode extends DtfBaseNode {
  type: "metadata";
  baseType: "metadata";
}

// ---------------------------------------------------------------------------
// 11. Map nodes
// ---------------------------------------------------------------------------

export interface DtfMapNode extends DtfBaseNode {
  type: string;   // "map" | "bookmap" | specialisation
  baseType: "map";

  /** Map title (topictitle or title element) */
  title?: DtfNode[];

  /** Map-level topicmeta */
  topicmeta?: DtfTopicmetaNode;

  /** Key definitions at map scope */
  keydefs?: DtfKeydefNode[];

  /** Relationship tables */
  reltables?: DtfReltableNode[];

  /** The navigation tree */
  topicrefs: DtfTopicrefNode[];

  /**
   * Keyscope names declared on this map.
   * Space-separated in DITA; stored as array in DTF.
   */
  keyscope?: string[];
}

// ---------------------------------------------------------------------------
// 12. Topicref node — core of Map navigation trees
// ---------------------------------------------------------------------------

export interface DtfTopicrefNode extends DtfBaseNode {
  type: string;   // "topicref" | "chapter" | "appendix" | "part" | etc.
  baseType: "topicref";

  /** Resolved or relative URI to the target topic */
  href?: string;

  /** Key reference instead of href */
  keyref?: string;

  /** Keys defined by this topicref (for key-defining topicrefs) */
  keys?: string[];

  /**
   * Keyscope names for branch scoping.
   * Stored as array; serialised as space-separated string in DITA XML.
   */
  keyscope?: string[];

  /**
   * Fully-qualified keyscope path from the map root.
   * Computed at import/processing time, not stored in DITA XML.
   * Example: ["product-a", "product-a.release-1"]
   * Used by the Keyscope-Resolver for correct key lookup.
   */
  _keyscopePath?: string[];

  /** Topicmeta for this ref */
  topicmeta?: DtfTopicmetaNode;

  /**
   * Branch filtering: ditavalref elements that scope this branch.
   * Each entry is a reference to a DITAVAL profile that applies
   * to this topicref and all its descendants.
   */
  ditavalrefs?: DtfDitavalrefNode[];

  /** Child topicrefs (nested navigation) */
  children?: DtfTopicrefNode[];
}

// ---------------------------------------------------------------------------
// 13. Keydef node
// ---------------------------------------------------------------------------

export interface DtfKeydefNode extends DtfBaseNode {
  type: "keydef";
  baseType: "topicref";

  /** The key name(s) — space-separated in DITA; array in DTF */
  keys: string[];

  /** URI the key resolves to (may be absent for keyword-only keys) */
  href?: string;

  /** Keyscope this keydef belongs to */
  keyscope?: string[];

  /** Text-only key content (for <keyword> substitution) */
  topicmeta?: DtfTopicmetaNode;

  /**
   * Processing-only flag: if true, this keydef should not generate
   * navigation output (maps to processing-role="resource-only").
   */
  resourceOnly?: boolean;
}

// ---------------------------------------------------------------------------
// 14. Ditavalref node — Branch Filtering
// ---------------------------------------------------------------------------

/**
 * A reference to a DITAVAL filter file, scoped to a map branch.
 * In DITA 1.3+, ditavalref can appear as a child of topicref to
 * apply conditional filtering to that branch only.
 */
export interface DtfDitavalrefNode extends DtfBaseNode {
  type: "ditavalref";
  baseType: "ditavalref";

  /** URI to the DITAVAL file */
  href?: string;

  /** Key reference to a DITAVAL file */
  keyref?: string;

  /**
   * Inlined DITAVAL rules (alternative to href/keyref).
   * Allows filter rules to be stored directly in the DTF document
   * without a separate file reference.
   */
  inlinedDitaval?: DtfDitavalProfile;

  /** dvrResourcePrefix for branch copy naming */
  dvrResourcePrefix?: string;

  /** dvrResourceSuffix for branch copy naming */
  dvrResourceSuffix?: string;

  /** dvrKeyscopePrefix for branch keyscope naming */
  dvrKeyscopePrefix?: string;

  /** dvrKeyscopeSuffix for branch keyscope naming */
  dvrKeyscopeSuffix?: string;
}

// ---------------------------------------------------------------------------
// 15. DITAVAL profile (inline or referenced)
// ---------------------------------------------------------------------------

/**
 * Represents the content of a DITAVAL filter file.
 * Can be stored inline in a DtfDitavalrefNode or as a standalone document.
 */
export interface DtfDitavalProfile {
  /** Version for forward compatibility */
  version?: "1.0";

  /** Filter rules */
  props: DtfDitavalProp[];

  /** Default action when no rule matches */
  defaultAction?: "include" | "exclude" | "passthrough" | "flag";
}

export interface DtfDitavalProp {
  /** The conditional attribute being filtered (e.g. "audience", "product") */
  att: string;

  /** The specific value to match (absent means "match any value") */
  val?: string;

  /** Action to take when this rule matches */
  action: "include" | "exclude" | "passthrough" | "flag";

  /** Flagging options (only used when action = "flag") */
  flag?: {
    color?: string;
    backcolor?: string;
    style?: "underline" | "double-underline" | "italics" | "overline" | "bold";
    startflag?: { imageref?: string; alt?: string };
    endflag?: { imageref?: string; alt?: string };
  };
}

// ---------------------------------------------------------------------------
// 16. Relationship table
// ---------------------------------------------------------------------------

export interface DtfReltableNode extends DtfBaseNode {
  type: "reltable";
  baseType: "reltable";
  relheader?: DtfRelheaderNode;
  relrows: DtfRelrowNode[];
}

export interface DtfRelheaderNode extends DtfBaseNode {
  type: "relheader";
  baseType: "relheader";
  relcolspecs: DtfRelcolspecNode[];
}

export interface DtfRelcolspecNode extends DtfBaseNode {
  type: "relcolspec";
  baseType: "relcolspec";
}

export interface DtfRelrowNode extends DtfBaseNode {
  type: "relrow";
  baseType: "relrow";
  relcells: DtfRelcellNode[];
}

export interface DtfRelcellNode extends DtfBaseNode {
  type: "relcell";
  baseType: "relcell";
}

// ---------------------------------------------------------------------------
// 17. Topicmeta node
// ---------------------------------------------------------------------------

export interface DtfTopicmetaNode extends DtfBaseNode {
  type: "topicmeta";
  baseType: "topicmeta";
  navtitle?: DtfNode[];
  linktext?: DtfNode[];
  searchtitle?: DtfNode[];
  shortdesc?: DtfNode[];
  author?: DtfElementNode[];
  source?: DtfElementNode;
  publisher?: DtfElementNode;
  copyright?: DtfElementNode[];
  critdates?: DtfCritdatesNode;
  permissions?: DtfElementNode;
  audience?: DtfElementNode[];
  category?: DtfElementNode[];
  keywords?: DtfKeywordsNode;
  prodinfo?: DtfProdinfoNode[];
  othermeta?: DtfOthermetaNode[];
  resourceid?: DtfElementNode[];
  ux_window?: DtfElementNode[];
}

export interface DtfKeywordsNode extends DtfBaseNode {
  type: "keywords";
  baseType: "keywords";
  keywords: DtfNode[];
}

export interface DtfProdinfoNode extends DtfBaseNode {
  type: "prodinfo";
  baseType: "prodinfo";
  prodname?: DtfNode[];
  vrmlist?: DtfVrmlistNode;
  brand?: DtfNode[];
  series?: DtfNode[];
  platform?: DtfNode[];
  prognum?: DtfNode[];
  featnum?: DtfNode[];
  component?: DtfNode[];
}

export interface DtfVrmlistNode extends DtfBaseNode {
  type: "vrmlist";
  baseType: "vrmlist";
  vrm: Array<{ version?: string; release?: string; modification?: string }>;
}

export interface DtfOthermetaNode extends DtfBaseNode {
  type: "othermeta";
  baseType: "othermeta";
  attrs: DtfAttrs & { name: string; content: string };
}

// ---------------------------------------------------------------------------
// 18. Specialisation registry entry
// ---------------------------------------------------------------------------

/**
 * Describes a known DITA specialisation so the converter and
 * editor can handle it correctly without hardcoded knowledge.
 */
export interface DtfSpecialisationEntry {
  /** Specialised element name */
  elementName: string;

  /** The DITA class string for this element */
  ditaClass: string;

  /** Base element in the DITA standard this specialises */
  baseElement: string;

  /** Domain or topic type module defining this specialisation */
  module: string;

  /** Whether children are allowed (block content model) */
  allowsContent: boolean;

  /** Allowed child element names, if constrained */
  allowedChildren?: string[];

  /** Whether this element may appear inline */
  isInline: boolean;

  /** JSON Schema fragment for additional validation of attrs */
  attrsSchema?: Record<string, unknown>;
}

// ---------------------------------------------------------------------------
// 19. Converter result types
// ---------------------------------------------------------------------------

export interface DtfImportResult {
  document: DtfDocument;
  warnings: DtfConversionWarning[];
  /** true if the original DITA XML can be reconstructed byte-for-byte */
  isLossless: boolean;
}

export interface DtfExportResult {
  xml: string;
  warnings: DtfConversionWarning[];
}

export interface DtfConversionWarning {
  severity: "info" | "warning" | "error";
  code: string;
  message: string;
  /** DTF node path where the issue occurred, e.g. "root.body.content[2]" */
  nodePath?: string;
  /** Original DITA XPath where the issue occurred */
  ditaXPath?: string;
}

// ---------------------------------------------------------------------------
// 20. Round-trip verification
// ---------------------------------------------------------------------------

export interface DtfRoundTripReport {
  /** true if DITA → DTF → DITA produced identical output */
  passed: boolean;
  /** Diff entries describing any differences found */
  diffs: DtfRoundTripDiff[];
  /** Original DITA XML (normalised) */
  originalXml: string;
  /** Reconstructed DITA XML (normalised) */
  reconstructedXml: string;
}

export interface DtfRoundTripDiff {
  type: "missing_element" | "extra_element" | "attribute_mismatch"
      | "text_mismatch" | "order_mismatch" | "namespace_mismatch";
  xpath: string;
  expected?: string;
  actual?: string;
}
