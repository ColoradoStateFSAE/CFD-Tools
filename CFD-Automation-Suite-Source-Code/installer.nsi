; =============================================================================
;  Ram Racing CFD Automation Suite - Windows Installer
;  Colorado State University FSAE | Aerodynamics Subteam
;
;  BUILD ORDER MATTERS. Run PyInstaller first:
;
;      pyinstaller --clean RamRacingCFD.spec
;      makensis installer.nsi
;
;  This packages dist\RamRacingCFD\ -- the self-contained PyInstaller bundle,
;  including the editable journals\ folder. Running makensis alone produces an
;  installer containing only .py source files, which cannot run.
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
!define PRODUCT_VERSION    "3.0.0"
!define PRODUCT_PUBLISHER  "Colorado State University FSAE - Ram Racing"
!define PRODUCT_WEB_SITE   "https://github.com/ColoradoStateFSAE/CFD-Tools"
!define PRODUCT_EXE        "RamRacingCFD.exe"
!define PRODUCT_DIR_REGKEY "Software\Microsoft\Windows\CurrentVersion\App Paths\${PRODUCT_EXE}"
!define PRODUCT_UNINST_KEY "Software\Microsoft\Windows\CurrentVersion\Uninstall\${PRODUCT_SHORT}"

!define BUILD_DIR "dist\RamRacingCFD"

Name          "${PRODUCT_NAME}"
OutFile       "RamRacingCFD-Setup.exe"
InstallDir    "$PROGRAMFILES64\Ram Racing\CFD Automation Suite"
InstallDirRegKey HKLM "${PRODUCT_DIR_REGKEY}" ""
RequestExecutionLevel admin
ShowInstDetails   show
ShowUnInstDetails show
SetCompressor /SOLID lzma

VIProductVersion "3.0.0.0"
VIAddVersionKey "ProductName"     "${PRODUCT_NAME}"
VIAddVersionKey "CompanyName"     "${PRODUCT_PUBLISHER}"
VIAddVersionKey "FileDescription" "${PRODUCT_NAME} Installer"
VIAddVersionKey "FileVersion"     "${PRODUCT_VERSION}"
VIAddVersionKey "ProductVersion"  "${PRODUCT_VERSION}"
VIAddVersionKey "LegalCopyright"  "(c) Colorado State University FSAE"

; ─── UI ──────────────────────────────────────────────────────────────────────
!define MUI_ABORTWARNING
!define MUI_ICON   "assets\logo.ico"
!define MUI_UNICON "${NSISDIR}\Contrib\Graphics\Icons\modern-uninstall.ico"

!define MUI_WELCOMEPAGE_TITLE "Ram Racing CFD Automation Suite"
!define MUI_WELCOMEPAGE_TEXT  "This will install the Ram Racing CFD Automation Suite.$\r$\n$\r$\nThe suite automates Ansys Fluent meshing and solving for FSAE aerodynamics by running recorded Fluent journals.$\r$\n$\r$\nRequirements:$\r$\n  - Ansys Fluent 2026 R1 (v261), installed and licensed$\r$\n  - 64-bit Windows 10 or later$\r$\n  - ~500 MB free disk space$\r$\n$\r$\nPython is NOT required; the runtime and all dependencies are bundled.$\r$\n$\r$\nThe journals folder is installed alongside the program so it can be re-recorded after an Ansys upgrade without reinstalling.$\r$\n$\r$\nClick Next to continue."

!define MUI_FINISHPAGE_RUN            "$INSTDIR\${PRODUCT_EXE}"
!define MUI_FINISHPAGE_RUN_TEXT       "Launch Ram Racing CFD now"
!define MUI_FINISHPAGE_SHOWREADME     "$INSTDIR\journals\README.md"
!define MUI_FINISHPAGE_SHOWREADME_TEXT "Open the journals guide"
!define MUI_FINISHPAGE_SHOWREADME_NOTCHECKED
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
;  Pre-install
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
            "A previous version is already installed.$\r$\n$\r$\n\
             Uninstall it first?$\r$\n$\r$\n\
             Your journals folder will be preserved." \
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
    ; Everything except journals — those are handled separately so a
    ; reinstall never overwrites a re-recorded journal.
    File /r /x journals "${BUILD_DIR}\*.*"

    ${IfNot} ${FileExists} "$INSTDIR\${PRODUCT_EXE}"
        MessageBox MB_OK|MB_ICONSTOP \
            "Installation failed: ${PRODUCT_EXE} was not copied.$\r$\n$\r$\n\
             The installer was built without running PyInstaller first."
        Abort
    ${EndIf}

    WriteRegStr HKLM "${PRODUCT_DIR_REGKEY}" "" "$INSTDIR\${PRODUCT_EXE}"
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
;  Journals — editable, preserved across upgrades
; =============================================================================
Section "Fluent journals" SEC_JOURNALS
    SectionIn RO

    ; Never clobber journals the team has re-recorded. Existing files are
    ; left alone; a backup of the shipped set goes in journals\_shipped\ so a
    ; broken edit can be compared against a known-good copy.
    ${If} ${FileExists} "$INSTDIR\journals\*.*"
        DetailPrint "Existing journals found — preserving them"
        SetOutPath "$INSTDIR\journals\_shipped"
        SetOverwrite on
        File /r "${BUILD_DIR}\journals\*.*"
        DetailPrint "Shipped journals copied to journals\_shipped for reference"
    ${Else}
        DetailPrint "Installing journals..."
        SetOutPath "$INSTDIR\journals"
        SetOverwrite on
        File /r "${BUILD_DIR}\journals\*.*"
    ${EndIf}

    ; The journals folder must stay writable for re-recording, but Program
    ; Files is admin-only by default. Grant Users modify rights on it.
    AccessControl::GrantOnFile "$INSTDIR\journals" "(BU)" "FullAccess"
    Pop $0
    ${If} $0 == "error"
        DetailPrint "Note: could not grant write access to journals folder."
        DetailPrint "Re-recording may require running as administrator, or set"
        DetailPrint "RAMRACING_JOURNALS to a folder you can write to."
    ${Else}
        DetailPrint "Journals folder is writable by all users"
    ${EndIf}
