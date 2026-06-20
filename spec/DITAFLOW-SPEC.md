# DitaFlow Format Specification

**Version:** 1.0.0
**Status:** Draft
**Dateiendung:** `.dtf` / `.dtf.json`
**Encoding:** UTF-8

---

## 1. Überblick

DitaFlow (`.dtf`) ist die kanonische JSON-Repräsentation des DITA-Informationsmodells. Das Format ermöglicht die vollständig verlustfreie, bidirektionale Konvertierung zwischen DITA XML (1.3 und 2.0) und einer editor- und datenbankfreundlichen JSON-Struktur.

### Designziele

| Ziel | Bedeutung |
|------|-----------|
| Semantische Äquivalenz | Jedes DITA-Element und -Attribut hat eine direkte DTF-Entsprechung |
| Verlustfreier Round-Trip | DITA → DTF → DITA produziert identisches XML |
| Spezialisierungsunterstützung | Spezialisierte Topics und Domains werden vollständig abgebildet |
| Branch Filtering | `ditavalref` und Keyscopes sind First-Class-Konzepte |
| Editor-Kompatibilität | DTF-Nodes entsprechen direkt ProseMirror/Tiptap-Nodes |
| DB-Nativität | Speicherbar als PostgreSQL JSONB ohne Transformation |

---

## 2. Dokumenthülle

Jede DTF-Datei ist ein JSON-Objekt mit folgenden Pflichtfeldern:

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

### Feldübersicht

| Feld | Typ | Pflicht | Beschreibung |
|------|-----|---------|--------------|
| `dtf` | `"ditaflow"` | ja | Format-Identifier |
| `dtfVersion` | `"1.0.0"` | ja | Format-Version |
| `ditaVersion` | `"1.3"` \| `"2.0"` | ja | Ziel-DITA-Version |
| `doctype` | string | ja | Wurzelelement-Name (z.B. `"task"`, `"bookmap"`) |
| `classChain` | string[] | ja | Vollständige DITA-class-Kette als Array |
| `baseDoctype` | `"topic"` \| `"map"` | ja | Dokumentfamilie |
| `root` | TopicNode \| MapNode | ja | Wurzelknoten |
| `processingInstructions` | PI[] | nein | Erhaltene XML-PIs |
| `meta` | DocumentMeta | nein | Import-Metadaten |

---

## 3. Das classChain-Prinzip

Das `classChain`-Feld ist das zentrale Mechanismus für verlustfreien Round-Trip bei Spezialisierungen.

### Hintergrund

In DITA XML trägt jedes Element ein `class`-Attribut, das die vollständige Vererbungskette kodiert:

```xml
<step class="- topic/li task/step ">
<codeblock class="+ topic/pre pr-d/codeblock ">
<apiOperation class="+ topic/section reference/section apiRef-d/apiOperation ">
```

### DTF-Repräsentation

DTF speichert diese Kette als Array, wobei jeder Eintrag genau einem Vererbungslevel entspricht:

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

### Regeln

1. `classChain` wird beim Import direkt aus dem DITA `class`-Attribut übernommen — keine Transformation.
2. `baseType` ist das letzte Basis-Element in der Kette (der generischste Typ).
3. Beim Export wird `classChain[0]` als `class`-Attribut rekonstruiert.
4. Unbekannte Spezialisierungen werden transparent durchgereicht.

---

## 4. Knotentypen

### 4.1 Textknoten

Der einfachste Knoten. Entspricht einem XML-Textknoten.

```json
{ "type": "text", "text": "Hallo Welt" }
```

Mit Marks (rein formatielle Inline-Auszeichnung):

```json
{
  "type": "text",
  "text": "wichtiger Begriff",
  "marks": [{ "type": "b" }, { "type": "i" }]
}
```

**Marks vs. Nodes:** Nur strukturell flache Formatierungsmarker werden als Marks modelliert (`b`, `i`, `u`, `sup`, `sub`, `tt`). Alle semantischen Inline-Elemente (`xref`, `keyword`, `ph`, `cite`, `term`, `fn`) werden als `DtfElementNode` mit eigenem `content`-Array modelliert. Dies löst das ProseMirror-Limitation, dass Marks nicht verschachtelt werden können.

### 4.2 Elementknoten

Der universelle Container für alle DITA-Elemente.

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
    { "type": "text", "text": "Diesen Schritt nicht überspringen." }
  ]
}
```

### 4.3 Conref-Knoten

Expliziter Knotentyp für Inhaltsreferenzen. Nicht als Attribut auf einem Elementknoten — als eigener Typ, damit Editoren und Resolver sie direkt filtern können.

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

Für key-basierte Conrefs:

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

Das Feld `resolved` enthält nach der Auflösung die kopierten Knoten, bleibt `null` bis zur Auflösung.

### 4.4 Bild-Knoten

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
    { "type": "text", "text": "Screenshot des Installationsassistenten" }
  ]
}
```

