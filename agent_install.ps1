# agent_install.ps1
# Быстрая установка и запуск агента ADB Device Manager на Windows

$ErrorActionPreference = 'Stop'

Write-Host "[INFO] Скачиваем проект с GitHub..."
$zipUrl = "https://github.com/Ladderface/1337/archive/refs/heads/main.zip"
$dest = "$env:TEMP\1337.zip"
Invoke-WebRequest -Uri $zipUrl -OutFile $dest

Write-Host "[INFO] Распаковываем архив..."
$target = "C:\ADBClient"
if (!(Test-Path $target)) { New-Item -ItemType Directory -Path $target | Out-Null }
Expand-Archive -Path $dest -DestinationPath $target -Force

# Путь к агенту
$agentPath = Join-Path $target "1337-main\agent"
cd $agentPath

# Проверка Python
if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    Write-Host "[INFO] Python не найден. Скачиваем и устанавливаем..."
    $pyInstaller = "$env:TEMP\python-installer.exe"
    Invoke-WebRequest -Uri "https://www.python.org/ftp/python/3.11.8/python-3.11.8-amd64.exe" -OutFile $pyInstaller
    Start-Process -Wait -FilePath $pyInstaller -ArgumentList "/quiet InstallAllUsers=1 PrependPath=1"
    $env:Path += ";C:\Python311;C:\Python311\Scripts"
}

Write-Host "[INFO] Устанавливаем зависимости..."
python -m pip install --upgrade pip
python -m pip install -r ..\..\requirements.txt

Write-Host "[INFO] Запускаем агента..."
python agent.py 