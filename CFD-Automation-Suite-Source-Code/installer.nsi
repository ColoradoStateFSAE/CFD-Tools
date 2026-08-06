; =============================================================================
;  Ram Racing CFD Automation Suite -- Windows Installer
;  Colorado State University FSAE | Aerodynamics Subteam
;
;  BUILD ORDER MATTERS. PyInstaller must run first:
;
;      pyinstaller --clean RamRacingCFD.spec
;      makensis installer.nsi
;
;  This packages dist\RamRacingCFD\ -- the self-contained bundle. Running
;  makensis on its own produces an installer holding only .py source files,
;  which cannot run without Python.
;
;  Output: RamRacingCFD-Setup.exe
; =============================================================================

Unicode True

!include "MUI2.nsh"
!include "LogicLib.nsh"
!include "FileFunc.nsh"
!include "x64.nsh"

!define PRODUCT_NAME       "Ram Racing CFD Automation Suite"
!define PRODUCT_SHORT      "RamRacingCFD"
!define PRODUCT_VERSION    "4.0.0"
!define PRODUCT_PUBLISHER  "Colorado State University FSAE - Ram Racing"
!define PRODUCT_WEB_SITE   "https://github.com/ColoradoStateFSAE/CFD-Tools"
!define PRODUCT_EXE        "RamRacingCFD.exe"
!define PRODUCT_DIR_REGKEY "Software\Microsoft\Windows\CurrentVersion\App Paths\${PRODUCT_EXE}"
!define PRODUCT_UNINST_KEY "Software\Microsoft\Windows\CurrentVersion\Uninstall\${PRODUCT_SHORT}"

!define BUILD_DIR "dist\RamRacingCFD"

Name             "${PRODUCT_NAME}"
OutFile          "RamRacingCFD-Setup.exe"
InstallDir       "$PROGRAMFILES64\Ram Racing\CFD Automation Suite"
InstallDirRegKey HKLM "${PRODUCT_DIR_REGKEY}" ""
RequestExecutionLevel admin
ShowInstDetails   show
ShowUnInstDetails show
SetCompressor /SOLID lzma

VIProductVersion "4.0.0.0"
VIAddVersionKey "ProductName"     "${PRODUCT_NAME}"
VIAddVersionKey "CompanyName"     "${PRODUCT_PUBLISHER}"
VIAddVersionKey "FileDescription" "${PRODUCT_NAME} Installer"
VIAddVersionKey "FileVersion"     "${PRODUCT_VERSION}"
VIAddVersionKey "ProductVersion"  "${PRODUCT_VERSION}"
VIAddVersionKey "LegalCopyright"  "(c) Colorado State University FSAE"

; ── Interface ────────────────────────────────────────────────────────────────
!define MUI_ABORTWARNING
!define MUI_ICON   "assets\logo.ico"
!define MUI_UNICON "${NSISDIR}\Contrib\Graphics\Icons\modern-uninstall.ico"

!define MUI_WELCOMEPAGE_TITLE "Ram Racing CFD Automation Suite"
!define MUI_WELCOMEPAGE_TEXT  "This will install the Ram Racing CFD Automation Suite.$\r$\n$\r$\nThe suite automates Ansys Fluent meshing and solving for FSAE aerodynamics.$\r$\n$\r$\nRequirements:$\r$\n  - Ansys Fluent 2026 R1 (v261), installed and licensed$\r$\n  - 64-bit Windows 10 or later$\r$\n  - About 500 MB of free disk space$\r$\n$\r$\nPython is NOT required. The runtime and every dependency are bundled.$\r$\n$\r$\nClick Next to continue."

!define MUI_FINISHPAGE_RUN            "$INSTDIR\${PRODUCT_EXE}"
!define MUI_FINISHPAGE_RUN_TEXT       "Launch Ram Racing CFD now"
!define MUI_FINISHPAGE_LINK           "CFD-Tools on GitHub"
!define MUI_FINISHPAGE_LINK_LOCATION  "${PRODUCT_WEB_SITE}"

!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_COMPONENTS
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH

