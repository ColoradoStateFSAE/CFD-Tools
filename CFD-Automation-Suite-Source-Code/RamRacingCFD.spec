name: Nightly Development Build

on:
  push:
    branches: [ "main" ]
  workflow_dispatch:

permissions:
  contents: write

jobs:
  # =========================================================================
  # JOB 1: Build the self-contained app with PyInstaller, then package
  # =========================================================================
  build-windows:
    runs-on: windows-latest
    timeout-minutes: 30

    defaults:
      run:
        working-directory: CFD-Automation-Suite-Source-Code

    steps:
      - name: Checkout repository code
        uses: actions/checkout@v4

      - name: Set up Python 3.12
        uses: actions/setup-python@v5
        with:
          python-version: '3.12'
          cache: 'pip'

      # ── Install all Python dependencies ──────────────────────────────
      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          pip install PyQt6 --only-binary=:all:
          pip install ansys-fluent-core
          pip install pyinstaller
          if (Test-Path requirements.txt) { pip install -r requirements.txt }

      # ── Verify critical imports work ─────────────────────────────────
      - name: Verify imports
        run: |
          python -c "import PyQt6.QtWidgets; print('PyQt6 OK')"
          python -c "import ansys.fluent.core; print('PyFluent OK')"
          python -c "from simtypes.configs import HalfCarConfig; print('Configs OK')"
          python -c "from core.runner import run_meshing; print('Runner OK')"

      # ── Build with PyInstaller ───────────────────────────────────────
      # This creates dist/RamRacingCFD/ containing the self-contained
      # executable + all bundled dependencies. No Python install needed
      # on the target machine.
      - name: Build with PyInstaller
        run: |
          pyinstaller --clean RamRacingCFD.spec 2>&1 | Tee-Object -FilePath build.log

          # Verify the exe was actually created and has real content
          if (!(Test-Path "dist\RamRacingCFD\RamRacingCFD.exe")) {
            Write-Error "BUILD FAILED — RamRacingCFD.exe not found"
            Get-Content build.log | Select-Object -Last 50
            exit 1
          }

          $size = (Get-Item "dist\RamRacingCFD\RamRacingCFD.exe").Length / 1MB
          if ($size -lt 1) {
            Write-Error "BUILD FAILED — exe is only $([math]::Round($size, 2)) MB (expected >10 MB)"
            exit 1
          }

          Write-Output "Build successful:"
          Get-ChildItem dist\RamRacingCFD\ | Measure-Object -Property Length -Sum | ForEach-Object {
            Write-Output "  $($_.Count) files, $([math]::Round($_.Sum / 1MB, 1)) MB total"
          }

      # ── Create portable zip (no installer needed) ───────────────────
      - name: Create portable zip
        shell: powershell
        run: |
          $date = Get-Date -Format "yyyyMMdd"
          $sha = (git rev-parse --short HEAD).Trim()
          $zipName = "RamRacingCFD-$date-$sha-portable.zip"
          Compress-Archive -Path dist\RamRacingCFD\* -DestinationPath "..\$zipName"
          Write-Output "Created $zipName ($([math]::Round((Get-Item ..\$zipName).Length / 1MB, 1)) MB)"

      # ── Create NSIS installer (optional — wraps the PyInstaller bundle) ──
      - name: Install NSIS
        uses: negrutiu/nsis-install@v2

      - name: Build NSIS installer
        shell: powershell
        run: |
          # Only build NSIS installer if the .nsi file exists
          if (Test-Path "installer.nsi") {
            makensis installer.nsi
            $date = Get-Date -Format "yyyyMMdd"
            $sha = (git rev-parse --short HEAD).Trim()
            # Find the generated exe and rename it
            Get-ChildItem -Filter *.exe -Exclude RamRacingCFD.exe | Select-Object -First 1 | ForEach-Object {
              Move-Item $_.FullName "..\RamRacingCFD-$date-$sha-setup.exe" -Force
              Write-Output "Installer: RamRacingCFD-$date-$sha-setup.exe"
            }
          } else {
            Write-Output "No installer.nsi found — skipping NSIS build"
          }

      # ── Stage all artifacts ──────────────────────────────────────────
      - name: Stage distribution files
        shell: powershell
        run: |
          mkdir -Force ..\dist-staged
          # Move zip
          Get-ChildItem ..\ -Filter "RamRacingCFD-*-portable.zip" | Move-Item -Destination ..\dist-staged\
          # Move installer exe (if it exists)
          Get-ChildItem ..\ -Filter "RamRacingCFD-*-setup.exe" | Move-Item -Destination ..\dist-staged\
          # List what we're uploading
          Write-Output "Distribution files:"
          Get-ChildItem ..\dist-staged\

      - name: Upload artifacts
        uses: actions/upload-artifact@v4
        with:
          name: windows-build
          path: dist-staged/*
          retention-days: 30

  # =========================================================================
  # JOB 2: Publish Release
  # =========================================================================
  publish-nightly:
    runs-on: ubuntu-latest
    timeout-minutes: 15
    needs: [build-windows]

    steps:
      - name: Checkout repository code
        uses: actions/checkout@v4

      - name: Generate build metadata
        id: metadata
        run: |
          echo "BUILD_DATE=$(date +'%Y%m%d')" >> $GITHUB_OUTPUT
          echo "COMMIT_SHA=$(git rev-parse --short HEAD)" >> $GITHUB_OUTPUT

      - name: Download Windows build
        uses: actions/download-artifact@v4
        with:
          name: windows-build
          path: dist-assets

      - name: List distribution assets
        run: ls -lh dist-assets/

      # Delete old release so there's only ever one nightly
      - name: Delete existing nightly release
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        run: gh release delete nightly-latest --yes --cleanup-tag || true

      - name: Wait for deletion to propagate
        run: sleep 5

      - name: Publish nightly release
        uses: softprops/action-gh-release@v2
        with:
          tag_name: nightly-latest
          name: "Nightly Development Build"
          body: |
            ### Nightly Development Build

            **Portable zip** — unzip anywhere and run `RamRacingCFD.exe`. No Python install required.
            Requires Ansys Fluent 2026 R1 installed separately.

            * **Build Date:** ${{ steps.metadata.outputs.BUILD_DATE }}
            * **Commit:** ${{ steps.metadata.outputs.COMMIT_SHA }}

            ---
            These builds are from `main` and may contain bugs or incomplete features.
          prerelease: true
          files: |
            dist-assets/*
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
