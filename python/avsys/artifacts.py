"""Small deterministic stimulus artifact packages for M1."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .contracts import dump_contract, load_contract
from .stimuli import canonical_pcm_bytes, generate_stimulus


@dataclass(frozen=True)
class StimulusArtifactPackage:
    directory: Path
    manifest_path: Path
    metadata_path: Path
    pcm_path: Path
    manifest_sha256: str
    pcm_sha256: str


def write_stimulus_package(
    manifest_path: str | Path, output_directory: str | Path
) -> StimulusArtifactPackage:
    """Generate only beneath the caller-selected artifact directory."""
    source = Path(manifest_path)
    manifest_raw = source.read_bytes()
    loaded = load_contract(source, contract="manifest")
    generated = generate_stimulus(loaded)
    directory = Path(output_directory)
    directory.mkdir(parents=True, exist_ok=True)
    packaged_manifest = directory / "manifest.json"
    metadata_path = directory / "stimulus.metadata.json"
    pcm_path = directory / "stimulus.pcm.f32le"
    packaged_manifest.write_bytes(manifest_raw)
    metadata_path.write_bytes(
        dump_contract(generated.metadata.to_document(), contract="stimulus_metadata")
    )
    pcm_path.write_bytes(canonical_pcm_bytes(generated.pcm))
    return StimulusArtifactPackage(
        directory=directory,
        manifest_path=packaged_manifest,
        metadata_path=metadata_path,
        pcm_path=pcm_path,
        manifest_sha256=generated.metadata.manifest_sha256,
        pcm_sha256=generated.metadata.pcm_sha256,
    )


__all__ = ["StimulusArtifactPackage", "write_stimulus_package"]