!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES

!insertmacro MUI_LANGUAGE "English"

; =============================================================================
;  Pre-install checks
; =============================================================================
Function .onInit
    ${IfNot} ${RunningX64}
        MessageBox MB_OK|MB_ICONSTOP \
            "This application requires 64-bit Windows.$\r$\n$\r$\nInstallation cannot continue."
        Abort
    ${EndIf}

    ReadRegStr $R0 HKLM "${PRODUCT_UNINST_KEY}" "UninstallString"
    ${If} $R0 != ""
        MessageBox MB_YESNO|MB_ICONQUESTION \
            "A previous version is already installed.$\r$\n$\r$\nUninstall it first?" \
            IDNO skip_uninstall
        ExecWait '$R0 /S _?=$INSTDIR'
        skip_uninstall:
    ${EndIf}
FunctionEnd

; =============================================================================
;  Application
; =============================================================================
Section "Application (required)" SEC_APP
    SectionIn RO

    SetOutPath "$INSTDIR"
    SetOverwrite try

    DetailPrint "Installing application files..."
    File /r "${BUILD_DIR}\*.*"

    ${IfNot} ${FileExists} "$INSTDIR\${PRODUCT_EXE}"
        MessageBox MB_OK|MB_ICONSTOP \
            "Installation failed: ${PRODUCT_EXE} is missing.$\r$\n$\r$\n\
             The installer was built without running PyInstaller first."
        Abort
    ${EndIf}

    WriteRegStr HKLM "${PRODUCT_DIR_REGKEY}" ""     "$INSTDIR\${PRODUCT_EXE}"
    WriteRegStr HKLM "${PRODUCT_DIR_REGKEY}" "Path" "$INSTDIR"

    WriteRegStr HKLM "${PRODUCT_UNINST_KEY}" "DisplayName"     "${PRODUCT_NAME}"
    WriteRegStr HKLM "${PRODUCT_UNINST_KEY}" "DisplayVersion"  "${PRODUCT_VERSION}"
    WriteRegStr HKLM "${PRODUCT_UNINST_KEY}" "Publisher"       "${PRODUCT_PUBLISHER}"
    WriteRegStr HKLM "${PRODUCT_UNINST_KEY}" "URLInfoAbout"    "${PRODUCT_WEB_SITE}"
    WriteRegStr HKLM "${PRODUCT_UNINST_KEY}" "DisplayIcon"     "$INSTDIR\${PRODUCT_EXE}"
    WriteRegStr HKLM "${PRODUCT_UNINST_KEY}" "UninstallString" "$INSTDIR\uninstall.exe"
    WriteRegStr HKLM "${PRODUCT_UNINST_KEY}" "InstallLocation" "$INSTDIR"
    WriteRegDWORD HKLM "${PRODUCT_UNINST_KEY}" "NoModify" 1
    WriteRegDWORD HKLM "${PRODUCT_UNINST_KEY}" "NoRepair" 1

    ${GetSize} "$INSTDIR" "/S=0K" $0 $1 $2
    IntFmt $0 "0x%08X" $0
    WriteRegDWORD HKLM "${PRODUCT_UNINST_KEY}" "EstimatedSize" "$0"

    WriteUninstaller "$INSTDIR\uninstall.exe"
SectionEnd

; =============================================================================
;  Shortcuts
; =============================================================================
Section "Start Menu shortcuts" SEC_STARTMENU
    CreateDirectory "$SMPROGRAMS\Ram Racing"
    CreateShortCut  "$SMPROGRAMS\Ram Racing\Ram Racing CFD.lnk" \
                    "$INSTDIR\${PRODUCT_EXE}" "" "$INSTDIR\${PRODUCT_EXE}" 0
    CreateShortCut  "$SMPROGRAMS\Ram Racing\Uninstall Ram Racing CFD.lnk" \
                    "$INSTDIR\uninstall.exe"
SectionEnd

