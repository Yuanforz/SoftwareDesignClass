# 灵犀助教 - 启动脚本

Write-Host "=====================================" -ForegroundColor Cyan
Write-Host "    灵犀助教 - AI学习助手启动工具    " -ForegroundColor Green
Write-Host "=====================================" -ForegroundColor Cyan
Write-Host ""

# 检查Python环境
Write-Host "[1/3] 检查Python环境..." -ForegroundColor Yellow
if (Get-Command uv -ErrorAction SilentlyContinue) {
    Write-Host "✓ 已检测到 uv" -ForegroundColor Green
} else {
    Write-Host "✗ 未检测到 uv，请先安装 uv" -ForegroundColor Red
    Write-Host "安装命令: pip install uv" -ForegroundColor Yellow
    exit 1
}

# 同步项目依赖
Write-Host "[2/3] 同步项目依赖..." -ForegroundColor Yellow
Write-Host "正在安装依赖（包括 CUDA 版 PyTorch 和 FunASR）..." -ForegroundColor Cyan
uv sync

if ($LASTEXITCODE -ne 0) {
    Write-Host "✗ 依赖同步失败" -ForegroundColor Red
    Write-Host "请检查网络连接和 pyproject.toml 配置" -ForegroundColor Yellow
    exit 1
}

Write-Host "✓ 依赖同步完成" -ForegroundColor Green

# 检查Node.js环境
Write-Host "[3/3] 检查Node.js环境..." -ForegroundColor Yellow
if (Get-Command node -ErrorAction SilentlyContinue) {
    Write-Host "✓ 已检测到 Node.js" -ForegroundColor Green
} 
else {
    Write-Host "✗ 未检测到 Node.js，桌面客户端将无法启动" -ForegroundColor Red
    Write-Host "您可以继续使用网页版，或安装 Node.js 后使用桌面版" -ForegroundColor Yellow
}

# 智能等待后端启动的函数
function Wait-BackendReady {
    param(
        [int]$TimeoutSeconds = 60
    )
    
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
        } catch {
            # 继续等待
        }
        
        Write-Host "." -NoNewline -ForegroundColor Gray
        $dots++
        if ($dots % 60 -eq 0) {
            Write-Host ""
        }
        Start-Sleep -Seconds 1
    }
    
    Write-Host ""
    Write-Host "⚠ 后端服务启动超时（${TimeoutSeconds}秒）" -ForegroundColor Yellow
    Write-Host "后端可能仍在启动中，请检查日志" -ForegroundColor Yellow
    return $false
}

Write-Host ""
Write-Host "请选择启动模式：" -ForegroundColor Cyan
Write-Host "1. 桌面客户端模式（推荐，桌宠模式）" -ForegroundColor White
Write-Host "2. 网页浏览器模式" -ForegroundColor White
Write-Host "3. 仅启动后端服务" -ForegroundColor White
Write-Host ""

$choice = Read-Host "请输入选项 (1/2/3)"

switch ($choice) {
    "1" {
        Write-Host ""
        Write-Host "启动灵犀助教（桌面客户端模式）..." -ForegroundColor Yellow
        
        # 启动后端服务
        Write-Host "启动后端服务..." -ForegroundColor Green
        Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$PSScriptRoot'; uv run run_server.py"
        
        # 智能等待后端启动
        $ready = Wait-BackendReady -TimeoutSeconds 60
        
        if ($ready) {
            # 启动桌面客户端
            Write-Host "启动桌面客户端..." -ForegroundColor Green
            Set-Location "$PSScriptRoot\desktop_launcher"
            
            if (-not (Test-Path "node_modules")) {
                Write-Host "首次运行，正在安装依赖..." -ForegroundColor Yellow
                npm install
            }
            
            npm start
        } else {
            Write-Host "您可以稍后手动启动桌面客户端或检查后端日志" -ForegroundColor Yellow
        }
    }
    "2" {
        Write-Host ""
        Write-Host "启动灵犀助教（网页模式）..." -ForegroundColor Yellow
        
        # 启动后端服务
        Write-Host "启动后端服务..." -ForegroundColor Green
        Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$PSScriptRoot'; uv run run_server.py"
        
        # 智能等待后端启动
        $ready = Wait-BackendReady -TimeoutSeconds 60
        
        if ($ready) {
            # 打开浏览器
            Write-Host "打开浏览器..." -ForegroundColor Green
            Start-Process "http://localhost:12393"
            
            Write-Host ""
            Write-Host "✓ 灵犀助教已启动！" -ForegroundColor Green
        } else {
            Write-Host ""
            Write-Host "如后端启动完成，请手动访问: http://localhost:12393" -ForegroundColor Cyan
        }
    }
    "3" {
        Write-Host ""
        Write-Host "启动后端服务..." -ForegroundColor Yellow
        uv run run_server.py
    }
    default {
        Write-Host "无效的选项，请重新运行脚本" -ForegroundColor Red
        exit 1
    }
}

Write-Host ""
Write-Host "=====================================" -ForegroundColor Cyan
Write-Host "快捷键说明（桌面客户端模式）：" -ForegroundColor Green
Write-Host "  Ctrl+Shift+L: 切换桌宠/正常模式" -ForegroundColor White
Write-Host "  Ctrl+Shift+H: 隐藏/显示窗口" -ForegroundColor White
Write-Host "  Ctrl+Shift+Q: 退出应用" -ForegroundColor White
Write-Host "=====================================" -ForegroundColor Cyan
