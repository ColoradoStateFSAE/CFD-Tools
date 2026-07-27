; =============================================================================
;  Ram Racing CFD Automation Suite - Windows Installer
;  Colorado State University FSAE - Aerodynamics Subteam
;
;  IMPORTANT: This script packages the PyInstaller output, NOT raw source.
;  You must run PyInstaller BEFORE compiling this installer:
;
;      pyinstaller --clean RamRacingCFD.spec
;      makensis installer.nsi
;
;  Expects: dist\RamRacingCFD\RamRacingCFD.exe to exist
;  Output:  RamRacingCFD-Setup.exe
; =============================================================================

Unicode True

!include "MUI2.nsh"
!include "LogicLib.nsh"
!include "FileFunc.nsh"
!include "x64.nsh"

; ─── Product metadata ────────────────────────────────────────────────────────
!define PRODUCT_NAME        "Ram Racing CFD Automation Suite"
!define PRODUCT_SHORT       "RamRacingCFD"
!define PRODUCT_VERSION     "0.1.0"
!define PRODUCT_PUBLISHER   "Colorado State University FSAE - Ram Racing"
!define PRODUCT_WEB_SITE    "https://github.com/ColoradoStateFSAE/CFD-Tools"
!define PRODUCT_EXE         "RamRacingCFD.exe"
!define PRODUCT_DIR_REGKEY  "Software\Microsoft\Windows\CurrentVersion\App Paths\${PRODUCT_EXE}"
!define PRODUCT_UNINST_KEY  "Software\Microsoft\Windows\CurrentVersion\Uninstall\${PRODUCT_SHORT}"

; ─── Source directory (PyInstaller output) ───────────────────────────────────
!define BUILD_DIR "dist\RamRacingCFD"

; ─── Installer configuration ─────────────────────────────────────────────────
Name          "${PRODUCT_NAME}"
OutFile       "RamRacingCFD-Setup.exe"
InstallDir    "$PROGRAMFILES64\Ram Racing\CFD Automation Suite"
InstallDirRegKey HKLM "${PRODUCT_DIR_REGKEY}" ""
RequestExecutionLevel admin
ShowInstDetails   show
ShowUnInstDetails show
SetCompressor /SOLID lzma

; ─── Version info block (shows in file properties) ───────────────────────────
VIProductVersion "0.0.2.0"
VIAddVersionKey "ProductName"     "${PRODUCT_NAME}"
VIAddVersionKey "CompanyName"     "${PRODUCT_PUBLISHER}"
VIAddVersionKey "FileDescription" "${PRODUCT_NAME} Installer"
VIAddVersionKey "FileVersion"     "${PRODUCT_VERSION}"
VIAddVersionKey "ProductVersion"  "${PRODUCT_VERSION}"
VIAddVersionKey "LegalCopyright"  "(c) Colorado State University FSAE"

; ─── Modern UI configuration ─────────────────────────────────────────────────
!define MUI_ABORTWARNING
!define MUI_ICON   "${NSISDIR}\Contrib\Graphics\Icons\modern-install.ico"
!define MUI_UNICON "${NSISDIR}\Contrib\Graphics\Icons\modern-uninstall.ico"

; Welcome page text
!define MUI_WELCOMEPAGE_TITLE "Ram Racing CFD Automation Suite"
!define MUI_WELCOMEPAGE_TEXT  "This will install the Ram Racing CFD Automation Suite on your computer.$\r$\n$\r$\nThis application automates Ansys Fluent meshing and solving workflows for FSAE aerodynamics.$\r$\n$\r$\nRequirements:$\r$\n  - Ansys Fluent 2026 R1 (v261) installed and licensed$\r$\n  - 64-bit Windows 10 or later$\r$\n  - ~500 MB free disk space$\r$\n$\r$\nPython is NOT required - all dependencies are bundled.$\r$\n$\r$\nClick Next to continue."

; Finish page
!define MUI_FINISHPAGE_RUN            "$INSTDIR\${PRODUCT_EXE}"
!define MUI_FINISHPAGE_RUN_TEXT       "Launch Ram Racing CFD now"
!define MUI_FINISHPAGE_SHOWREADME     "$INSTDIR\README.md"
!define MUI_FINISHPAGE_SHOWREADME_TEXT "View README"
!define MUI_FINISHPAGE_SHOWREADME_NOTCHECKED
!define MUI_FINISHPAGE_LINK           "Ram Racing CFD-Tools on GitHub"
!define MUI_FINISHPAGE_LINK_LOCATION  "${PRODUCT_WEB_SITE}"

; ─── Installer pages ─────────────────────────────────────────────────────────
!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH

; ─── Uninstaller pages ───────────────────────────────────────────────────────
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES

!insertmacro MUI_LANGUAGE "English"

