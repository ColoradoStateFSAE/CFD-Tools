% Y+ Calculator 
% Made in 2026-2027 Season
% Author: Hayes Dodson

% --- Boundary Conditions ---
p = 1.225; % kg/m^3 (From Ansys)
u_dv = 0.000017894; % Pa*s (From Ansys)
U_inf = input('Enter Free Stream Velocity (m/s): '); % Free Stream Velocity (m/s)
gr = 1.3; % Growth Rate

% --- Lengths ---
L_ch = input('Enter Chassis Length (m): ');
L_fw = input('Enter Front Wing Length (m): ');
L_und = input('Enter Undertray Length (m): ');
L_rw = input('Enter Rear Wing Length (m): ');
L_wheels = 0.406400; % (m)

% --- Componenet Reynolds Numbers ---
Re_ch = (p*U_inf*L_ch)/u_dv; % Chassis Reynolds Number
Re_fw = (p*U_inf*L_fw)/u_dv; % Front Wing Reynolds Number
Re_und = (p*U_inf*L_und)/u_dv; % Undertray Reynolds Number
Re_rw = (p*U_inf*L_rw)/u_dv; % Rear Wing Reynolds Number
Re_wheels = (p*U_inf*L_wheels)/u_dv; % Wheels Reynolds Number

% --- Componenet Skin Friction Coefficients ---
Cf_ch = (2*log10(Re_ch)-0.65)^-2.3; % Chassis Skin Friction Coefficient
Cf_fw = (2*log10(Re_fw)-0.65)^-2.3; % Front Wing Skin Friction Coefficient
Cf_und = (2*log10(Re_und)-0.65)^-2.3; % Undertray Skin Friction Coefficient
Cf_rw = (2*log10(Re_rw)-0.65)^-2.3; % Rear Wing Skin Friction Coefficient
Cf_wheels = (2*log10(Re_wheels)-0.65)^-2.3; % Wheels Skin Friction Coefficient

% --- Component Wall Shear Stress ---
Tw_ch = 0.5*Cf_ch*p*U_inf^2; % Chassis Wall Shear Stress
Tw_fw = 0.5*Cf_fw*p*U_inf^2; % Front Wing Wall Shear Stress
Tw_und = 0.5*Cf_und*p*U_inf^2; % Undertray Wall Shear Stress
Tw_rw = 0.5*Cf_rw*p*U_inf^2; % Rear Wing Wall Shear Stress
Tw_wheels = 0.5*Cf_wheels*p*U_inf^2; % Wheels Wall Shear Stress

% --- Component Friction Velocity @ Wall ---
ut_ch = sqrt(Tw_ch/p); % Chassis Friction Velocity
ut_fw = sqrt(Tw_fw/p); % Front Wing Friction Velocity
ut_und = sqrt(Tw_und/p); % Undertray Friction Velocity
ut_rw = sqrt(Tw_rw/p); % Rear Wing Friction Velocity
ut_wheels = sqrt(Tw_wheels/p); % Wheels Friction Velocity

% --- Total Boundary Layer Thickness ---
s_ch = (0.37*L_ch)/Re_ch^0.2; % Chassis BL Thickness (m)
s_fw = (0.37*L_fw)/Re_fw^0.2; % Front Wing BL Thickness (m)
s_und = (0.37*L_und)/Re_und^0.2; % Undertray BL Thickness (m)
s_rw = (0.37*L_rw)/Re_rw^0.2; % Rear Wing BL Thickness (m)
s_wheels = (0.37*L_wheels)/Re_wheels^0.2; % Wheels BL Thickness (m)

% --- Initial Boundary Layer Height ---
yi_ch = u_dv/(p*ut_ch); % Chassis Initial Boundary Layer Height
yi_fw = u_dv/(p*ut_fw); % Front Wing Initial Boundary Layer Height
yi_und = u_dv/(p*ut_und); % Undertray Initial Boundary Layer Height
yi_rw = u_dv/(p*ut_rw); % Rear Wing Initial Boundary Layer Height
yi_wheels = u_dv/(p*ut_wheels); % Wheels Initial Boundary Layer Height

% --- Number of Layers
N_ch = (log(1+((s_ch*(gr-1))/(2*yi_ch))))/log(gr); % Number of Layers for Chassis
N_fw = (log(1+((s_fw*(gr-1))/(2*yi_fw))))/log(gr); % Number of Layers for Front Wing
N_und = (log(1+((s_und*(gr-1))/(2*yi_und))))/log(gr); % Number of Layers for Undertray
N_rw = (log(1+((s_rw*(gr-1))/(2*yi_rw))))/log(gr); % Number of Layers for Rear Wing
N_wheels = (log(1+((s_wheels*(gr-1))/(2*yi_wheels))))/log(gr); % Number of Layers for Wheels

% ---- OUTPUTS ----
fprintf('\n---- OUTPUTS ----\n');
fprintf('Freestream Velocity (m/s): %.4f\n', U_inf);
fprintf('Growth Rate: %.2f\n', gr);

fprintf('\n--- Chassis ---\n');
fprintf('Initial Height (m): %.4e\n', yi_ch);
fprintf('Number of Layers: %d\n', ceil(N_ch));

fprintf('\n--- Front Wing ---\n');
fprintf('Initial Height (m): %.4e\n', yi_fw);
fprintf('Number of Layers: %d\n', ceil(N_fw));

fprintf('\n--- Undertray ---\n');
fprintf('Initial Height (m): %.4e\n', yi_und);
fprintf('Number of Layers: %d\n', ceil(N_und));

fprintf('\n--- Rear Wing ---\n');
fprintf('Initial Height (m): %.4e\n', yi_rw);
fprintf('Number of Layers: %d\n', ceil(N_rw));

fprintf('\n--- Wheels ---\n');
fprintf('Initial Height (m): %.4e\n', yi_wheels);
fprintf('Number of Layers: %d\n', ceil(N_wheels));