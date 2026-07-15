# Multi-view backend notes

The desktop tool now has two generation backends:

1. `TripoSR`
   - Stable default backend.
   - Uses only the front image to create the base mesh.
   - Other views are used by the agent analysis and Blender modification prompt.

2. `External Multi-View`
   - Adapter for DUSt3R, MASt3R, or another multi-view reconstruction runner.
   - This project does not install those heavy environments automatically.
   - Configure it with environment variables:

```powershell
setx MULTIVIEW_RECON_PYTHON "D:\your_multiview_env\python.exe"
setx MULTIVIEW_RECON_SCRIPT "C:\path\to\your_multiview_runner.py"
```

The external runner should accept:

```text
--output-dir <folder>
--front <image>
--back <image>
--left <image>
--right <image>
--top <image>
--bottom <image>
```

It should write one of these files:

```text
mesh.obj
model.obj
scene.obj
```

The desktop tool will then import that OBJ into Blender and export:

```text
result.blend
model.glb
model.fbx
model.stl
preview.png
```
