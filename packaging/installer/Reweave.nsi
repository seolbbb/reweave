Unicode true
RequestExecutionLevel user
!include "${BUILD_CONFIG}"
!include "MUI2.nsh"
!include "FileFunc.nsh"

Name "Reweave ${VERSION}"
OutFile "${OUTPUT}"
InstallDir "$LOCALAPPDATA\Programs\Reweave"
SetCompressor /SOLID lzma
SetCompressorDictSize 64
ShowInstDetails show
ShowUninstDetails show
BrandingText "Reweave - local conversation context"

Var Isolated
Var Workspace
Var Parameters

!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_LICENSE "${PRODUCT_LICENSE}"
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_LANGUAGE "English"

!macro ParseMode
    SetShellVarContext current
    StrCpy $Isolated "0"
    StrCpy $Workspace ""
    ${GetParameters} $Parameters
    ClearErrors
    ${GetOptions} $Parameters "/ISOLATED" $0
    IfErrors +2
        StrCpy $Isolated "1"
    ${GetOptions} $Parameters "/WORKSPACE=" $Workspace
!macroend

Function .onInit
    !insertmacro ParseMode
FunctionEnd

Function un.onInit
    !insertmacro ParseMode
FunctionEnd

Section "Reweave" SEC_MAIN
    InitPluginsDir
    SetOutPath "$PLUGINSDIR\payload"
    File /r "${PAYLOAD}\*"
    WriteUninstaller "$PLUGINSDIR\payload\Uninstall.exe"
    SetOutPath "$PLUGINSDIR"
    File /oname=lifecycle.ps1 "${LIFECYCLE}"
    nsExec::ExecToStack /TIMEOUT=600000 '"$SYSDIR\WindowsPowerShell\v1.0\powershell.exe" -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "$PLUGINSDIR\lifecycle.ps1" -Operation Install -InstallRoot "$INSTDIR" -PayloadRoot "$PLUGINSDIR\payload" -Isolated "$Isolated" -WorkspaceRoot "$Workspace"'
    Pop $0
    Pop $1
    DetailPrint "$1"
    StrCmp $0 "0" installed
        SetErrorLevel 1
        Abort "Installation stopped. Review the details above."
    installed:
SectionEnd

Section "Uninstall"
    InitPluginsDir
    SetOutPath "$PLUGINSDIR"
    File /oname=lifecycle.ps1 "${LIFECYCLE}"
    nsExec::ExecToStack /TIMEOUT=600000 '"$SYSDIR\WindowsPowerShell\v1.0\powershell.exe" -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "$PLUGINSDIR\lifecycle.ps1" -Operation Uninstall -InstallRoot "$INSTDIR" -Isolated "$Isolated" -WorkspaceRoot "$Workspace"'
    Pop $0
    Pop $1
    DetailPrint "$1"
    StrCmp $0 "0" removed
        SetErrorLevel 1
        Abort "Uninstallation stopped. Review the details above."
    removed:
SectionEnd
