%% ============================================================
%  FSAE Steady-State Cornering CFD Geometry Calculator
%  Reference: Nayman & Penny – "Developing Steady-State
%             Cornering CFD Simulations for Use in FSAE"
%             (Siemens / Queen's Formula SAE)
%
%  Ported methodology to Ansys Fluent conventions.
%  All lengths in metres, angles in radians (and degrees),
%  speeds in m/s, rotation rates in rad/s.
% ============================================================

clc; clear; close all;

fprintf('============================================================\n');
fprintf('   FSAE Cornering CFD Geometry & Physics Parameter Calc\n');
fprintf('============================================================\n\n');

%% ---- 1. USER INPUTS ----------------------------------------

fprintf('--- Car Parameters ---\n');
wheelbase  = input('  Wheelbase (m)                        [e.g. 1.55]: ');
cgx        = input('  CGX: weight fraction on REAR axle    [e.g. 0.49]: ');
track_f    = input('  Front track width (m)                [e.g. 1.20]: ');
track_r    = input('  Rear  track width (m)                [e.g. 1.15]: ');
tire_rad   = input('  Tire radius (m)                      [e.g. 0.2286]: ');
h_f        = input('  Front axle height from ground (m)   [e.g. 0.2286]: ');
h_r        = input('  Rear  axle height from ground (m)   [e.g. 0.2286]: ');

fprintf('\n--- Corner Parameters ---\n');
R          = input('  Corner radius at CoG (m)             [e.g. 8.375]: ');
a_lat_g    = input('  Target lateral acceleration (g''s)   [e.g. 1.1]:   ');
yaw_deg    = input('  Car yaw angle (deg, 0 = no yaw)      [e.g. 0]:     ');

fprintf('\n--- Domain Parameters ---\n');
OR         = input('  Outer domain radius (m)              [e.g. 50]:    ');
IAW        = input('  InletAngleWheelbase  (# wheelbases)  [e.g. 9]:     ');
OAW        = input('  OutletAngleWheelbase (# wheelbases)  [e.g. 18]:    ');
dom_height = input('  Domain height (m)                    [e.g. 16]:    ');

%% ---- 2. DERIVED PHYSICAL CONSTANTS -------------------------

g      = 9.81;                        % m/s^2
a_c    = a_lat_g * g;                 % lateral acceleration (m/s^2)
yaw    = deg2rad(yaw_deg);            % yaw in radians

%% ---- 3. VELOCITIES & ROTATION RATES ------------------------

% Tangential speed at CoG  (from a_c = v^2 / R)
VMag        = sqrt(a_c * R);

% Domain (MRF) rotation rate  omega = v / R
Domain_Rot  = VMag / R;

% Steering angle (geometric Ackermann, left turn positive)
% delta = arctan(l / R)
delta_rad   = atan(wheelbase / R);
delta_deg   = rad2deg(delta_rad);

% Centre of Gravity location along wheelbase
CG = cgx * wheelbase;                 % distance from FRONT axle to CoG

%% ---- 4. TIRE RADIAL DISTANCES FROM CoR ---------------------
% The Centre of Rotation (CoR) is at (CG, -R, 0) in lab coords.
% Each tire position in the lab frame (x = rearward positive,
% y = lateral, z = up):
%
%   FL: x =  0         (front axle)  y = +track_f/2
%   FR: x =  0                        y = -track_f/2
%   RL: x = -wheelbase (rear axle)   y = +track_r/2
%   RR: x = -wheelbase               y = -track_r/2
%
% CoR is at (CG, -R, 0)  so relative positions:

% Tire x-offsets from CoR  (positive = rearward)
dx_F = 0        - CG;          % front axle relative to CoR (x)
dx_R = -wheelbase - CG;        % rear  axle relative to CoR (x)  [= -wheelbase-CG, negative]

% Actually the paper places the lab origin at the FRONT axle centre.
% CoR_x = CG  (distance behind front axle)
% So relative positions:
%   FL: (0 - CG, +track_f/2 - (-R)) = (-CG,  track_f/2 + R)
%   FR: (-CG, -track_f/2 + R)  ... etc.
% Simplify with signed convention used in the paper:

FL_x_rel = -CG;                FL_y_rel =  track_f/2 + R;
FR_x_rel = -CG;                FR_y_rel = -track_f/2 + R;
RL_x_rel = -(wheelbase + CG);  RL_y_rel =  track_r/2 + R;
RR_x_rel = -(wheelbase + CG);  RR_y_rel = -track_r/2 + R;

FL_Rad = sqrt(FL_x_rel^2 + FL_y_rel^2);
FR_Rad = sqrt(FR_x_rel^2 + FR_y_rel^2);
RL_Rad = sqrt(RL_x_rel^2 + RL_y_rel^2);
RR_Rad = sqrt(RR_x_rel^2 + RR_y_rel^2);

% Tire rotation rates  omega_tire = sqrt(a_c * tire_R) / tire_radius
%   (tangential speed at each tire hub / tire radius)
Omega_FL = sqrt(a_c * FL_Rad) / tire_rad;
Omega_FR = sqrt(a_c * FR_Rad) / tire_rad;
Omega_RL = sqrt(a_c * RL_Rad) / tire_rad;
Omega_RR = sqrt(a_c * RR_Rad) / tire_rad;

%% ---- 5. DOMAIN GEOMETRY (PIE-SHAPED DOMAIN) ----------------

% Inlet arc half-angle from CoG
inlet_angle_rad  = IAW * wheelbase / R;
inlet_angle_deg  = rad2deg(inlet_angle_rad);

% Outlet angle definition (see paper, uses 45-deg offset from CoG)
outlet_angle_rad = OAW * wheelbase / R - pi/4;
outlet_angle_deg = rad2deg(outlet_angle_rad);

% Domain centre coordinates (in lab frame)
%   Centre of the pie = CoR = (CG, -R, 0)
CoR_x = CG;
CoR_y = -R;
CoR_z = 0;

%% ---- 6. WAKE REFINEMENT BLOCK GEOMETRY ---------------------
% Three levels of refinement, lofted volumes.
% Width: 2.5 m (start) → 6 m (outlet)
% Height: 2.5 m (start) → 4.5 m (outlet)

WB = wheelbase;  % abbreviation

% Section angles from CoG (in radians from line CoR→CoG)
sec1_angle = 0.45 * WB/R;
sec2_angle = sec1_angle + 4 * WB/R;
sec3_angle = sec2_angle + 4 * WB/R;  % cumulative angle to sec3 start
sec4_angle = sec3_angle + 4 * WB/R;
sec5_angle = sec4_angle + 0.25 * OAW * WB/R;
sec6_angle = sec5_angle + (0.5*OAW - 8.95) * WB/R;   % = OAW*WB/R - pi/4 (outlet)

% Width at each section (from Table 1)
W1 = 2.5;
W2 = 2.5 + 3.5/(OAW - 0.45) * 4;
W3 = 2.5 + 3.5/(OAW - 0.45) * 8.5;
W4 = 2.5 + 3.5/(OAW - 0.45) * (8.5 + 0.25*OAW);
W5 = 2.5 + 3.5/(OAW - 0.45) * (8.5 + 0.5*OAW) * 4;  % note: *4 from paper
W6 = 6.0;

% Height at each section
H1 = 2.0;
H2 = 2.0 + 2.5/(OAW - 0.45) * 4;
H3 = 2.0 + 2.5/(OAW - 0.45) * 8.5;
H4 = 2.0 + 2.5/(OAW - 0.45) * (8.5 + 0.25*OAW);
H5 = 2.0 + 2.5/(OAW - 0.45) * (8.5 + 0.5*OAW);
H6 = 4.5;

%% ---- 7. TIRE COORDINATE SYSTEM ORIGINS ---------------------
% Front-right origin (from paper): [cgx*l - h_F*cos(Phi_FR),  h_F*sin(Phi_FR),  R_FR]
% For a flat car (zero camber/roll baseline), Phi_FR = 0:
%   Origin_FR = [CG, 0, h_f]  (simplified, zero camber)
% For a full derivation the Java macro is needed; the expressions below
% give the baseline origins (zero camber, zero toe, zero roll).

Phi_FR = 0;   % camber angle for FR tire (rad) – set to zero for baseline
Phi_FL = 0;
Phi_RR = 0;
Phi_RL = 0;

FR_origin = [CG - h_f*cos(Phi_FR),  h_f*sin(Phi_FR),  tire_rad];
FL_origin = [CG - h_f*cos(Phi_FL), -h_f*sin(Phi_FL),  tire_rad];
RR_origin = [-(wheelbase - CG) - h_r*cos(Phi_RR),  h_r*sin(Phi_RR),  tire_rad];
RL_origin = [-(wheelbase - CG) - h_r*cos(Phi_RL), -h_r*sin(Phi_RL),  tire_rad];

% COR coordinate system origin
COR_origin = [CG, -R, 0];

%% ---- 8. FLUENT-SPECIFIC BOUNDARY CONDITIONS ----------------
% Fluent uses rad/s for rotation, m/s for wall velocities.
% MRF frame: rotation axis = +Z, rotation rate = Domain_Rot (rad/s)
% Inlet: velocity-inlet at 0 m/s (fluid moved by MRF, not inlet)
% Outlet: pressure-outlet at 0 Pa gauge
% Ground: no-slip wall, stationary in lab frame (no tangential velocity)
% Top / side walls: slip walls (or symmetry)

%% ---- 9. PRINT RESULTS --------------------------------------

fprintf('\n============================================================\n');
fprintf('              COMPUTED PARAMETERS\n');
fprintf('============================================================\n\n');

fprintf('--- Core Physics ---\n');
fprintf('  Lateral acceleration       a_c        = %.4f  m/s^2\n', a_c);
fprintf('  CoG tangential speed       VMag        = %.4f  m/s\n',  VMag);
fprintf('  Domain MRF rotation rate   Domain_Rot  = %.6f rad/s\n', Domain_Rot);
fprintf('  Geometric steering angle   delta       = %.4f  deg  (%.6f rad)\n', delta_deg, delta_rad);
fprintf('  Car yaw angle                          = %.4f  deg\n\n', yaw_deg);

fprintf('--- Tire Radii from CoR ---\n');
fprintf('  FL_Rad = %.6f m\n', FL_Rad);
fprintf('  FR_Rad = %.6f m\n', FR_Rad);
fprintf('  RL_Rad = %.6f m\n', RL_Rad);
fprintf('  RR_Rad = %.6f m\n\n', RR_Rad);

fprintf('--- Tire Rotation Rates (rad/s, about each tire Z-axis) ---\n');
fprintf('  Omega_FL = %.6f rad/s\n', Omega_FL);
fprintf('  Omega_FR = %.6f rad/s\n', Omega_FR);
fprintf('  Omega_RL = %.6f rad/s\n', Omega_RL);
fprintf('  Omega_RR = %.6f rad/s\n\n', Omega_RR);

fprintf('--- Domain Geometry ---\n');
fprintf('  Centre of Rotation (CoR) in lab frame:\n');
fprintf('    CoR_x = %.6f m\n', CoR_x);
fprintf('    CoR_y = %.6f m\n', CoR_y);
fprintf('    CoR_z = %.6f m\n', CoR_z);
fprintf('  Corner radius (at CoG)     R           = %.4f  m\n', R);
fprintf('  Outer domain radius        OR          = %.4f  m\n', OR);
fprintf('  Domain height                          = %.4f  m\n', dom_height);
fprintf('  Inlet half-angle                       = %.4f  deg  (%.6f rad)\n', inlet_angle_deg, inlet_angle_rad);
fprintf('  Outlet half-angle (from 45-deg ref)    = %.4f  deg  (%.6f rad)\n', outlet_angle_deg, outlet_angle_rad);
fprintf('  Total pie sweep angle                  = %.4f  deg\n\n', inlet_angle_deg + outlet_angle_deg);

fprintf('--- Wake Refinement Block Cross-Sections (Table 1) ---\n');
fprintf('  %-8s  %-12s  %-12s  %-22s\n','Section','Width (m)','Height (m)','Cumul. angle from CoG (rad)');
fprintf('  %-8d  %-12.4f  %-12.4f  %-22.6f\n', 1, W1, H1, sec1_angle);
fprintf('  %-8d  %-12.4f  %-12.4f  %-22.6f\n', 2, W2, H2, sec2_angle);
fprintf('  %-8d  %-12.4f  %-12.4f  %-22.6f\n', 3, W3, H3, sec3_angle);
fprintf('  %-8d  %-12.4f  %-12.4f  %-22.6f\n', 4, W4, H4, sec4_angle);
fprintf('  %-8d  %-12.4f  %-12.4f  %-22.6f\n', 5, W5, H5, sec5_angle);
fprintf('  %-8d  %-12.4f  %-12.4f  %-22.6f\n\n', 6, W6, H6, sec6_angle);

fprintf('--- Tire Coordinate System Origins (lab frame, zero camber baseline) ---\n');
fprintf('  FL: [%.6f, %.6f, %.6f]\n', FL_origin(1), FL_origin(2), FL_origin(3));
fprintf('  FR: [%.6f, %.6f, %.6f]\n', FR_origin(1), FR_origin(2), FR_origin(3));
fprintf('  RL: [%.6f, %.6f, %.6f]\n', RL_origin(1), RL_origin(2), RL_origin(3));
fprintf('  RR: [%.6f, %.6f, %.6f]\n\n', RR_origin(1), RR_origin(2), RR_origin(3));

fprintf('--- Ansys Fluent Boundary Condition Summary ---\n');
fprintf('  Inlet   (velocity-inlet)   : 0 m/s (fluid motion from MRF)\n');
fprintf('  Outlet  (pressure-outlet)  : 0 Pa gauge\n');
fprintf('  Ground  (wall, no-slip)    : stationary in LAB frame\n');
fprintf('  Top/Side walls             : slip wall (or symmetry)\n');
fprintf('  Car surfaces               : stationary in ROTATING frame\n');
fprintf('  MRF Zone                   : rotation axis = +Z\n');
fprintf('                               rotation rate  = %.6f rad/s\n', Domain_Rot);
fprintf('  FL wall rotation rate      : %.6f rad/s about tire Z-axis\n', Omega_FL);
fprintf('  FR wall rotation rate      : %.6f rad/s about tire Z-axis\n', Omega_FR);
fprintf('  RL wall rotation rate      : %.6f rad/s about tire Z-axis\n', Omega_RL);
fprintf('  RR wall rotation rate      : %.6f rad/s about tire Z-axis\n\n', Omega_RR);

fprintf('--- Normalization for Coefficient Reports ---\n');
fprintf('  Reference velocity  VMag   = %.6f m/s\n',    VMag);
fprintf('  Cp = (P - P_ref) / (0.5 * rho * VMag^2)\n');
fprintf('  (Enter VMag as freestream speed in Fluent reference values)\n\n');

fprintf('============================================================\n');
fprintf('  All outputs above should be entered into Ansys Fluent.\n');
fprintf('  Coordinate convention: X = rearward, Y = left, Z = up.\n');
fprintf('  Verify sign convention matches your imported CAD.\n');
fprintf('============================================================\n');

%% ---- 10. OPTIONAL: SAVE TO TEXT FILE -----------------------
save_flag = input('\nSave results to a text file? (1 = yes, 0 = no): ');
if save_flag
    fname = 'cornering_params_output.txt';
    fid   = fopen(fname, 'w');
    fprintf(fid, 'FSAE Cornering CFD Parameters\n');
    fprintf(fid, 'Generated: %s\n\n', datestr(now));
    fprintf(fid, '--- Inputs ---\n');
    fprintf(fid, 'Wheelbase        = %.4f m\n',  wheelbase);
    fprintf(fid, 'CGX (rear frac.) = %.4f\n',    cgx);
    fprintf(fid, 'Front track      = %.4f m\n',  track_f);
    fprintf(fid, 'Rear track       = %.4f m\n',  track_r);
    fprintf(fid, 'Tire radius      = %.4f m\n',  tire_rad);
    fprintf(fid, 'Corner radius R  = %.4f m\n',  R);
    fprintf(fid, 'Lat. accel.      = %.4f g\n',  a_lat_g);
    fprintf(fid, 'Yaw angle        = %.4f deg\n',yaw_deg);
    fprintf(fid, 'Outer radius     = %.4f m\n',  OR);
    fprintf(fid, 'IAW              = %.4f\n',     IAW);
    fprintf(fid, 'OAW              = %.4f\n',     OAW);
    fprintf(fid, 'Domain height    = %.4f m\n\n', dom_height);
    fprintf(fid, '--- Outputs ---\n');
    fprintf(fid, 'VMag             = %.6f m/s\n',   VMag);
    fprintf(fid, 'Domain_Rot       = %.6f rad/s\n', Domain_Rot);
    fprintf(fid, 'delta            = %.6f deg\n',   delta_deg);
    fprintf(fid, 'CG dist fr front = %.6f m\n',     CG);
    fprintf(fid, 'CoR location     = [%.6f, %.6f, %.6f]\n', CoR_x, CoR_y, CoR_z);
    fprintf(fid, 'FL_Rad = %.6f m | Omega_FL = %.6f rad/s\n', FL_Rad, Omega_FL);
    fprintf(fid, 'FR_Rad = %.6f m | Omega_FR = %.6f rad/s\n', FR_Rad, Omega_FR);
    fprintf(fid, 'RL_Rad = %.6f m | Omega_RL = %.6f rad/s\n', RL_Rad, Omega_RL);
    fprintf(fid, 'RR_Rad = %.6f m | Omega_RR = %.6f rad/s\n', RR_Rad, Omega_RR);
    fprintf(fid, 'Inlet angle      = %.6f deg\n',   inlet_angle_deg);
    fprintf(fid, 'Outlet angle     = %.6f deg\n',   outlet_angle_deg);
    fprintf(fid, '\nWake Refinement Sections:\n');
    fprintf(fid, 'Sec  Width(m)  Height(m)  CumAngle(rad)\n');
    data = [1 W1 H1 sec1_angle; 2 W2 H2 sec2_angle; 3 W3 H3 sec3_angle;
            4 W4 H4 sec4_angle; 5 W5 H5 sec5_angle; 6 W6 H6 sec6_angle];
    for k = 1:6
        fprintf(fid, ' %d   %.4f    %.4f     %.6f\n', data(k,1), data(k,2), data(k,3), data(k,4));
    end
    fprintf(fid, '\nTire Origins (lab frame):\n');
    fprintf(fid, 'FL: [%.6f, %.6f, %.6f]\n', FL_origin(1), FL_origin(2), FL_origin(3));
    fprintf(fid, 'FR: [%.6f, %.6f, %.6f]\n', FR_origin(1), FR_origin(2), FR_origin(3));
    fprintf(fid, 'RL: [%.6f, %.6f, %.6f]\n', RL_origin(1), RL_origin(2), RL_origin(3));
    fprintf(fid, 'RR: [%.6f, %.6f, %.6f]\n', RR_origin(1), RR_origin(2), RR_origin(3));
    fclose(fid);
    fprintf('\n  Results saved to: %s\n', fname);
end
