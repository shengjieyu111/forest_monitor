$ErrorActionPreference = 'Stop'

$projectRoot = Resolve-Path (Join-Path $PSScriptRoot '..\..')
$maven = 'D:\Desktop\IDEA\IntelliJ IDEA Community Edition 2024.2.3\plugins\maven\lib\maven3\bin\mvn.cmd'
$java = 'D:\java11\bin\java.exe'
$python = Join-Path $projectRoot '.venv\Scripts\python.exe'
$managePy = Join-Path $projectRoot 'manage.py'

Push-Location $projectRoot
try {
    & $maven -q -DskipTests compile
    if ($LASTEXITCODE -ne 0) {
        throw 'Maven compilation failed.'
    }

    & $maven -q dependency:build-classpath '-Dmdep.outputFile=target\runtime-classpath.txt'
    if ($LASTEXITCODE -ne 0) {
        throw 'Maven dependency resolution failed.'
    }

    $dependencyClasspath = (Get-Content -Raw -Encoding UTF8 'target\runtime-classpath.txt').Trim()
    $classpath = "target\classes;$dependencyClasspath"
    & $java '-Dfile.encoding=UTF-8' -classpath $classpath WeatherAnalyticsSuite /waether/input /waether
    if ($LASTEXITCODE -ne 0) {
        throw 'MapReduce analytics failed.'
    }

    & $python $managePy sync_mapreduce_results
    if ($LASTEXITCODE -ne 0) {
        throw 'Database synchronization failed.'
    }

    Write-Host 'MapReduce analytics completed and results were saved to SQLite.' -ForegroundColor Green
}
finally {
    Pop-Location
}
