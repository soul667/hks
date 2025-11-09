# 手部追踪 - 快速开始脚本
# 适用于 Windows PowerShell

Write-Host "==================================" -ForegroundColor Cyan
Write-Host "手部轨迹追踪 - 环境设置" -ForegroundColor Cyan
Write-Host "==================================" -ForegroundColor Cyan
Write-Host ""

# 检查 Python 版本
Write-Host "检查 Python 版本..." -ForegroundColor Yellow
$pythonVersion = python --version 2>&1
Write-Host "当前版本: $pythonVersion" -ForegroundColor Green

if ($pythonVersion -match "3\.13") {
    Write-Host ""
    Write-Host "警告: 检测到 Python 3.13，MediaPipe 不支持此版本！" -ForegroundColor Red
    Write-Host ""
    Write-Host "请选择以下方案之一：" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "方案 1: 使用 Python 3.12 创建虚拟环境" -ForegroundColor Cyan
    Write-Host "  1. 安装 Python 3.12 (https://www.python.org/downloads/)" -ForegroundColor White
    Write-Host "  2. 运行: py -3.12 -m venv venv312" -ForegroundColor White
    Write-Host "  3. 运行: .\venv312\Scripts\Activate.ps1" -ForegroundColor White
    Write-Host "  4. 运行: pip install mediapipe opencv-python numpy" -ForegroundColor White
    Write-Host ""
    Write-Host "方案 2: 使用 conda" -ForegroundColor Cyan
    Write-Host "  1. 运行: conda create -n handtrack python=3.12" -ForegroundColor White
    Write-Host "  2. 运行: conda activate handtrack" -ForegroundColor White
    Write-Host "  3. 运行: pip install mediapipe opencv-python numpy" -ForegroundColor White
    Write-Host ""
    Write-Host "详细说明请查看: HAND_TRACKING_GUIDE.md" -ForegroundColor Green
    Write-Host ""
    exit 1
}

# 创建虚拟环境（如果不存在）
if (-not (Test-Path ".\venv_handtrack")) {
    Write-Host ""
    Write-Host "创建虚拟环境..." -ForegroundColor Yellow
    python -m venv venv_handtrack
    Write-Host "✓ 虚拟环境已创建" -ForegroundColor Green
}

# 激活虚拟环境
Write-Host ""
Write-Host "激活虚拟环境..." -ForegroundColor Yellow
& .\venv_handtrack\Scripts\Activate.ps1

# 安装依赖
Write-Host ""
Write-Host "安装依赖包..." -ForegroundColor Yellow
pip install --upgrade pip
pip install mediapipe opencv-python numpy

Write-Host ""
Write-Host "==================================" -ForegroundColor Green
Write-Host "✓ 安装完成！" -ForegroundColor Green
Write-Host "==================================" -ForegroundColor Green
Write-Host ""
Write-Host "使用示例：" -ForegroundColor Cyan
Write-Host "  python hand_tracking.py input.mp4" -ForegroundColor White
Write-Host "  python hand_tracking.py input.mp4 -o output.mp4 -t 2.0" -ForegroundColor White
Write-Host ""
Write-Host "更多帮助：" -ForegroundColor Cyan
Write-Host "  python hand_tracking.py --help" -ForegroundColor White
Write-Host "  查看 HAND_TRACKING_GUIDE.md" -ForegroundColor White
Write-Host ""
