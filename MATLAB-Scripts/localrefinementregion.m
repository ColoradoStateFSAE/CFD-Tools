% Refinement Zone Coordinate Generator
% Prompts user for geometry inputs and outputs refinement coordinates

clc; clear;

% --- User Inputs ---
L = input('Enter Length (L): ');
W = input('Enter Width (W): ');
H = input('Enter Height (H): ');

% --- Near Refinement Zone ---
near.mesh = 0.032;
near.x_min = -L;
near.x_max = 3*L;
near.y_min = 0;
near.y_max = H + L/3;
near.z_min = -(W + H/2);
near.z_max = W + H/2;

% --- Mid Refinement Zone ---
mid.mesh = 0.064;
mid.x_min = -1.25*L;
mid.x_max = 5*L;
mid.y_min = 0;
mid.y_max = H + 2*L/3;
mid.z_min = -(W + H);
mid.z_max = W + H;

% --- Far Refinement Zone ---
far.mesh = 0.128;
far.x_min = -1.5*L;
far.x_max = 7*L;
far.y_min = 0;
far.y_max = 2*L;
far.z_min = -(W + 3*H/2);
far.z_max = W + 3*H/2;

% --- Display Results ---
fprintf('\n=== Near Refinement Zone ===\n');
fprintf('Mesh Size: %.3f m\n', near.mesh);
fprintf('X: [%.3f, %.3f]\n', near.x_min, near.x_max);
fprintf('Y: [%.3f, %.3f]\n', near.y_min, near.y_max);
fprintf('Z: [%.3f, %.3f]\n', near.z_min, near.z_max);

fprintf('\n=== Mid Refinement Zone ===\n');
fprintf('Mesh Size: %.3f m\n', mid.mesh);
fprintf('X: [%.3f, %.3f]\n', mid.x_min, mid.x_max);
fprintf('Y: [%.3f, %.3f]\n', mid.y_min, mid.y_max);
fprintf('Z: [%.3f, %.3f]\n', mid.z_min, mid.z_max);

fprintf('\n=== Far Refinement Zone ===\n');
fprintf('Mesh Size: %.3f m\n', far.mesh);
fprintf('X: [%.3f, %.3f]\n', far.x_min, far.x_max);
fprintf('Y: [%.3f, %.3f]\n', far.y_min, far.y_max);
fprintf('Z: [%.3f, %.3f]\n', far.z_min, far.z_max);
