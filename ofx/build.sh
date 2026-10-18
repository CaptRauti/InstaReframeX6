#!/bin/bash
# Build InstaReframeX6 OFX plugin with llvm-mingw clang
set -e
LLVMBIN="$LOCALAPPDATA/Microsoft/WinGet/Packages/MartinStorsjo.LLVM-MinGW.UCRT_Microsoft.Winget.Source_8wekyb3d8bbwe/llvm-mingw-20260908-ucrt-x86_64/bin"
SDK="C:/Users/stefa/AppData/Local/hermes/cache/scratch/ofx/OpenFX"
OBJ="C:/Users/stefa/AppData/Local/hermes/cache/scratch/ofx/obj"
OUT="C:/Users/stefa/insta-reframe-x6-release/ofx"
mkdir -p "$OBJ" "$OUT"

FLAGS="-c -O2 -std=c++17 -DNDEBUG -D_HAS_AUTO_PTR_ETC -I $SDK/include -I $SDK/Support/include -I $SDK/Support/Plugins/include"

# 1) compile OFX support library
for f in "$SDK"/Support/Library/*.cpp; do
    n=$(basename "${f%.cpp}")
    if [ ! -f "$OBJ/$n.o" ] || [ "$f" -nt "$OBJ/$n.o" ]; then
        "$LLVMBIN/clang++" $FLAGS -o "$OBJ/$n.o" "$f"
        echo "support: $n"
    fi
done

# 2) compile plugin + link DLL (static runtime, self-contained)
"$LLVMBIN/clang++" $FLAGS -o "$OBJ/plugin.o" "$OUT/plugin.cpp"
"$LLVMBIN/clang++" -shared -static -static-libgcc -o "$OUT/InstaReframeX6.dll" \
    "$OBJ/plugin.o" "$OBJ"/ofxs*.o -l user32 -l gdi32 -l ole32
echo "BUILT: $OUT/InstaReframeX6.dll"
ls -la "$OUT/InstaReframeX6.dll"
# exported entry points
"$LLVMBIN/llvm-nm" -g --defined-only "$OUT/InstaReframeX6.dll" | grep -i "OfxGet"