Section "Desktop shortcut" SEC_DESKTOP
    CreateShortCut "$DESKTOP\Ram Racing CFD.lnk" \
                   "$INSTDIR\${PRODUCT_EXE}" "" "$INSTDIR\${PRODUCT_EXE}" 0
SectionEnd

; =============================================================================
;  Ansys detection -- informational, never blocks the install
; =============================================================================
Section "-AnsysCheck"
    DetailPrint "Checking for Ansys Fluent 2026 R1..."
    StrCpy $R1 ""

    ReadEnvStr $R0 "AWP_ROOT261"
    ${If} $R0 != ""
    ${AndIf} ${FileExists} "$R0\fluent\*.*"
        StrCpy $R1 $R0
    ${EndIf}

    ${If} $R1 == ""
        ${If} ${FileExists} "$PROGRAMFILES64\ANSYS Inc\v261\fluent\*.*"
            StrCpy $R1 "$PROGRAMFILES64\ANSYS Inc\v261"
        ${ElseIf} ${FileExists} "C:\Program Files\ANSYS Inc\v261\fluent\*.*"
            StrCpy $R1 "C:\Program Files\ANSYS Inc\v261"
        ${EndIf}
    ${EndIf}

    ${If} $R1 != ""
        DetailPrint "  Found: $R1"
        ReadEnvStr $R2 "AWP_ROOT261"
        ${If} $R2 == ""
            WriteRegExpandStr HKLM \
                "SYSTEM\CurrentControlSet\Control\Session Manager\Environment" \
                "AWP_ROOT261" "$R1"
            DetailPrint "  AWP_ROOT261 set system-wide"
            SendMessage ${HWND_BROADCAST} ${WM_WININICHANGE} 0 "STR:Environment" /TIMEOUT=5000
        ${EndIf}
    ${Else}
        DetailPrint "  WARNING: Ansys Fluent 2026 R1 was not found"
        MessageBox MB_OK|MB_ICONEXCLAMATION \
            "Ansys Fluent 2026 R1 (v261) was not detected.$\r$\n$\r$\n\
             The suite will install, but Fluent must be installed and licensed$\r$\n\
             before a simulation can run.$\r$\n$\r$\n\
             For a non-standard location:$\r$\n$\r$\n\
             setx AWP_ROOT261 $\"C:\path\to\ANSYS Inc\v261$\" /M"
    ${EndIf}
SectionEnd

!insertmacro MUI_FUNCTION_DESCRIPTION_BEGIN
    !insertmacro MUI_DESCRIPTION_TEXT ${SEC_APP} \
        "The application and all bundled dependencies. Required."
    !insertmacro MUI_DESCRIPTION_TEXT ${SEC_STARTMENU} \
        "Add shortcuts to the Windows Start Menu."
    !insertmacro MUI_DESCRIPTION_TEXT ${SEC_DESKTOP} \
        "Add a shortcut to the Desktop."
!insertmacro MUI_FUNCTION_DESCRIPTION_END

; =============================================================================
;  Uninstall
; =============================================================================
Section "Uninstall"
    Delete "$DESKTOP\Ram Racing CFD.lnk"
    Delete "$SMPROGRAMS\Ram Racing\Ram Racing CFD.lnk"
    Delete "$SMPROGRAMS\Ram Racing\Uninstall Ram Racing CFD.lnk"
    RMDir  "$SMPROGRAMS\Ram Racing"

    RMDir /r "$INSTDIR"

    DeleteRegKey HKLM "${PRODUCT_UNINST_KEY}"
    DeleteRegKey HKLM "${PRODUCT_DIR_REGKEY}"

    SetAutoClose false
SectionEnd

Function un.onInit
    MessageBox MB_ICONQUESTION|MB_YESNO|MB_DEFBUTTON2 \
        "Remove ${PRODUCT_NAME} and all of its components?$\r$\n$\r$\n\
         Simulation output folders are not touched." \
        IDYES +2
    Abort
FunctionEnd

Function un.onUninstSuccess
    HideWindow
    MessageBox MB_ICONINFORMATION|MB_OK \
        "${PRODUCT_NAME} was successfully removed."
FunctionEnd
