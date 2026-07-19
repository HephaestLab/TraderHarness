import hashlib
import json

import pandas as pd
import pytest

from traderharness.data.release import (
    DatasetIntegrityError,
    build_dataset_card,
    build_public_news,
    download_full_dataset,
    verify_manifest,
)


def test_dataset_card_is_discoverable_and_documents_derived_fields():
    card = build_dataset_card()

    assert "tags:" in card
    assert "- finance" in card
    assert "traderharness data download --full" in card
    assert "284,219,844" in card
    assert "entity-templated headlines" in card
    assert "Upstream data rights" in card


def test_public_news_keeps_templated_headline_but_never_full_content():
    source = pd.DataFrame(
        [
            {
                "id": 1,
                "title": "{{C600519}}发布业绩",
                "content": "这是不得公开分发的完整快讯正文。",
                "display_time": "2024-03-04 10:00:00",
                "level": "A",
            },
            {
                "id": 2,
                "title": "",
                "content": "另一条完整快讯正文。",
                "display_time": "2024-03-04 10:01:00",
                "level": "B",
            },
        ]
    )

    public = build_public_news(source)

    assert public.loc[0, "content"] == "{{C600519}}发布业绩"
    assert public.loc[1, "content"] == "快讯正文未随公开数据集分发。"
    assert "不得公开分发" not in public.to_json(force_ascii=False)
    assert "另一条完整" not in public.to_json(force_ascii=False)
    assert public["content_source"].tolist() == [
        "derived_headline",
        "redacted",
    ]


def test_verify_manifest_rejects_corrupted_download(tmp_path):
    payload = tmp_path / "daily.parquet"
    payload.write_bytes(b"corrupted")
    manifest = {
        "schema_version": 1,
        "files": [
            {
                "path": "daily.parquet",
                "bytes": len(b"corrupted"),
                "sha256": hashlib.sha256(b"good").hexdigest(),
            }
        ],
    }
    (tmp_path / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(DatasetIntegrityError, match="checksum"):
        verify_manifest(tmp_path)


def test_full_download_is_verified_and_installed_atomically(tmp_path):
    target = tmp_path / "dataset"

    def fake_snapshot_download(*, repo_id, local_dir, repo_type):
        assert repo_id == "ANTICH/traderharness-ashare-5y"
        assert repo_type == "dataset"
        staging = tmp_path / "dataset.download"
        assert local_dir == str(staging)
        payload = staging / "daily.parquet"
        payload.parent.mkdir(parents=True, exist_ok=True)
        payload.write_bytes(b"daily")
        manifest = {
            "schema_version": 1,
            "files": [
                {
                    "path": "daily.parquet",
                    "bytes": 5,
                    "sha256": hashlib.sha256(b"daily").hexdigest(),
                }
            ],
        }
        (staging / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        return str(staging)

    installed = download_full_dataset(target, snapshot_downloader=fake_snapshot_download)

    assert installed == target
    assert (target / "daily.parquet").read_bytes() == b"daily"
    assert not (tmp_path / "dataset.download").exists()
