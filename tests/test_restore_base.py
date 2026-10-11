import json

import numpy as np
from safetensors.numpy import load_file, save_file

from restore_base import copy_mtp, copy_missing_files


def test_copies_missing_mtp_tensors_and_indexes_them(tmp_path):
    base, ckpt = tmp_path / "base", tmp_path / "ckpt"
    base.mkdir()
    ckpt.mkdir()
    save_file({"model.layers.0.w": np.zeros(2, np.float32), "mtp.fc.weight": np.ones((2, 2), np.float32),
               "model.mtp.norm.weight": np.full(3, 2, np.float32)}, str(base / "model.safetensors"))
    save_file({"model.layers.0.w": np.full(2, 7, np.float32)}, str(ckpt / "model.safetensors"))

    assert copy_mtp(base, ckpt) == 2

    index = json.loads((ckpt / "model.safetensors.index.json").read_text())["weight_map"]
    assert index == {"model.layers.0.w": "model.safetensors",
                     "mtp.fc.weight": "mtp.safetensors", "model.mtp.norm.weight": "mtp.safetensors"}
    mtp = load_file(str(ckpt / "mtp.safetensors"))
    assert (mtp["mtp.fc.weight"] == 1).all() and (mtp["model.mtp.norm.weight"] == 2).all()
    assert (load_file(str(ckpt / "model.safetensors"))["model.layers.0.w"] == 7).all()  # trained weights untouched


def test_noop_when_checkpoint_already_has_mtp(tmp_path):
    base, ckpt = tmp_path / "base", tmp_path / "ckpt"
    base.mkdir()
    ckpt.mkdir()
    save_file({"mtp.fc.weight": np.ones(2, np.float32)}, str(base / "model.safetensors"))
    save_file({"mtp.fc.weight": np.zeros(2, np.float32)}, str(ckpt / "model.safetensors"))
    assert copy_mtp(base, ckpt) == 0
    assert not (ckpt / "mtp.safetensors").exists()


def test_copies_only_missing_processor_files(tmp_path):
    base, ckpt = tmp_path / "base", tmp_path / "ckpt"
    base.mkdir()
    ckpt.mkdir()
    for name, text in [("preprocessor_config.json", "P"), ("video_preprocessor_config.json", "V"),
                       ("config.json", "BASE"), ("model.safetensors.index.json", "BASE-INDEX"),
                       ("chat_template.jinja", "T")]:
        (base / name).write_text(text)
    (ckpt / "config.json").write_text("TRAINED")

    copied = copy_missing_files(base, ckpt)

    assert sorted(copied) == ["chat_template.jinja", "preprocessor_config.json", "video_preprocessor_config.json"]
    assert (ckpt / "config.json").read_text() == "TRAINED"            # never overwrite trained files
    assert not (ckpt / "model.safetensors.index.json").exists()      # base index points at base weight files