### 4.5 Processing Instructions und Kommentare

```json
{ "type": "pi", "target": "ish-replace-vars", "data": "name=\"product\"" }
{ "type": "comment", "text": " Reviewer: Diese Warnung prüfen " }
```

---

## 5. Topic-Struktur

Ein Task-Topic in DTF:

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
      "xml:lang": "de-DE",
      "audience": "admin",
      "product": "Server"
    },
    "content": [],
    "shortdesc": {
      "type": "shortdesc",
      "classChain": ["- topic/shortdesc task/shortdesc "],
      "baseType": "shortdesc",
      "attrs": {},
      "content": [
        { "type": "text", "text": "Konfigurieren Sie die Installation für Ihre Umgebung." }
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
                    { "type": "text", "text": "Verzeichnis anlegen." }
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

## 6. Map-Struktur mit Branch Filtering und Keyscopes

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
    "attrs": { "id": "product-manual", "xml:lang": "de-DE" },
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

### Keyscope-Auflösungsregeln

1. `_keyscopePath` ist ein berechnetes Feld, das beim Import/Prozessieren gesetzt wird.
2. Jeder Keyscope-Name wird mit dem Eltern-Scope durch `.` verbunden: `"manual.server-edition"`.
3. Die Key-Auflösung sucht vom engsten zum weitesten Scope (lokaler Scope zuerst, dann Eltern-Scopes).
4. `_keyscopePath` wird beim DTF→DITA Export **nicht** serialisiert (ist ein Prozessierungs-Artefakt).

---

## 7. attrs._ext — Transparente Erweiterungsattribute

Jedes unbekannte Attribut, das beim DITA-Import angetroffen wird, landet in `attrs._ext`:

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

Diese Attribute werden beim Export unverändert auf das XML-Element geschrieben. Kein Datenverlust, auch bei proprietären CMS-Erweiterungen (Ixiasoft, SDL Tridion, etc.).

---

## 8. Spezialisierungs-Plugin-Interface

Neue Spezialisierungen werden über eine Registry registriert:

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

Der Konverter und Editor nutzen die Registry für:
- Korrekte `classChain`-Generierung beim Import
- Validierung spezialisierungs-spezifischer Attribute
- Editor-Toolbar: welche Elemente sind in welchem Kontext erlaubt

---

## 9. Round-Trip-Garantien

### Was verlustfrei ist

| Element | Garantie |
|---------|----------|
| Alle DITA-Elemente | ✓ vollständig |
| Alle DITA-Attribute | ✓ vollständig |
| Unbekannte Attribute (`_ext`) | ✓ vollständig |
| Spezialisierungen (via `classChain`) | ✓ vollständig |
| Processing Instructions | ✓ vollständig |
| XML-Kommentare | ✓ vollständig |
| Branch Filtering (`ditavalref`) | ✓ vollständig |
| Keyscopes | ✓ vollständig |
| CALS-Tabellen inkl. `colspec`/`spanspec` | ✓ vollständig |
| Mixed Content (Text + Inline gemischt) | ✓ vollständig |

### Was nicht Round-Trip-fähig ist (by design)

| Element | Begründung |
|---------|------------|
| XML-Namespacedeklarationen auf Nicht-Wurzelelementen | Selten, nicht DITA-konform |
| Whitespace zwischen Attributen | Semantisch irrelevant |
| Reihenfolge von Attributen | XML-Standard: attribut-Reihenfolge ist bedeutungslos |
| BOM (Byte Order Mark) | Normalisiert zu UTF-8 ohne BOM |

---

## 10. Versionierung

DitaFlow-Dokumente sind vorwärtskompatibel:
- `dtfVersion` wird bei Breaking Changes inkrementiert.
- Unbekannte Felder werden ignoriert (nicht verworfen).
- Der Konverter schreibt immer die aktuelle Version.
- Ältere Dokumente können mit einem Migrations-Script aktualisiert werden.

---

## 11. Dateikonventionen

| Konvention | Regel |
|------------|-------|
| Dateiendung | `.dtf` (bevorzugt) oder `.dtf.json` |
| Encoding | UTF-8, kein BOM |
| Zeilenende | LF (`\n`) |
| Einrückung (gespeichert) | Minifiziert (kein Whitespace) |
| Einrückung (Debug/Export) | 2 Spaces |
| Dateiname | entspricht dem `id`-Attribut des Wurzel-Topics/Maps |

---

*DitaFlow Specification — © 2025 — Version 1.0.0 Draft*
