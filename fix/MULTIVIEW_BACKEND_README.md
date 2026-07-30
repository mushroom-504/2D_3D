# External Multi-View 后端

该后端是可选实验功能，不影响默认的 TripoSR 和 CraftsMan 远程服务。

推荐使用下面任一项目相对目录：

```text
2D_3D/
├─ MASt3R/
└─ .venv-mast3r/
   └─ Scripts/python.exe
```

程序会自动寻找：

- `MASt3R`
- `mast3r`
- `mast3r-main`
- `.venv-mast3r/Scripts/python.exe`

如果源码或环境放在别处，不需要修改代码，可以设置：

```powershell
$env:IMAGE3D_MAST3R_DIR = "你的 MASt3R 源码目录"
$env:IMAGE3D_MAST3R_PYTHON = "对应环境的 python.exe"
```

未安装该可选环境时，后端体检只会把 `External Multi-View` 标记为不可用，不会影响 TripoSR、CraftsMan、对话智能体和 Blender 修复流程。
