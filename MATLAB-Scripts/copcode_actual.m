%% ===== VEHICLE GEOMETRY =====
L = 62;         % Wheelbase — front axle to rear axle distance (inches)

%% ===== SPRUNG ELEMENT X-POSITIONS (from front axle, rearward positive) =====
Lf = 29.36;     % Front wing CoP x-location — how far behind the front axle the front wing's center of pressure sits (inches)
Lu = 42.93;     % Undertray CoP x-location — how far behind the front axle the undertray's center of pressure sits (inches)
Lrw = L + 8.1;  % Rear wing CoP x-location — how far behind the front axle the rear wing sits, computed as wheelbase + rear-wing overhang past the rear axle (inches)
Lc = 31;        % Chassis CoP x-location — how far behind the front axle the chassis body's center of pressure sits, roughly at the wheelbase midpoint (inches)

%% ===== SPRUNG ELEMENT DOWNFORCE-CoP HEIGHTS (above ground) =====
Hf = 3;         % Front wing CoP height — vertical location of the front wing's aero force above the ground plane (inches)
Hu = 2;         % Undertray CoP height — vertical location of the undertray's aero force above the ground plane (inches)
Hrw = 42.84;    % Rear wing downforce CoP height — vertical location of the rear wing's downforce above the ground plane (inches)
Hc = 12;        % Chassis CoP height — vertical location of the chassis body's aero force above the ground plane (inches)
Hrw_drag = 42.84;   % Rear wing drag CoP height — vertical location of the rear wing's drag force above the ground plane; typically same as downforce CoP height (inches)

%% ===== UNSPRUNG ELEMENT X-POSITIONS (from front axle) =====
Lwf = 0;        % Front wheels x-location — sits at the front axle by definition, so distance from front axle is zero (inches)
Lwr = L;        % Rear wheels x-location — sits at the rear axle by definition, so distance from front axle equals wheelbase (inches)

%% ===== UNSPRUNG ELEMENT HEIGHTS =====
Hw = 9;         % Wheel CoP height — approximately equal to the tire's unloaded rolling radius, where wheel drag effectively acts (inches)

%% ===== SPRUNG DOWNFORCES (downforce is positive, lift is negative) =====
Ff = 52.23;     % Front wing downforce — vertical aero force from the front wing pushing car toward ground (lbf)
Fu = 59.6;      % Undertray downforce — vertical aero force from the undertray/diffuser pushing car toward ground (lbf)
Frw = 74;       % Rear wing downforce — vertical aero force from the rear wing pushing car toward ground (lbf)
Fc = 5;         % Chassis downforce — vertical aero force on the chassis body; often small or slightly negative (lift) (lbf)

%% ===== UNSPRUNG DOWNFORCES =====
Fwf = 3;        % Front wheels lift/downforce — vertical aero force on the two front wheels combined; usually small (lbf)
Fwr = 4;        % Rear wheels lift/downforce — vertical aero force on the two rear wheels combined; usually small (lbf)

%% ===== SPRUNG DRAG FORCES (streamwise force opposing motion) =====
Fdr_fw = 8;     % Front wing drag — streamwise aero force resisting motion from the front wing (lbf)
Fdr_u = 5;      % Undertray drag — streamwise aero force resisting motion from the undertray (lbf)
Fdr_rw = 32;    % Rear wing drag — streamwise aero force resisting motion from the rear wing; usually the largest single sprung drag contributor (lbf)
Fdr_c = 15;     % Chassis drag — streamwise aero force resisting motion from the chassis body (lbf)

%% ===== UNSPRUNG DRAG FORCES =====
Fdr_wf = 6;     % Front wheels drag — streamwise aero force resisting motion from the front wheels combined (lbf)
Fdr_wr = 6;     % Rear wheels drag — streamwise aero force resisting motion from the rear wheels combined (lbf)


%% ========== SPRUNG CoP CALCULATIONS ==========

Fz_sprung = Ff + Fu + Frw + Fc;                 % Total sprung downforce — sum of all sprung vertical aero forces (lbf)
Fx_sprung = Fdr_fw + Fdr_u + Fdr_rw + Fdr_c;    % Total sprung drag — sum of all sprung streamwise aero forces (lbf)