; =============================================================================
;  Pre-install checks
; =============================================================================
Function .onInit
    ; Require 64-bit Windows
    ${IfNot} ${RunningX64}
        MessageBox MB_OK|MB_ICONSTOP \
            "This application requires 64-bit Windows.$\r$\n$\r$\nInstallation cannot continue."
        Abort
    ${EndIf}

    ; Warn if a previous version is installed
    ReadRegStr $R0 HKLM "${PRODUCT_UNINST_KEY}" "UninstallString"
    ${If} $R0 != ""
        MessageBox MB_YESNO|MB_ICONQUESTION \
            "A previous version of ${PRODUCT_NAME} is already installed.$\r$\n$\r$\n\
             Uninstall it before continuing?" \
            IDNO skip_uninstall
        ExecWait '$R0 /S _?=$INSTDIR'
        skip_uninstall:
    ${EndIf}
FunctionEnd

; =============================================================================
;  Main install section
; =============================================================================
Section "Application (required)" SEC_APP
    SectionIn RO   ; read-only, cannot be deselected

    SetOutPath "$INSTDIR"
    SetOverwrite try

    ; ── Copy the entire PyInstaller bundle ───────────────────────────────
    ; This includes RamRacingCFD.exe, all bundled Python runtime,
    ; PyQt6 DLLs, PyFluent packages, and the _internal folder.
    DetailPrint "Installing application files..."
    File /r "${BUILD_DIR}\*.*"

    ; ── Copy documentation if present ────────────────────────────────────
    ${If} ${FileExists} "README.md"
        File "README.md"
    ${EndIf}

    ; ── Verify the executable actually landed ────────────────────────────
    ${IfNot} ${FileExists} "$INSTDIR\${PRODUCT_EXE}"
        MessageBox MB_OK|MB_ICONSTOP \
            "Installation failed: ${PRODUCT_EXE} was not copied.$\r$\n$\r$\n\
             The installer package may be corrupt or was built incorrectly.$\r$\n\
             Ensure PyInstaller was run before building this installer."
        Abort
    ${EndIf}

    ; ── Registry: App Paths (allows running from Win+R) ──────────────────
    WriteRegStr HKLM "${PRODUCT_DIR_REGKEY}" "" "$INSTDIR\${PRODUCT_EXE}"
    WriteRegStr HKLM "${PRODUCT_DIR_REGKEY}" "Path" "$INSTDIR"

    ; ── Registry: Add/Remove Programs entry ──────────────────────────────
    WriteRegStr HKLM "${PRODUCT_UNINST_KEY}" "DisplayName"     "${PRODUCT_NAME}"
    WriteRegStr HKLM "${PRODUCT_UNINST_KEY}" "DisplayVersion"  "${PRODUCT_VERSION}"
    WriteRegStr HKLM "${PRODUCT_UNINST_KEY}" "Publisher"       "${PRODUCT_PUBLISHER}"
    WriteRegStr HKLM "${PRODUCT_UNINST_KEY}" "URLInfoAbout"    "${PRODUCT_WEB_SITE}"
    WriteRegStr HKLM "${PRODUCT_UNINST_KEY}" "DisplayIcon"     "$INSTDIR\${PRODUCT_EXE}"
    WriteRegStr HKLM "${PRODUCT_UNINST_KEY}" "UninstallString" "$INSTDIR\uninstall.exe"
    WriteRegStr HKLM "${PRODUCT_UNINST_KEY}" "InstallLocation" "$INSTDIR"
    WriteRegDWORD HKLM "${PRODUCT_UNINST_KEY}" "NoModify" 1
    WriteRegDWORD HKLM "${PRODUCT_UNINST_KEY}" "NoRepair" 1

    ; Record installed size for Add/Remove Programs
    ${GetSize} "$INSTDIR" "/S=0K" $0 $1 $2
    IntFmt $0 "0x%08X" $0
    WriteRegDWORD HKLM "${PRODUCT_UNINST_KEY}" "EstimatedSize" "$0"

    ; ── Write uninstaller ────────────────────────────────────────────────
    WriteUninstaller "$INSTDIR\uninstall.exe"
SectionEnd

; =============================================================================
;  Start Menu shortcuts
; =============================================================================
Section "Start Menu shortcuts" SEC_STARTMENU
    CreateDirectory "$SMPROGRAMS\Ram Racing"
    CreateShortCut  "$SMPROGRAMS\Ram Racing\Ram Racing CFD.lnk" \
                    "$INSTDIR\${PRODUCT_EXE}" "" "$INSTDIR\${PRODUCT_EXE}" 0
    CreateShortCut  "$SMPROGRAMS\Ram Racing\Uninstall Ram Racing CFD.lnk" \
                    "$INSTDIR\uninstall.exe"
