# 灵犀助教 - 桌宠模式一键启动脚本

Write-Host "=====================================" -ForegroundColor Cyan
Write-Host "      灵犀助教 - 桌宠模式启动        " -ForegroundColor Green
Write-Host "=====================================" -ForegroundColor Cyan
Write-Host ""

# 检查 uv 环境
Write-Host "[1/3] 检查 uv 环境..." -ForegroundColor Yellow
if (Get-Command uv -ErrorAction SilentlyContinue) {
    Write-Host "✓ 已检测到 uv" -ForegroundColor Green
} else {
    Write-Host "✗ 未检测到 uv，请先安装 uv" -ForegroundColor Red
    Write-Host "安装命令: pip install uv" -ForegroundColor Yellow
    Read-Host "按回车键退出"
    exit 1
}

# 检查 Node.js 环境
Write-Host "[2/3] 检查 Node.js 环境..." -ForegroundColor Yellow
if (Get-Command node -ErrorAction SilentlyContinue) {
    Write-Host "✓ 已检测到 Node.js" -ForegroundColor Green
} else {
    Write-Host "✗ 未检测到 Node.js，桌宠模式需要 Node.js" -ForegroundColor Red
    Write-Host "请安装 Node.js: https://nodejs.org/" -ForegroundColor Yellow
    Read-Host "按回车键退出"
    exit 1
}

# 同步项目依赖
Write-Host "[3/3] 同步项目依赖..." -ForegroundColor Yellow
uv sync

if ($LASTEXITCODE -ne 0) {
    Write-Host "✗ 依赖同步失败" -ForegroundColor Red
    Read-Host "按回车键退出"
    exit 1
}
Write-Host "✓ 依赖同步完成" -ForegroundColor Green

# 智能等待后端启动的函数
function Wait-BackendReady {
    param([int]$TimeoutSeconds = 60)
    
    Write-Host "等待后端服务启动..." -ForegroundColor Yellow
    $startTime = Get-Date
    $backendUrl = "http://localhost:12393"
    $dots = 0
    
    while (((Get-Date) - $startTime).TotalSeconds -lt $TimeoutSeconds) {
        try {
            $response = Invoke-WebRequest -Uri $backendUrl -Method GET -TimeoutSec 2 -ErrorAction SilentlyContinue
            if ($response.StatusCode -eq 200 -or $response.StatusCode -eq 404) {
                Write-Host ""
                Write-Host "✓ 后端服务已就绪" -ForegroundColor Green
                return $true
            }
        } catch { }
        
        Write-Host "." -NoNewline -ForegroundColor Gray
        $dots++
        if ($dots % 60 -eq 0) { Write-Host "" }
        Start-Sleep -Seconds 1
    }
    
    Write-Host ""
    Write-Host "⚠ 后端服务启动超时（${TimeoutSeconds}秒）" -ForegroundColor Yellow
    return $false
}

Write-Host ""
Write-Host "启动灵犀助教（桌宠模式）..." -ForegroundColor Green

# 启动后端服务（后台窗口）
Write-Host "启动后端服务..." -ForegroundColor Yellow
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$PSScriptRoot'; uv run run_server.py"

# 等待后端就绪
$ready = Wait-BackendReady -TimeoutSeconds 60

if ($ready) {
    Write-Host ""
    Write-Host "=====================================" -ForegroundColor Cyan
    Write-Host "快捷键说明：" -ForegroundColor Green
    Write-Host "  Ctrl+Shift+L: 切换桌宠/正常模式" -ForegroundColor White
    Write-Host "  Ctrl+Shift+H: 隐藏/显示窗口" -ForegroundColor White
    Write-Host "  Ctrl+Shift+Q: 退出应用" -ForegroundColor White
    Write-Host "=====================================" -ForegroundColor Cyan
    Write-Host ""
    
    # 启动桌面客户端
    Write-Host "启动桌宠客户端..." -ForegroundColor Green
    Set-Location "$PSScriptRoot\desktop_launcher"
    
    if (-not (Test-Path "node_modules")) {
        Write-Host "首次运行，正在安装前端依赖..." -ForegroundColor Yellow
        npm install
    }
    
    npm start
} else {
    Write-Host "后端启动超时，请检查后端窗口的错误信息" -ForegroundColor Red
    Read-Host "按回车键退出"
    exit 1
}
