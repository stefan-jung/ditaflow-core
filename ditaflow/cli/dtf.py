"""`dtf` command-line interface: convert, validate, roundtrip."""

from __future__ import annotations

import json
from pathlib import Path

import click
from rich.console import Console

from ditaflow.converter.dita_parser import DitaParser
from ditaflow.converter.dita_serializer import DtfSerializer
from ditaflow.validator.dtf_validator import DtfValidator

console = Console()

DITA_EXTENSIONS = {".dita", ".ditamap", ".xml"}
DTF_EXTENSIONS = {".dtf", ".json"}


@click.group()
def cli() -> None:
    """DitaFlow (.dtf) converter CLI."""


@cli.command()
@click.argument("input_path", type=click.Path(exists=True, path_type=Path))
@click.option("--output", "-o", required=True, type=click.Path(path_type=Path))
def convert(input_path: Path, output: Path) -> None:
    """Convert DITA XML to .dtf, or .dtf back to DITA XML (direction inferred
    from the input file's extension)."""
    if input_path.suffix in DITA_EXTENSIONS:
        result = DitaParser().parse_file(input_path)
        document_json = json.dumps(result.document, indent=2, ensure_ascii=False)
        output.write_text(document_json, encoding="utf-8")
        for warning in result.warnings:
            console.print(f"[yellow]warning[/yellow] {warning.code}: {warning.message}")
        console.print(f"[green]Wrote[/green] {output}")
    elif input_path.suffix in DTF_EXTENSIONS:
        document = json.loads(input_path.read_text(encoding="utf-8"))
        export_result = DtfSerializer().serialize(document)
        output.write_text(export_result.xml, encoding="utf-8")
        console.print(f"[green]Wrote[/green] {output}")
    else:
        raise click.ClickException(f"Unrecognized input extension: {input_path.suffix}")


@cli.command()
@click.argument("dtf_path", type=click.Path(exists=True, path_type=Path))
def validate(dtf_path: Path) -> None:
    """Validate a .dtf document against the DitaFlow JSON Schema."""
    document = json.loads(dtf_path.read_text(encoding="utf-8"))
    errors = DtfValidator().validate(document)
    if not errors:
        console.print("[green]Valid[/green]")
        return
    for error in errors:
        console.print(f"[red]error[/red] {error}")
    raise click.exceptions.Exit(1)


@cli.command()
@click.argument("dita_path", type=click.Path(exists=True, path_type=Path))
def roundtrip(dita_path: Path) -> None:
    """Convert DITA -> DTF -> DITA and report whether the result is
    semantically identical to the original (per spec §9)."""
    parser = DitaParser()
    serializer = DtfSerializer()

    import_result = parser.parse_file(dita_path)
    export_result = serializer.serialize(import_result.document)
    reimport_result = parser.parse_string(export_result.xml, base_dir=dita_path.parent)

    original = dict(import_result.document)
    reconstructed = dict(reimport_result.document)
    original.pop("meta", None)
    reconstructed.pop("meta", None)

    if original == reconstructed:
        console.print("[green]PASS[/green] — semantically identical round trip")
    else:
        console.print("[red]FAIL[/red] — differences found after DITA -> DTF -> DITA -> DTF")
        console.print(export_result.xml)
        raise click.exceptions.Exit(1)


if __name__ == "__main__":
    cli()