%% Pitching moments about the front axle from downforce elements (lbf·in)
m_frontwing = Ff * Lf;      % Moment from front wing downforce — its vertical force times its lever arm behind the front axle
m_undertray = Fu * Lu;      % Moment from undertray downforce — its vertical force times its lever arm behind the front axle
m_rearwing  = Frw * Lrw;    % Moment from rear wing downforce — its vertical force times its lever arm behind the front axle
m_chassis   = Fc * Lc;      % Moment from chassis downforce — its vertical force times its lever arm behind the front axle

%% Sprung CoP fore-aft location (x)
COP_s_x = (m_frontwing + m_rearwing + m_undertray + m_chassis) / Fz_sprung;    % Sprung CoP x — effective location of total sprung downforce, measured rearward from front axle (inches)
COP_s_pct = (COP_s_x / L) * 100;    % Sprung CoP as % of wheelbase — fraction of wheelbase back from front axle where the CoP effectively sits (%)

%% Pitching moments about the ground line from drag elements (lbf·in)
m_drag_fw = Fdr_fw * Hf;            % Moment from front wing drag — its streamwise force times its height above ground
m_drag_u  = Fdr_u  * Hu;            % Moment from undertray drag — its streamwise force times its height above ground
m_drag_rw = Fdr_rw * Hrw_drag;      % Moment from rear wing drag — its streamwise force times its height above ground
m_drag_c  = Fdr_c  * Hc;            % Moment from chassis drag — its streamwise force times its height above ground

%% Sprung CoP height (y)
COP_s_y = (m_drag_fw + m_drag_u + m_drag_rw + m_drag_c) / Fx_sprung;    % Sprung CoP y — effective height above ground at which the total sprung drag acts (inches)


%% ========== UNSPRUNG CoP CALCULATIONS ==========

Fz_unsprung = Fwf + Fwr;                % Total unsprung downforce — sum of front and rear wheel vertical aero forces (lbf)
Fx_unsprung = Fdr_wf + Fdr_wr;          % Total unsprung drag — sum of front and rear wheel streamwise aero forces (lbf)

%% Pitching moments about the front axle from unsprung downforce
m_wheels_front = Fwf * Lwf;             % Moment from front wheels downforce — zero because front wheels sit at the front axle (lever arm = 0)
m_wheels_rear  = Fwr * Lwr;             % Moment from rear wheels downforce — rear wheel force times full wheelbase (lever arm from front axle)

%% Unsprung CoP fore-aft location (x)
COP_u_x = (m_wheels_front + m_wheels_rear) / Fz_unsprung;   % Unsprung CoP x — effective location of total unsprung downforce, measured rearward from front axle (inches)
COP_u_pct = (COP_u_x / L) * 100;    % Unsprung CoP as % of wheelbase — fraction of wheelbase back from front axle where the unsprung CoP sits (%)

%% Pitching moments about the ground line from unsprung drag
m_drag_wf = Fdr_wf * Hw;                % Moment from front wheel drag — its streamwise force times tire rolling radius
m_drag_wr = Fdr_wr * Hw;                % Moment from rear wheel drag — its streamwise force times tire rolling radius

%% Unsprung CoP height (y)
COP_u_y = (m_drag_wf + m_drag_wr) / Fx_unsprung;    % Unsprung CoP y — effective height above ground at which the total unsprung drag acts, approximately tire rolling radius (inches)


%% ========== DISPLAY RESULTS ==========
fprintf('===== SPRUNG =====\n');
fprintf('Total downforce:         %.2f lbf\n', Fz_sprung);
fprintf('Total drag:              %.2f lbf\n', Fx_sprung);
fprintf('CoP x (from front axle): %.2f in\n', COP_s_x);
fprintf('CoP %% (rear):            %.2f %%\n', COP_s_pct);
fprintf('CoP y (above ground):    %.2f in\n', COP_s_y);

fprintf('\n===== UNSPRUNG =====\n');
fprintf('Total downforce:         %.2f lbf\n', Fz_unsprung);
fprintf('Total drag:              %.2f lbf\n', Fx_unsprung);
fprintf('CoP x (from front axle): %.2f in\n', COP_u_x);
fprintf('CoP %% (rear):            %.2f %%\n', COP_u_pct);
fprintf('CoP y (above ground):    %.2f in\n', COP_u_y);
