# =============================================================================
#  RPM package for the Ram Racing CFD Automation Suite
#  Rocky Linux 8.x / RHEL 8.x
#
#  Build the bundle first, then the package:
#
#      pyinstaller --clean RamRacingCFD.spec
#
#      sudo dnf install rpm-build rpmdevtools
#      rpmdev-setuptree
#      cp RamRacingCFD.rpm.spec ~/rpmbuild/SPECS/
#      mkdir -p ~/rpmbuild/SOURCES/dist
#      cp -r dist/RamRacingCFD ~/rpmbuild/SOURCES/dist/
#      rpmbuild -bb ~/rpmbuild/SPECS/RamRacingCFD.rpm.spec
#
#  Result: ~/rpmbuild/RPMS/x86_64/RamRacingCFD-4.0.0-1.el8.x86_64.rpm
#      sudo dnf install RamRacingCFD-4.0.0-1.el8.x86_64.rpm
# =============================================================================

Name:           RamRacingCFD
Version:        4.0.0
Release:        1%{?dist}
Summary:        Automated Ansys Fluent CFD for FSAE aerodynamics
License:        Proprietary
URL:            https://github.com/ColoradoStateFSAE/CFD-Tools
BuildArch:      x86_64

# The bundle ships its own Python runtime, so the only runtime dependency is
# the Qt platform library the GUI needs.
Requires:       xcb-util-cursor

# Nothing is compiled here: the PyInstaller output is packaged as-is.
AutoReqProv:    no

%description
Ram Racing CFD Automation Suite.

Automates Ansys Fluent meshing and solving for Formula SAE aerodynamics.
Each simulation type is a self-contained setup covering meshing, solver
configuration, report definitions and result export.

Requires Ansys Fluent 2026 R1 (v261), installed and licensed separately.
Python is not required; the runtime and all dependencies are bundled.

%install
rm -rf %{buildroot}
mkdir -p %{buildroot}/opt/RamRacingCFD

# Trailing /. copies the directory contents. A shell glob does not expand
# inside rpmbuild's restricted shell.
cp -r %{_sourcedir}/dist/RamRacingCFD/. %{buildroot}/opt/RamRacingCFD/

# ── Launcher ─────────────────────────────────────────────────────────────────
mkdir -p %{buildroot}/usr/local/bin
cat > %{buildroot}/usr/local/bin/ramracingcfd << 'LAUNCHEOF'
#!/bin/bash
# Ram Racing CFD launcher. Locates Ansys Fluent 2026 R1 if AWP_ROOT261 is unset.
if [ -z "$AWP_ROOT261" ]; then
    for candidate in \
        "$HOME/ansys_inc/v261" \
        "/ansys_inc/v261" \
        "/usr/ansys_inc/v261"; do
        if [ -d "$candidate" ]; then
            export AWP_ROOT261="$candidate"
            break
        fi
    done
fi

if [ -z "$AWP_ROOT261" ]; then
    echo "WARNING: Ansys Fluent 2026 R1 not found."
    echo "Set AWP_ROOT261 before running a simulation."
fi

exec /opt/RamRacingCFD/RamRacingCFD "$@"
LAUNCHEOF
chmod 755 %{buildroot}/usr/local/bin/ramracingcfd

# ── Desktop entry ────────────────────────────────────────────────────────────
mkdir -p %{buildroot}/usr/share/applications
cat > %{buildroot}/usr/share/applications/RamRacingCFD.desktop << 'DESKTOPEOF'
[Desktop Entry]
Name=Ram Racing CFD
Comment=Automated Ansys Fluent CFD for FSAE aerodynamics
Exec=/usr/local/bin/ramracingcfd
Icon=/opt/RamRacingCFD/assets/logo.png
Terminal=false
Type=Application
Categories=Science;Engineering;
StartupNotify=true
DESKTOPEOF

%files
%dir /opt/RamRacingCFD
/opt/RamRacingCFD/*
/usr/local/bin/ramracingcfd
/usr/share/applications/RamRacingCFD.desktop

%post
echo "Ram Racing CFD Automation Suite installed to /opt/RamRacingCFD"
echo "Run with:  ramracingcfd"
echo
if [ -z "$AWP_ROOT261" ] && [ ! -d /ansys_inc/v261 ]; then
    echo "NOTE: Ansys Fluent 2026 R1 was not detected."
    echo "      Set AWP_ROOT261 before running a simulation."
fi

%postun
if [ $1 -eq 0 ]; then
    echo "Ram Racing CFD Automation Suite removed."
    echo "Simulation output folders were not touched."
fi

%changelog
* Fri Jul 31 2026 Ram Racing Aero <aero@ramracing.colostate.edu> - 4.0.0-1
- Restructured: each simulation type is now one self-contained file
- Three stage solver ramp, curvature correction on the final stage
- SCz, SCx and centre of pressure evaluated as Fluent expressions
- Named Selections and Report Definitions reference tabs in the GUI
- Wheels modelled as rotating walls with editable axle origins
- Targets Ansys Fluent 2026 R1 (v261) and PyFluent 0.39
