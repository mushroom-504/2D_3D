import argparse
import shutil
import sys
from pathlib import Path


MAST3R_ROOT = Path(r"C:\Users\荣\Desktop\mast3r-main\mast3r-main")


def collect_images(args):
    images = []
    for view in ["front", "back", "left", "right", "top", "bottom"]:
        value = getattr(args, view)
        if value and Path(value).exists():
            images.append(str(Path(value)))
    return images


def find_model_file(output_dir):
    output_dir = Path(output_dir)
    preferred_names = [
        "scene.glb",
        "model.glb",
        "mesh.glb",
        "scene.obj",
        "model.obj",
        "mesh.obj",
    ]
    for name in preferred_names:
        candidate = output_dir / name
        if candidate.exists():
            return candidate

    for suffix in [".glb", ".obj", ".gltf", ".ply"]:
        matches = sorted(output_dir.rglob(f"*{suffix}"), key=lambda p: p.stat().st_size, reverse=True)
        if matches:
            return matches[0]
    return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--front")
    parser.add_argument("--back")
    parser.add_argument("--left")
    parser.add_argument("--right")
    parser.add_argument("--top")
    parser.add_argument("--bottom")
    parser.add_argument("--device", default="auto")
    parser.add_argument("--image-size", type=int, default=512)
    parser.add_argument("--model-name", default="naver/MASt3R_ViTLarge_BaseDecoder_512_catmlpdpt_metric")
    parser.add_argument("--as-pointcloud", action="store_true")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    images = collect_images(args)
    if len(images) < 2:
        raise SystemExit("MASt3R needs at least two images. Please provide front plus at least one reference view.")

    if not MAST3R_ROOT.exists():
        raise SystemExit(f"MASt3R root not found: {MAST3R_ROOT}")

    sys.path.insert(0, str(MAST3R_ROOT))

    import torch
    from mast3r.model import AsymmetricMASt3R
    from mast3r.demo import get_reconstructed_scene
    import mast3r.utils.path_to_dust3r  # noqa: F401

    if args.device == "auto":
        device = "cuda" if torch.cuda.is_available() else "cpu"
    else:
        device = args.device

    print(f"MASt3R device: {device}")
    print("Images:")
    for image in images:
        print(" -", image)

    model = AsymmetricMASt3R.from_pretrained(args.model_name).to(device)

    scene_state, outfile = get_reconstructed_scene(
        str(output_dir),
        None,
        model,
        None,
        device,
        False,
        args.image_size,
        None,
        images,
        "refine",
        0.07,
        300,
        0.014,
        300,
        2,
        5,
        args.as_pointcloud,
        False,
        True,
        False,
        0.05,
        "swin",
        max(1, min(len(images) - 1, 3)),
        True,
        0,
        0,
        False,
    )

    found = None
    if outfile:
        candidate = Path(outfile)
        if candidate.exists():
            found = candidate
    if found is None:
        found = find_model_file(output_dir)

    if found is None:
        generated = "\n".join(str(p) for p in output_dir.rglob("*"))
        raise SystemExit("MASt3R finished, but no model file was found.\nGenerated files:\n" + generated)

    target = output_dir / ("scene" + found.suffix.lower())
    if found.resolve() != target.resolve():
        shutil.copy2(found, target)

    print(f"MASt3R model exported: {target}")


if __name__ == "__main__":
    main()
