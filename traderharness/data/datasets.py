"""Dataset management — download and manage HuggingFace datasets."""

from __future__ import annotations

from pathlib import Path

from traderharness.paths import datasets_dir

DATASETS_DIR = datasets_dir()


BUILTIN_DATASETS = {
    "a50-2023": {
        "description": "A-share Top50 daily bars 2023",
        "hf_repo": "HephaestLab/a50-2023",
    },
    "a50-2024": {
        "description": "A-share Top50 daily bars 2024",
        "hf_repo": "HephaestLab/a50-2024",
    },
    "test-fixture": {
        "description": "Small test dataset for CI/development",
        "hf_repo": None,
    },
}


def list_datasets() -> list[dict]:
    """List available datasets."""
    results = []
    for name, meta in BUILTIN_DATASETS.items():
        local_path = DATASETS_DIR / name
        results.append(
            {
                "name": name,
                "description": meta["description"],
                "downloaded": local_path.exists(),
            }
        )
    return results


def get_dataset_path(name: str) -> Path:
    """Get the local path for a dataset."""
    return DATASETS_DIR / name


def ensure_dataset(name: str) -> Path:
    """Ensure dataset is available locally. Downloads if needed."""
    path = get_dataset_path(name)
    if path.exists():
        return path
    meta = BUILTIN_DATASETS.get(name)
    if meta is None:
        raise ValueError(f"Unknown dataset: {name}")
    if meta["hf_repo"] is None:
        path.mkdir(parents=True, exist_ok=True)
        return path
    _download_hf_dataset(meta["hf_repo"], path)
    return path


def _download_hf_dataset(repo_id: str, target: Path) -> None:
    """Download dataset from HuggingFace Hub."""
    try:
        from huggingface_hub import snapshot_download

        snapshot_download(repo_id=repo_id, local_dir=str(target), repo_type="dataset")
    except ImportError:
        raise ImportError("huggingface_hub not installed. Run: pip install huggingface_hub")


def download_full(*, force: bool = False) -> Path:
    """Download and atomically install the canonical full-market dataset."""
    from traderharness.data.release import download_full_dataset
    from traderharness.paths import dataset_dir

    return download_full_dataset(dataset_dir(), force=force)
