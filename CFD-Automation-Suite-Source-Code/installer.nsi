; ============================================================
; Ram Racing CFD Automation Tool — NSIS Installer Script
; Build: makensis installer.nsi
; Output: RamRacingCFD-Setup.exe
; ============================================================

Unicode True

; ── Installer metadata ────────────────────────────────────────────────────────
!define APP_NAME        "Ram Racing CFD Automation Tool"
!define APP_VERSION     "1.0.0"
!define APP_PUBLISHER   "Ram Racing Aerodynamic Subteam"
!define APP_EXE         "RamRacingCFD.exe"
!define INSTALL_DIR     "$PROGRAMFILES64\RamRacingCFD"
!define UNINSTALLER     "Uninstall.exe"
!define REG_KEY         "Software\Microsoft\Windows\CurrentVersion\Uninstall\RamRacingCFD"

; ── Output file ───────────────────────────────────────────────────────────────
Name "${APP_NAME}"
OutFile "RamRacingCFD-Setup.exe"
InstallDir "${INSTALL_DIR}"
InstallDirRegKey HKLM "${REG_KEY}" "InstallLocation"
RequestExecutionLevel admin

; ── Modern UI ─────────────────────────────────────────────────────────────────
!include "MUI2.nsh"

!define MUI_ABORTWARNING
!define MUI_ICON "assets\logo.ico"
!define MUI_UNICON "assets\logo.ico"

; Header / welcome images (optional — comment out if you don't have them)
; !define MUI_WELCOMEFINISHPAGE_BITMAP "assets\installer_banner.bmp"

!define MUI_WELCOMEPAGE_TITLE "Ram Racing CFD Automation Tool"
!define MUI_WELCOMEPAGE_TEXT "This will install the Ram Racing CFD Automation Tool $\r$\n$\r$\nThe tool automates the full Fluent 2024R2 CFD pipeline including meshing, solver ramp-up, and results export.$\r$\n$\r$\nAnsys Fluent 2024R2 must already be installed and licensed on this machine."

; ── Pages ─────────────────────────────────────────────────────────────────────
!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_LICENSE "Documentation\LICENSE.txt"
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH

!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES

!insertmacro MUI_LANGUAGE "English"

; ── Install section ───────────────────────────────────────────────────────────
Section "Main Application" SecMain

    SectionIn RO  ; required, cannot be deselected

    SetOutPath "$INSTDIR"

    ; Copy entire PyInstaller dist folder
    File /r "dist\RamRacingCFD\*.*"

    ; Write uninstaller
    WriteUninstaller "$INSTDIR\${UNINSTALLER}"

    ; ── Registry entries (Add/Remove Programs) ────────────────────────────────
    WriteRegStr   HKLM "${REG_KEY}" "DisplayName"      "${APP_NAME}"
    WriteRegStr   HKLM "${REG_KEY}" "DisplayVersion"   "${APP_VERSION}"
    WriteRegStr   HKLM "${REG_KEY}" "Publisher"        "${APP_PUBLISHER}"
    WriteRegStr   HKLM "${REG_KEY}" "InstallLocation"  "$INSTDIR"
    WriteRegStr   HKLM "${REG_KEY}" "UninstallString"  "$INSTDIR\${UNINSTALLER}"
    WriteRegStr   HKLM "${REG_KEY}" "DisplayIcon"      "$INSTDIR\${APP_EXE}"
    WriteRegDWORD HKLM "${REG_KEY}" "NoModify"         1
    WriteRegDWORD HKLM "${REG_KEY}" "NoRepair"         1

    ; ── Start Menu shortcut ───────────────────────────────────────────────────
    CreateDirectory "$SMPROGRAMS\Ram Racing"
    CreateShortcut  "$SMPROGRAMS\Ram Racing\CFD Automation Tool.lnk" \
                    "$INSTDIR\${APP_EXE}" "" \
                    "$INSTDIR\${APP_EXE}" 0 \
                    SW_SHOWNORMAL "" \
                    "Ram Racing CFD Automation Tool"
    CreateShortcut  "$SMPROGRAMS\Ram Racing\Uninstall CFD Tool.lnk" \
                    "$INSTDIR\${UNINSTALLER}"

    ; ── Desktop shortcut (optional) ───────────────────────────────────────────
    CreateShortcut  "$DESKTOP\Ram Racing CFD Tool.lnk" \
                    "$INSTDIR\${APP_EXE}" "" \
                    "$INSTDIR\${APP_EXE}" 0 \
                    SW_SHOWNORMAL "" \
                    "Ram Racing CFD Automation Tool"

SectionEnd

; ── Uninstall section ─────────────────────────────────────────────────────────
Section "Uninstall"

    ; Remove all installed files
    RMDir /r "$INSTDIR"

    ; Remove Start Menu shortcuts
    RMDir /r "$SMPROGRAMS\Ram Racing"

    ; Remove Desktop shortcut
    Delete "$DESKTOP\Ram Racing CFD Tool.lnk"

    ; Remove registry entries
    DeleteRegKey HKLM "${REG_KEY}"

SectionEnd

; ── Finish page — launch app after install ────────────────────────────────────
!define MUI_FINISHPAGE_RUN         "$INSTDIR\${APP_EXE}"
!define MUI_FINISHPAGE_RUN_TEXT    "Launch Ram Racing CFD Tool"
!define MUI_FINISHPAGE_SHOWREADME  "$INSTDIR\utils\Wheel_MRF_Setup_Guide.pdf"
!define MUI_FINISHPAGE_SHOWREADME_TEXT "Open Wheel MRF Setup Guide"
