Name:           RamRacingCFD
Version:        1.0.0
Release:        1%{?dist}
Summary:        Ram Racing CFD Automation Suite
License:        Proprietary
BuildArch:      x86_64

# No build dependencies — we install the pre-built PyInstaller bundle
# Build on Rocky Linux 8.x, run on Rocky Linux 8.x

%description
Ram Racing CFD Automation Suite.
Automates Ansys Fluent meshing and solving workflows for Formula SAE aerodynamics.
Requires Ansys Fluent 2025 R2 (v252) installed at /home/<user>/ansys_inc/v252
or accessible via AWP_ROOT252.

%install
mkdir -p %{buildroot}/opt/RamRacingCFD
# Copy the PyInstaller bundle (built separately)
cp -r %{_sourcedir}/dist/RamRacingCFD/* %{buildroot}/opt/RamRacingCFD/

# Desktop launcher script
mkdir -p %{buildroot}/usr/local/bin
cat > %{buildroot}/usr/local/bin/ramracingcfd << 'EOF'
#!/bin/bash
# Ram Racing CFD launcher
# Requires AWP_ROOT252 to be set or Ansys installed at default location
if [ -z "$AWP_ROOT252" ]; then
    if [ -d "$HOME/ansys_inc/v252" ]; then
        export AWP_ROOT252="$HOME/ansys_inc/v252"
    elif [ -d "/ansys_inc/v252" ]; then
        export AWP_ROOT252="/ansys_inc/v252"
    else
        echo "ERROR: AWP_ROOT252 not set and Ansys v252 not found."
        echo "Set AWP_ROOT252 to your Ansys 2025 R2 installation directory."
        exit 1
    fi
fi
exec /opt/RamRacingCFD/RamRacingCFD "$@"
EOF
chmod 755 %{buildroot}/usr/local/bin/ramracingcfd

# .desktop file for application menu
mkdir -p %{buildroot}/usr/share/applications
cat > %{buildroot}/usr/share/applications/RamRacingCFD.desktop << 'EOF'
[Desktop Entry]
Name=Ram Racing CFD
Comment=CFD Automation Suite for Ansys Fluent
Exec=ramracingcfd
Icon=/opt/RamRacingCFD/assets/logo.png
Terminal=false
Type=Application
Categories=Science;Engineering;
EOF

%files
/opt/RamRacingCFD/
/usr/local/bin/ramracingcfd
/usr/share/applications/RamRacingCFD.desktop

%post
echo "Ram Racing CFD installed to /opt/RamRacingCFD"
echo "Run with: ramracingcfd"
echo "Requires Ansys Fluent 2025 R2 (v252). Set AWP_ROOT252 if not in default location."

%preun
# Nothing to do before uninstall

%postun
echo "Ram Racing CFD uninstalled."
