param(
    [switch] $Debug,
    [switch] $NoDpp,
    [string] $VcpkgPrefix = "C:\vcpkg\installed\x64-windows",
    [string] $VsDevCmd = "C:\Program Files\Microsoft Visual Studio\18\Community\Common7\Tools\VsDevCmd.bat"
)

$ErrorActionPreference = "Stop"

$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
$Python = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $Python)) {
    throw "Missing project virtualenv. Create it first with: python -m venv .venv"
}

$NanobindDir = & $Python -m nanobind --cmake_dir
if ($LASTEXITCODE -ne 0) {
    throw "nanobind is not installed in .venv. Run: .\.venv\Scripts\python.exe -m pip install nanobind"
}

$BuildType = if ($Debug) { "Debug" } else { "Release" }
$DppEnabled = if ($NoDpp) { "OFF" } else { "ON" }
$BuildSuffix = if ($NoDpp) { "no-dpp" } else { "dpp" }
$BuildDir = Join-Path $Root "build\$($BuildType.ToLower())-$BuildSuffix-vs"

$Configure = @(
    "cmake",
    "-S `"$Root`"",
    "-B `"$BuildDir`"",
    "-G Ninja",
    "-DCMAKE_BUILD_TYPE=$BuildType",
    "-DDIRECTIONER_WITH_DPP=$DppEnabled",
    "-DPython_EXECUTABLE=`"$Python`"",
    "-Dnanobind_DIR=`"$NanobindDir`""
)

if (-not $NoDpp) {
    $Configure += "-DCMAKE_PREFIX_PATH=`"$VcpkgPrefix`""
}

$Command = "`"$VsDevCmd`" -arch=x64 -host_arch=x64 && $($Configure -join ' ') && cmake --build `"$BuildDir`""
cmd.exe /d /c $Command
if ($LASTEXITCODE -ne 0) {
    throw "Native build failed."
}