SectionEnd

; =============================================================================
;  Desktop shortcut
; =============================================================================
Section "Desktop shortcut" SEC_DESKTOP
    CreateShortCut "$DESKTOP\Ram Racing CFD.lnk" \
                   "$INSTDIR\${PRODUCT_EXE}" "" "$INSTDIR\${PRODUCT_EXE}" 0
SectionEnd

; =============================================================================
;  Ansys detection (informational only - does not block install)
; =============================================================================
Section "-AnsysCheck"
    DetailPrint "Checking for Ansys Fluent 2026 R1..."

    StrCpy $R1 ""   ; found path

    ; Check AWP_ROOT261 environment variable
    ReadEnvStr $R0 "AWP_ROOT261"
    ${If} $R0 != ""
        ${If} ${FileExists} "$R0\fluent\*.*"
            StrCpy $R1 $R0
        ${EndIf}
    ${EndIf}

    ; Check standard install locations
    ${If} $R1 == ""
        ${If} ${FileExists} "$PROGRAMFILES64\ANSYS Inc\v261\fluent\*.*"
            StrCpy $R1 "$PROGRAMFILES64\ANSYS Inc\v261"
        ${ElseIf} ${FileExists} "C:\Program Files\ANSYS Inc\v261\fluent\*.*"
            StrCpy $R1 "C:\Program Files\ANSYS Inc\v261"
        ${EndIf}
    ${EndIf}

    ${If} $R1 != ""
        DetailPrint "  Found Ansys 2026 R1 at: $R1"
        ; Persist AWP_ROOT261 for all users if not already set
        ReadEnvStr $R2 "AWP_ROOT261"
        ${If} $R2 == ""
            WriteRegExpandStr HKLM \
                "SYSTEM\CurrentControlSet\Control\Session Manager\Environment" \
                "AWP_ROOT261" "$R1"
            DetailPrint "  Set AWP_ROOT261 system environment variable"
            SendMessage ${HWND_BROADCAST} ${WM_WININICHANGE} 0 "STR:Environment" /TIMEOUT=5000
        ${EndIf}
    ${Else}
        DetailPrint "  WARNING: Ansys Fluent 2026 R1 not found"
        MessageBox MB_OK|MB_ICONEXCLAMATION \
            "Ansys Fluent 2026 R1 (v261) was not detected on this system.$\r$\n$\r$\n\
             The application will install successfully, but you must have Ansys$\r$\n\
             Fluent 2026 R1 installed and licensed to run simulations.$\r$\n$\r$\n\
             If Ansys is installed in a non-standard location, set the$\r$\n\
             AWP_ROOT261 environment variable to its install directory:$\r$\n$\r$\n\
             setx AWP_ROOT261 $\"C:\path\to\ANSYS Inc\v261$\" /M"
    ${EndIf}
SectionEnd

; ─── Section descriptions (shown on hover in component page) ─────────────────
!insertmacro MUI_FUNCTION_DESCRIPTION_BEGIN
    !insertmacro MUI_DESCRIPTION_TEXT ${SEC_APP} \
        "The main application and all bundled dependencies. Required."
    !insertmacro MUI_DESCRIPTION_TEXT ${SEC_STARTMENU} \
        "Add shortcuts to the Windows Start Menu."
    !insertmacro MUI_DESCRIPTION_TEXT ${SEC_DESKTOP} \
        "Add a shortcut to the Desktop."
!insertmacro MUI_FUNCTION_DESCRIPTION_END

; =============================================================================
;  Uninstaller
; =============================================================================
Section "Uninstall"
    ; Remove shortcuts
    Delete "$DESKTOP\Ram Racing CFD.lnk"
    Delete "$SMPROGRAMS\Ram Racing\Ram Racing CFD.lnk"
    Delete "$SMPROGRAMS\Ram Racing\Uninstall Ram Racing CFD.lnk"
    RMDir  "$SMPROGRAMS\Ram Racing"

    ; Remove all installed files
    ; RMDir /r removes the whole tree including _internal
    RMDir /r "$INSTDIR"

    ; Clean registry
    DeleteRegKey HKLM "${PRODUCT_UNINST_KEY}"
    DeleteRegKey HKLM "${PRODUCT_DIR_REGKEY}"

    SetAutoClose false
SectionEnd

Function un.onUninstSuccess
    HideWindow
    MessageBox MB_ICONINFORMATION|MB_OK \
        "${PRODUCT_NAME} was successfully removed from your computer."
FunctionEnd

Function un.onInit
    MessageBox MB_ICONQUESTION|MB_YESNO|MB_DEFBUTTON2 \
        "Remove ${PRODUCT_NAME} and all of its components?" \
        IDYES +2
    Abort
FunctionEnd