SectionEnd

; =============================================================================
;  Shortcuts
; =============================================================================
Section "Start Menu shortcuts" SEC_STARTMENU
    CreateDirectory "$SMPROGRAMS\Ram Racing"
    CreateShortCut  "$SMPROGRAMS\Ram Racing\Ram Racing CFD.lnk" \
                    "$INSTDIR\${PRODUCT_EXE}" "" "$INSTDIR\${PRODUCT_EXE}" 0
    CreateShortCut  "$SMPROGRAMS\Ram Racing\Journals Folder.lnk" \
                    "$INSTDIR\journals"
    CreateShortCut  "$SMPROGRAMS\Ram Racing\Uninstall Ram Racing CFD.lnk" \
                    "$INSTDIR\uninstall.exe"
SectionEnd

Section "Desktop shortcut" SEC_DESKTOP
    CreateShortCut "$DESKTOP\Ram Racing CFD.lnk" \
                   "$INSTDIR\${PRODUCT_EXE}" "" "$INSTDIR\${PRODUCT_EXE}" 0
SectionEnd

; =============================================================================
;  Ansys detection (informational)
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
        DetailPrint "  Found Ansys 2026 R1: $R1"
        ReadEnvStr $R2 "AWP_ROOT261"
        ${If} $R2 == ""
            WriteRegExpandStr HKLM \
                "SYSTEM\CurrentControlSet\Control\Session Manager\Environment" \
                "AWP_ROOT261" "$R1"
            DetailPrint "  AWP_ROOT261 set system-wide"
            SendMessage ${HWND_BROADCAST} ${WM_WININICHANGE} 0 "STR:Environment" /TIMEOUT=5000
        ${EndIf}
    ${Else}
        DetailPrint "  WARNING: Ansys Fluent 2026 R1 not found"
        MessageBox MB_OK|MB_ICONEXCLAMATION \
            "Ansys Fluent 2026 R1 (v261) was not detected.$\r$\n$\r$\n\
             The suite will install, but Fluent must be installed and licensed$\r$\n\
             to mesh or solve.$\r$\n$\r$\n\
             For a non-standard install location:$\r$\n$\r$\n\
             setx AWP_ROOT261 $\"C:\path\to\ANSYS Inc\v261$\" /M"
    ${EndIf}
SectionEnd

!insertmacro MUI_FUNCTION_DESCRIPTION_BEGIN
    !insertmacro MUI_DESCRIPTION_TEXT ${SEC_APP} \
        "The application and all bundled dependencies. Required."
    !insertmacro MUI_DESCRIPTION_TEXT ${SEC_JOURNALS} \
        "Recorded Fluent journals. Installed to a writable folder so they can \
         be re-recorded after an Ansys upgrade. Existing journals are preserved."
    !insertmacro MUI_DESCRIPTION_TEXT ${SEC_STARTMENU} \
        "Start Menu shortcuts, including one to the journals folder."
    !insertmacro MUI_DESCRIPTION_TEXT ${SEC_DESKTOP} \
        "Desktop shortcut."
!insertmacro MUI_FUNCTION_DESCRIPTION_END

; =============================================================================
;  Uninstall
; =============================================================================
Section "Uninstall"
    Delete "$DESKTOP\Ram Racing CFD.lnk"
    Delete "$SMPROGRAMS\Ram Racing\Ram Racing CFD.lnk"
    Delete "$SMPROGRAMS\Ram Racing\Journals Folder.lnk"
    Delete "$SMPROGRAMS\Ram Racing\Uninstall Ram Racing CFD.lnk"
    RMDir  "$SMPROGRAMS\Ram Racing"

    ; Offer to keep journals — they may hold hours of re-recording work
    ${If} ${FileExists} "$INSTDIR\journals\*.*"
        MessageBox MB_YESNO|MB_ICONQUESTION \
            "Keep the journals folder?$\r$\n$\r$\n\
             It contains your recorded Fluent journals, including any you have\
             re-recorded.$\r$\n$\r$\n\
             Yes = keep    No = delete everything" \
            IDNO remove_all

        ; Remove everything except journals
        Delete "$INSTDIR\${PRODUCT_EXE}"
        Delete "$INSTDIR\uninstall.exe"
        RMDir /r "$INSTDIR\_internal"
        RMDir /r "$INSTDIR\assets"
        RMDir /r "$INSTDIR\utils"
        DetailPrint "Journals kept at $INSTDIR\journals"
        Goto cleanup_registry

        remove_all:
        RMDir /r "$INSTDIR"
    ${Else}
        RMDir /r "$INSTDIR"
    ${EndIf}

    cleanup_registry:
    DeleteRegKey HKLM "${PRODUCT_UNINST_KEY}"
    DeleteRegKey HKLM "${PRODUCT_DIR_REGKEY}"

    SetAutoClose false
SectionEnd

Function un.onInit
    MessageBox MB_ICONQUESTION|MB_YESNO|MB_DEFBUTTON2 \
        "Remove ${PRODUCT_NAME} and all of its components?" \
        IDYES +2
    Abort
FunctionEnd

Function un.onUninstSuccess
    HideWindow
    MessageBox MB_ICONINFORMATION|MB_OK \
        "${PRODUCT_NAME} was successfully removed."
FunctionEnd
