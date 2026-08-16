"""Strict JSON parsing and Draft 2020-12 contract validation."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from importlib import resources
import json
import math
from pathlib import Path
from typing import Any, Iterable

from jsonschema import Draft202012Validator, FormatChecker


_SCHEMA_FILES = {
    "baseline": "baseline.schema.json",
    "manifest": "manifest.schema.json",
    "result": "result.schema.json",
    "stimulus_metadata": "stimulus-metadata.schema.json",
}


class ContractError(ValueError):
    """A strict JSON parse or schema-validation failure."""

    def __init__(self, message: str, *, document_path: str, schema_path: str) -> None:
        self.document_path = document_path
        self.schema_path = schema_path
        super().__init__(
            f"{message} [document_path={document_path}; schema_path={schema_path}]"
        )


@dataclass(frozen=True)
class LoadedContract:
    """Validated document plus the digest of its byte-identical input."""

    document: dict[str, Any]
    sha256: str
    raw: bytes = b""


def _json_pointer(parts: Iterable[object]) -> str:
    encoded = [str(part).replace("~", "~0").replace("/", "~1") for part in parts]
    return "/" + "/".join(encoded) if encoded else "/"


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ContractError(
                f"duplicate object key {key!r}",
                document_path="/",
                schema_path="<parse>",
            )
        result[key] = value
    return result


def _reject_non_finite_token(token: str) -> None:
    raise ContractError(
        f"non-finite JSON number token {token!r}",
        document_path="/",
        schema_path="<parse>",
    )


def _read_schema(contract: str) -> dict[str, Any]:
    try:
        filename = _SCHEMA_FILES[contract]
    except KeyError as error:
        raise ValueError(f"unknown contract {contract!r}") from error

    packaged = resources.files("avsys").joinpath("schemas", "v1", filename)
    if packaged.is_file():
        text = packaged.read_text(encoding="utf-8")
    else:
        source_schema = Path(__file__).resolve().parents[2] / "schemas" / "v1" / filename
        text = source_schema.read_text(encoding="utf-8")
    schema = json.loads(text)
    Draft202012Validator.check_schema(schema)
    return schema


def validate_document(document: dict[str, Any], *, contract: str) -> None:
    """Validate an already parsed document without coercing any value."""
    schema = _read_schema(contract)
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    errors = sorted(
        validator.iter_errors(document),
        key=lambda error: (list(error.absolute_path), list(error.absolute_schema_path)),
    )
    if errors:
        error = errors[0]
        raise ContractError(
            error.message,
            document_path=_json_pointer(error.absolute_path),
            schema_path=_json_pointer(error.absolute_schema_path),
        )


def load_contract_bytes(raw: bytes, *, contract: str) -> LoadedContract:
    """Parse strict UTF-8 JSON, validate it, and retain its exact-byte digest."""
    digest = hashlib.sha256(raw).hexdigest()
    try:
        text = raw.decode("utf-8", errors="strict")
    except UnicodeDecodeError as error:
        raise ContractError(
            f"document is not strict UTF-8: {error}",
            document_path="/",
            schema_path="<parse>",
        ) from error

    try:
        document = json.loads(
            text,
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_non_finite_token,
        )
    except ContractError:
        raise
    except json.JSONDecodeError as error:
        raise ContractError(
            f"invalid JSON at line {error.lineno}, column {error.colno}: {error.msg}",
            document_path="/",
            schema_path="<parse>",
        ) from error

    if not isinstance(document, dict):
        raise ContractError(
            "contract root must be an object",
            document_path="/",
            schema_path="/type",
        )
    validate_document(document, contract=contract)
    return LoadedContract(document=document, sha256=digest, raw=raw)


def load_contract(path: str | Path, *, contract: str) -> LoadedContract:
    """Load a contract from disk without normalizing its input bytes."""
    return load_contract_bytes(Path(path).read_bytes(), contract=contract)


def _assert_finite(value: Any, path: tuple[object, ...] = ()) -> None:
    if isinstance(value, float) and not math.isfinite(value):
        raise ContractError(
            "cannot serialize a non-finite number",
            document_path=_json_pointer(path),
            schema_path="<serialization>",
        )
    if isinstance(value, dict):
        for key, child in value.items():
            _assert_finite(child, (*path, key))
    elif isinstance(value, (list, tuple)):
        for index, child in enumerate(value):
            _assert_finite(child, (*path, index))


def dump_contract(document: dict[str, Any], *, contract: str) -> bytes:
    """Validate and serialize deterministically with standard JSON numbers only."""
    _assert_finite(document)
    validate_document(document, contract=contract)
    try:
        encoded = json.dumps(
            document,
            allow_nan=False,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    except (TypeError, ValueError) as error:
        raise ContractError(
            f"document is not JSON serializable: {error}",
            document_path="/",
            schema_path="<serialization>",
        ) from error
    return (encoded + "\n").encode("utf-8")
