classdef ETDCombinedJSONCSVViewerApp < matlab.apps.AppBase
    % ETDCombinedJSONCSVViewerApp
    % Combined viewer:
    %   - Load ETD TrackingResult JSON (trackingResults)
    %   - Load platform CSV (Time_Sec, Pos_H, Pos_V, Pos_R, Temp_A/B, Set_A/B, Stable_A/B ...)
    %   - Overlay + compare with toggles
    %   - Optional time offset and auto delay estimate (xcorr)
    %
    % Save as ETDCombinedJSONCSVViewerApp.m
    % Run: app = ETDCombinedJSONCSVViewerApp;

    properties (Access = public)
        UIFigure matlab.ui.Figure
        MainGrid matlab.ui.container.GridLayout

        TopBar matlab.ui.container.GridLayout
        LoadJSONButton matlab.ui.control.Button
        LoadCSVButton matlab.ui.control.Button
        JSONLabel matlab.ui.control.Label
        CSVLabel matlab.ui.control.Label
        ExportPNGsButton matlab.ui.control.Button
        ExportCSVButton matlab.ui.control.Button
        RefreshButton matlab.ui.control.Button

        LeftPanel matlab.ui.container.Panel
        LeftGrid matlab.ui.container.GridLayout

        % Dataset toggles
        ShowETDCheck matlab.ui.control.CheckBox
        ShowCSVCheck matlab.ui.control.CheckBox

        % Smoothing / downsample
        SmoothCheck matlab.ui.control.CheckBox
        SmoothWinLabel matlab.ui.control.Label
        SmoothWinEdit matlab.ui.control.NumericEditField
        DownsampleLabel matlab.ui.control.Label
        DownsampleEdit matlab.ui.control.NumericEditField
        MarkersCheck matlab.ui.control.CheckBox

        % Time alignment
        TimeAlignLabel matlab.ui.control.Label
        TimeOffsetEdit matlab.ui.control.NumericEditField % seconds, applied to CSV
        AutoDelayButton matlab.ui.control.Button
        DelayResultLabel matlab.ui.control.Label
        SyncPeaksButton matlab.ui.control.Button

        % Mapping
        MapLabel matlab.ui.control.Label
        MapDrop matlab.ui.control.DropDown

        % Matrix element selection (ETD)
        MatrixLabel matlab.ui.control.Label
        MatrixDrop matlab.ui.control.DropDown

        Tabs matlab.ui.container.TabGroup
        TabOverview matlab.ui.container.Tab
        TabCompare matlab.ui.container.Tab
        Tab3D matlab.ui.container.Tab
        TabMatrix matlab.ui.container.Tab
        TabStats matlab.ui.container.Tab

        % Axes
        AxRMSE matlab.ui.control.UIAxes
        AxTracking matlab.ui.control.UIAxes

        AxTrans matlab.ui.control.UIAxes
        AxRot matlab.ui.control.UIAxes

        AxCompare matlab.ui.control.UIAxes
        AxTemp matlab.ui.control.UIAxes

        AxTraj2D matlab.ui.control.UIAxes
        AxTraj3D matlab.ui.control.UIAxes

        AxMatrixElem matlab.ui.control.UIAxes
        AxMatrixHeat matlab.ui.control.UIAxes

        StatsText matlab.ui.control.TextArea
    end

    properties (Access = private)
        JSONPath char = ''
        CSVPath  char = ''

        ETD table = table()   % parsed ETD signals (t, rmse, shifts, M01..M16)
        CSV table = table()   % parsed CSV signals (t, Pos_H, Pos_V, Pos_R, Temp_*, Set_*, Stable_*)
        HasETD logical = false
        HasCSV logical = false
    end

    methods (Access = public)
        function app = ETDCombinedJSONCSVViewerApp
            app.createComponents();
            app.startup();
        end

        function delete(app)
            if isvalid(app.UIFigure), delete(app.UIFigure); end
        end
    end

    methods (Access = private)
        function startup(app)
            app.populateMatrixDropdown();
            app.populateMappingDropdown();

            app.ShowETDCheck.Value = true;
            app.ShowCSVCheck.Value = true;
            app.SmoothCheck.Value = true;
            app.SmoothWinEdit.Value = 7;
            app.DownsampleEdit.Value = 1;
            app.MarkersCheck.Value = false;

            app.TimeOffsetEdit.Value = 0.0; % seconds to ADD to CSV time (shift)
            app.DelayResultLabel.Text = "Auto delay: (not computed)";

            app.JSONLabel.Text = "JSON: none";
            app.CSVLabel.Text  = "CSV: none";

            app.updateAll();
        end

        % -------------------- Loading --------------------
        function onLoadJSON(app)
            [f,p] = uigetfile({'*.json','JSON files (*.json)'}, 'Select ETD TrackingResult JSON');
            if isequal(f,0), return; end
            app.JSONPath = fullfile(p,f);
            app.JSONLabel.Text = ['JSON: ' app.JSONPath];

            try
                s = fileread(app.JSONPath);
                st = jsondecode(s);
                if ~isfield(st,'trackingResults') || isempty(st.trackingResults)
                    uialert(app.UIFigure, 'JSON has no trackingResults.', 'Load error');
                    app.HasETD = false;
                    app.ETD = table();
                    app.updateAll();
                    return;
                end
                app.ETD = app.parseETD(st);
                app.HasETD = true;
                app.updateAll();
            catch ME
                app.HasETD = false;
                app.ETD = table();
                uialert(app.UIFigure, ['JSON load failed: ' ME.message], 'Load error');
            end
        end

        function onLoadCSV(app)
            [f,p] = uigetfile({'*.csv','CSV files (*.csv)'; '*.*','All files (*.*)'}, 'Select platform CSV');
            if isequal(f,0), return; end
            app.CSVPath = fullfile(p,f);
            app.CSVLabel.Text = ['CSV: ' app.CSVPath];

            try
                T = app.loadCSVSmart(app.CSVPath);
                T = app.standardizeVarNames(T);
                T = app.forceNumericColumns(T);

                % Require some time column
                tvar = app.findFirstExistingVar(T, {'Time_Sec','time_sec','Time','t','timestamp','Timestamp'});
                if isempty(tvar)
                    uialert(app.UIFigure, 'CSV: no time column found (e.g. Time_Sec).', 'Load error');
                    app.HasCSV = false;
                    app.CSV = table();
                    app.updateAll();
                    return;
                end

                % Normalize time to seconds, start at 0
                t = double(T.(tvar));
                t = t - t(1);
                T.Time_Sec = t;

                app.CSV = T;
                app.HasCSV = true;
                app.updateAll();
            catch ME
                app.HasCSV = false;
                app.CSV = table();
                uialert(app.UIFigure, ['CSV load failed: ' ME.message], 'Load error');
            end
        end

        function ETD = parseETD(app, st)
            tr = st.trackingResults;
            n = numel(tr);

            trackingLost = false(n,1);
            timestamp_ms = zeros(n,1);
            rmse3D = nan(n,1);
            rmseThermal = nan(n,1);

            dist  = nan(n,1);
            lat   = nan(n,1);
            lng   = nan(n,1);
            vert  = nan(n,1);
            pitch = nan(n,1);
            roll  = nan(n,1);
            yaw   = nan(n,1);

            M = nan(n,16);

            for i=1:n
                x = tr(i);
                if isfield(x,'trackingLost'), trackingLost(i) = logical(x.trackingLost); end
                if isfield(x,'timestamp'), timestamp_ms(i)=double(x.timestamp); end
                if isfield(x,'rmse3D'), rmse3D(i)=double(x.rmse3D); end
                if isfield(x,'rmseThermal'), rmseThermal(i)=double(x.rmseThermal); end

                if isfield(x,'shiftValues') && ~isempty(x.shiftValues)
                    sv = x.shiftValues;
                    dist(i)=app.toNum(sv,'distance');
                    lat(i)=app.toNum(sv,'lateral');
                    lng(i)=app.toNum(sv,'longitudinal');
                    vert(i)=app.toNum(sv,'vertical');
                    pitch(i)=app.toNum(sv,'pitch');
                    roll(i)=app.toNum(sv,'roll');
                    yaw(i)=app.toNum(sv,'yaw');
                end

                if isfield(x,'shiftAsMatrix') && ~isempty(x.shiftAsMatrix)
                    v = x.shiftAsMatrix;
                    if isnumeric(v) && numel(v)==16
                        M(i,:) = reshape(double(v),1,16);
                    end
                end
            end

            t = (timestamp_ms - timestamp_ms(1))/1000.0; % sec, start at 0

            ETD = table(t, trackingLost, rmse3D, rmseThermal, dist, lat, lng, vert, pitch, roll, yaw);
            for k=1:16
                ETD.(sprintf('M%02d',k)) = M(:,k);
            end
        end

        function x = toNum(app, sv, field)
            x = NaN;
            if isfield(sv, field)
                v = sv.(field);
                if ischar(v), x = str2double(v);
                elseif isstring(v), x = str2double(char(v));
                elseif isnumeric(v), x = double(v);
                end
            end
        end

        % -------------------- CSV helpers --------------------
        function T = loadCSVSmart(app, path)
            T = readtable(path);

            % If single column and header seems semicolon-separated -> retry
            if width(T)==1
                header = T.Properties.VariableNames{1};
                if contains(header,';')
                    T = readtable(path,'Delimiter',';');
                else
                    raw = fileread(path);
                    firstLine = regexp(raw, '^\s*([^\r\n]+)', 'tokens', 'once');
                    if ~isempty(firstLine) && contains(firstLine{1}, ';')
                        T = readtable(path,'Delimiter',';');
                    end
                end
            end
        end

        function T = standardizeVarNames(app, T)
            vn = T.Properties.VariableNames;

            map = {
                {'Time_Sec','time_sec','Time','t','sec','timestamp','Timestamp'}, 'Time_Sec';
                {'Pos_H','pos_h','H','PosX','X'}, 'Pos_H';
                {'Pos_V','pos_v','V','PosY','Y'}, 'Pos_V';
                {'Pos_R','pos_r','R','Rot','Angle'}, 'Pos_R';
                {'Temp_A','temp_a','TA','Temp1'}, 'Temp_A';
                {'Temp_B','temp_b','TB','Temp2'}, 'Temp_B';
                {'Set_A','set_a','Setpoint_A','SA'}, 'Set_A';
                {'Set_B','set_b','Setpoint_B','SB'}, 'Set_B';
                {'Stable_A','stable_a','Stab_A','OK_A'}, 'Stable_A';
                {'Stable_B','stable_b','Stab_B','OK_B'}, 'Stable_B';
            };

            for i=1:size(map,1)
                aliases = map{i,1};
                target = map{i,2};
                idx = find(ismember(lower(vn), lower(aliases)), 1, 'first');
                if ~isempty(idx)
                    vn{idx} = target;
                end
            end

            T.Properties.VariableNames = matlab.lang.makeUniqueStrings(matlab.lang.makeValidName(vn));
        end

        function T = forceNumericColumns(app, T)
            for k=1:width(T)
                col = T{:,k};
                if iscellstr(col) || isstring(col)
                    s = string(col);
                    s = replace(s, ',', '.');
                    x = str2double(s);
                    if sum(~isnan(x)) >= max(3, round(0.6*numel(x)))
                        T{:,k} = x;
                    end
                end
            end
        end

        function name = findFirstExistingVar(app, T, candidates)
            name = '';
            vn = T.Properties.VariableNames;
            for i=1:numel(candidates)
                if any(strcmp(vn, candidates{i}))
                    name = candidates{i};
                    return;
                end
            end
        end

        % -------------------- UI actions --------------------
        function onRefresh(app)
            app.updateAll();
        end

        function onAutoDelay(app)
            % Estimate delay between ETD longitudinal (or selected ETD axis) and CSV mapped axis
            if ~app.HasETD || ~app.HasCSV
                uialert(app.UIFigure, 'Load both JSON and CSV first.', 'Auto delay');
                return;
            end

            % Choose signals
            [etdSigName, csvSigName] = app.getCompareSignals();

            if ~ismember(etdSigName, app.ETD.Properties.VariableNames)
                uialert(app.UIFigure, ['ETD signal not found: ' etdSigName], 'Auto delay');
                return;
            end
            if ~ismember(csvSigName, app.CSV.Properties.VariableNames)
                uialert(app.UIFigure, ['CSV signal not found: ' csvSigName], 'Auto delay');
                return;
            end

            tE = app.ETD.t;
            yE = double(app.ETD.(etdSigName));

            tC = app.CSV.Time_Sec + app.TimeOffsetEdit.Value;
            yC = double(app.CSV.(csvSigName));

            % Resample both to common uniform grid for xcorr
            dt = app.estimateCommonDt(tE, tC);
            if ~isfinite(dt) || dt<=0
                uialert(app.UIFigure, 'Could not estimate sample rate for delay.', 'Auto delay');
                return;
            end

            tMin = max(min(tE), min(tC));
            tMax = min(max(tE), max(tC));
            if tMax <= tMin
                uialert(app.UIFigure, 'No overlapping time range for delay estimation.', 'Auto delay');
                return;
            end

            tg = (tMin:dt:tMax)';
            yEg = interp1(tE, yE, tg, 'linear', 'extrap');
            yCg = interp1(tC, yC, tg, 'linear', 'extrap');

            % Detrend / normalize (robust)
            yEg = yEg - mean(yEg,'omitnan');
            yCg = yCg - mean(yCg,'omitnan');
            yEg(isnan(yEg)) = 0;
            yCg(isnan(yCg)) = 0;

            [xc,lags] = xcorr(yEg, yCg);
            [~,im] = max(xc);
            lag = lags(im);
            delaySec = -lag * dt; % positive => add to CSV to align to ETD

            app.TimeOffsetEdit.Value = app.TimeOffsetEdit.Value + delaySec;
            app.DelayResultLabel.Text = sprintf('Auto delay applied: %.3f s (CSV shifted)', delaySec);

            app.updateAll();
        end

        function dt = estimateCommonDt(app, tE, tC)
            dE = diff(tE); dE = dE(isfinite(dE) & dE>0);
            dC = diff(tC); dC = dC(isfinite(dC) & dC>0);
            if isempty(dE) || isempty(dC)
                dt = NaN; return;
            end
            dt = max(median(dE), median(dC)); % safe for resampling
        end
        
        function onSyncPeaks(app)
            if ~app.HasETD || ~app.HasCSV
                uialert(app.UIFigure, 'Load both JSON and CSV first.', 'Sync Error');
                return;
            end
            
            % Wir nutzen die in der Dropdown-Liste gewählten Signale (z.B. lng und Pos_H)
            [etdSigName, csvSigName] = app.getCompareSignals();
            
            tE = app.ETD.t;
            yE = double(app.ETD.(etdSigName));
            tC = app.CSV.Time_Sec; % Ohne Offset, da wir ihn neu berechnen
            yC = double(app.CSV.(csvSigName));
            
            try
                [t_csv_synced, t_json_synced] = app.synchronizeTimeAxes(tC, yC, tE, yE);
                
                % Neue Zeitachsen zuweisen
                app.CSV.Time_Sec = t_csv_synced;
                app.ETD.t = t_json_synced;
                
                % UI Offset resetten, da die Zeiten jetzt absolut synchronisiert sind
                app.TimeOffsetEdit.Value = 0;
                app.DelayResultLabel.Text = 'Sync by 5mm Peaks applied!';
                
                app.updateAll();
            catch ME
                uialert(app.UIFigure, ['Sync failed: ' ME.message], 'Sync Error');
            end
        end

        function [t_csv_synced, t_json_synced] = synchronizeTimeAxes(app, t_csv, v_csv, t_json, v_json)
            function [t_mid_first, t_mid_last] = findPeakMidpoints(t, v)
                % Filter gegen leichtes Rauschen (Debouncing)
                v_smooth = movmedian(v, 5, 'omitnan');
                threshold = 4.5; 
                is_peak = v_smooth > threshold;
                
                edges = diff([0; is_peak; 0]);
                start_idx = find(edges == 1);
                end_idx = find(edges == -1) - 1;
                
                if length(start_idx) >= 2
                    idx_mid_first = round((start_idx(1) + end_idx(1)) / 2);
                    t_mid_first = t(idx_mid_first);
                    idx_mid_last = round((start_idx(end) + end_idx(end)) / 2);
                    t_mid_last = t(idx_mid_last);
                else
                    error('Nicht genügend 5mm Peaks für die Synchronisation gefunden.');
                end
            end

            [t_csv_first, t_csv_last] = findPeakMidpoints(t_csv, v_csv);
            [t_json_first, t_json_last] = findPeakMidpoints(t_json, v_json);
            
            delta_t_csv = t_csv_last - t_csv_first;
            delta_t_json = t_json_last - t_json_first;
            
            if delta_t_json > 0
                scale_factor = delta_t_csv / delta_t_json;
            else
                scale_factor = 1; 
            end
            
            t_csv_synced = t_csv - t_csv_first;
            t_json_synced = (t_json - t_json_first) * scale_factor;
        end

        % -------------------- Plotting --------------------
        function updateAll(app)
            app.updateOverview();
            app.updateCompare();
            app.updateTraj();
            app.updateMatrix();
            app.updateStats();
        end

        function [idxE, idxC] = downsampleIdx(app)
            ds = max(1, round(app.DownsampleEdit.Value));
            idxE = [];
            idxC = [];
            if app.HasETD
                idxE = 1:ds:height(app.ETD);
            end
            if app.HasCSV
                idxC = 1:ds:height(app.CSV);
            end
        end

        function y = maybeSmooth(app, y)
            if ~app.SmoothCheck.Value, return; end
            w = max(1, round(app.SmoothWinEdit.Value));
            try
                y = movmean(y, w, 'omitnan');
            catch
                y = movmean(y, w);
            end
        end

        function mk = markerStyle(app)
            if app.MarkersCheck.Value, mk='.'; else, mk='none'; end
        end

        function updateOverview(app)
            cla(app.AxRMSE); cla(app.AxTracking);

            mk = app.markerStyle();
            [idxE, idxC] = app.downsampleIdx(); %#ok<NASGU>

            % RMSE axes: ETD only
            if app.HasETD && app.ShowETDCheck.Value
                t = app.ETD.t(idxE);
                r3 = app.maybeSmooth(app.ETD.rmse3D(idxE));
                rt = app.maybeSmooth(app.ETD.rmseThermal(idxE));
                plot(app.AxRMSE, t, r3, 'Marker', mk); hold(app.AxRMSE,'on');
                plot(app.AxRMSE, t, rt, 'Marker', mk);
                legend(app.AxRMSE, {'rmse3D (ETD)','rmseThermal (ETD)'}, 'Location','best');
            end
            grid(app.AxRMSE,'on');
            xlabel(app.AxRMSE,'Time (s)');
            ylabel(app.AxRMSE,'RMSE');
            title(app.AxRMSE,'ETD quality metrics');

            % Tracking status: ETD only
            if app.HasETD && app.ShowETDCheck.Value
                t = app.ETD.t(idxE);
                stairs(app.AxTracking, t, double(app.ETD.trackingLost(idxE)), 'LineWidth', 1.5);
                ylim(app.AxTracking, [-0.1 1.1]);
                yticks(app.AxTracking,[0 1]); yticklabels(app.AxTracking,{'OK','Lost'});
            end
            grid(app.AxTracking,'on');
            xlabel(app.AxTracking,'Time (s)');
            title(app.AxTracking,'Tracking status (ETD)');
        end

        function updateCompare(app)
            cla(app.AxTrans); cla(app.AxRot); cla(app.AxCompare); cla(app.AxTemp);
            mk = app.markerStyle();
            [idxE, idxC] = app.downsampleIdx();

            % --- Translations overlay (ETD translations + CSV positions mapped)
            hold(app.AxTrans,'off');
            leg = {};

            if app.HasETD && app.ShowETDCheck.Value
                tE = app.ETD.t(idxE);
                lat = app.maybeSmooth(app.ETD.lat(idxE));
                lng = app.maybeSmooth(app.ETD.lng(idxE));
                vrt = app.maybeSmooth(app.ETD.vert(idxE));

                plot(app.AxTrans, tE, lat, 'Marker', mk); hold(app.AxTrans,'on'); leg{end+1}='ETD lateral';
                plot(app.AxTrans, tE, lng, 'Marker', mk); leg{end+1}='ETD longitudinal';
                plot(app.AxTrans, tE, vrt, 'Marker', mk); leg{end+1}='ETD vertical';
            end

            if app.HasCSV && app.ShowCSVCheck.Value
                tC = (app.CSV.Time_Sec + app.TimeOffsetEdit.Value);
                tC = tC(idxC);

                if ismember('Pos_H', app.CSV.Properties.VariableNames)
                    y = app.maybeSmooth(double(app.CSV.Pos_H(idxC)));
                    plot(app.AxTrans, tC, y, '--', 'Marker', mk); hold(app.AxTrans,'on'); leg{end+1}='CSV Pos\_H';
                end
                if ismember('Pos_V', app.CSV.Properties.VariableNames)
                    y = app.maybeSmooth(double(app.CSV.Pos_V(idxC)));
                    plot(app.AxTrans, tC, y, '--', 'Marker', mk); leg{end+1}='CSV Pos\_V';
                end
            end

            grid(app.AxTrans,'on');
            xlabel(app.AxTrans,'Time (s)');
            ylabel(app.AxTrans,'Shift / Position (mm)');
            title(app.AxTrans,'Translations / Platform positions');
            if ~isempty(leg), legend(app.AxTrans, leg, 'Location','best'); end

            % --- Rotations overlay (ETD pitch/roll/yaw + CSV Pos_R)
            hold(app.AxRot,'off'); leg = {};
            if app.HasETD && app.ShowETDCheck.Value
                tE = app.ETD.t(idxE);
                p = app.maybeSmooth(app.ETD.pitch(idxE));
                r = app.maybeSmooth(app.ETD.roll(idxE));
                y = app.maybeSmooth(app.ETD.yaw(idxE));
                plot(app.AxRot, tE, p, 'Marker', mk); hold(app.AxRot,'on'); leg{end+1}='ETD pitch';
                plot(app.AxRot, tE, r, 'Marker', mk); leg{end+1}='ETD roll';
                plot(app.AxRot, tE, y, 'Marker', mk); leg{end+1}='ETD yaw';
            end
            if app.HasCSV && app.ShowCSVCheck.Value && ismember('Pos_R', app.CSV.Properties.VariableNames)
                tC = (app.CSV.Time_Sec + app.TimeOffsetEdit.Value);
                tC = tC(idxC);
                yR = app.maybeSmooth(double(app.CSV.Pos_R(idxC)));
                plot(app.AxRot, tC, yR, '--', 'Marker', mk); hold(app.AxRot,'on'); leg{end+1}='CSV Pos\_R';
            end
            grid(app.AxRot,'on');
            xlabel(app.AxRot,'Time (s)');
            ylabel(app.AxRot,'Rotation (deg)');
            title(app.AxRot,'Rotations');
            if ~isempty(leg), legend(app.AxRot, leg, 'Location','best'); end

            % --- Smart compare plot (one ETD signal vs mapped CSV signal)
            hold(app.AxCompare,'off'); leg = {};
            if app.HasETD && app.HasCSV && app.ShowETDCheck.Value && app.ShowCSVCheck.Value
                [etdSig, csvSig] = app.getCompareSignals();
                if ismember(etdSig, app.ETD.Properties.VariableNames) && ismember(csvSig, app.CSV.Properties.VariableNames)
                    tE = app.ETD.t(idxE);
                    yE = app.maybeSmooth(double(app.ETD.(etdSig)(idxE)));
                    tC = (app.CSV.Time_Sec + app.TimeOffsetEdit.Value);
                    tC = tC(idxC);
                    yC = app.maybeSmooth(double(app.CSV.(csvSig)(idxC)));

                    plot(app.AxCompare, tE, yE, 'LineWidth', 1.2, 'Marker', mk); hold(app.AxCompare,'on'); leg{end+1}=['ETD ' etdSig];
                    plot(app.AxCompare, tC, yC, '--', 'LineWidth', 1.2, 'Marker', mk); leg{end+1}=['CSV ' csvSig];

                    % correlation on overlap (as quick metric)
                    [rho, nUsed] = app.quickCorrelation(tE,yE,tC,yC);
                    title(app.AxCompare, sprintf('Compare (%s vs %s)  |  corr=%.3f  (n=%d)', etdSig, csvSig, rho, nUsed));
                else
                    title(app.AxCompare, 'Compare: missing signals');
                end
            else
                title(app.AxCompare, 'Compare: load both + enable both datasets');
            end
            grid(app.AxCompare,'on');
            xlabel(app.AxCompare,'Time (s)');
            ylabel(app.AxCompare,'Value');
            if ~isempty(leg), legend(app.AxCompare, leg, 'Location','best'); end

            % --- Temperature plot (CSV only)
            hold(app.AxTemp,'off'); leg = {};
            if app.HasCSV && app.ShowCSVCheck.Value
                tC = (app.CSV.Time_Sec + app.TimeOffsetEdit.Value);
                tC = tC(idxC);

                if ismember('Temp_A', app.CSV.Properties.VariableNames)
                    y = app.maybeSmooth(double(app.CSV.Temp_A(idxC)));
                    plot(app.AxTemp, tC, y, 'Marker', mk); hold(app.AxTemp,'on'); leg{end+1}='Temp\_A';
                end
                if ismember('Temp_B', app.CSV.Properties.VariableNames)
                    y = app.maybeSmooth(double(app.CSV.Temp_B(idxC)));
                    plot(app.AxTemp, tC, y, 'Marker', mk); leg{end+1}='Temp\_B';
                end
                if ismember('Set_A', app.CSV.Properties.VariableNames)
                    plot(app.AxTemp, tC, double(app.CSV.Set_A(idxC)), '--'); hold(app.AxTemp,'on'); leg{end+1}='Set\_A';
                end
                if ismember('Set_B', app.CSV.Properties.VariableNames)
                    plot(app.AxTemp, tC, double(app.CSV.Set_B(idxC)), '--'); hold(app.AxTemp,'on'); leg{end+1}='Set\_B';
                end
            end
            grid(app.AxTemp,'on');
            xlabel(app.AxTemp,'Time (s)');
            ylabel(app.AxTemp,'Temp / Setpoint');
            title(app.AxTemp,'Platform temperature & setpoints');
            if ~isempty(leg), legend(app.AxTemp, leg, 'Location','best'); end
        end

        function [rho, nUsed] = quickCorrelation(app, tE, yE, tC, yC)
            % Pearson correlation without Statistics Toolbox (no corr()).
            % Interpolate CSV onto ETD time points in overlap, then compute
            % rho = cov(y1,y2) / (std(y1)*std(y2))
        
            % overlap
            tMin = max(min(tE), min(tC));
            tMax = min(max(tE), max(tC));
            mask = (tE >= tMin) & (tE <= tMax) & isfinite(yE);
            t = tE(mask);
            y1 = yE(mask);
        
            if numel(t) < 5
                rho = NaN; nUsed = numel(t);
                return;
            end
        
            y2 = interp1(tC, yC, t, 'linear', NaN);
        
            ok = isfinite(y1) & isfinite(y2);
            y1 = double(y1(ok));
            y2 = double(y2(ok));
            nUsed = numel(y1);
        
            if nUsed < 5
                rho = NaN;
                return;
            end
        
            % demean
            y1 = y1 - mean(y1);
            y2 = y2 - mean(y2);
        
            s1 = sqrt(sum(y1.^2));
            s2 = sqrt(sum(y2.^2));
        
            if s1 == 0 || s2 == 0
                rho = NaN;
                return;
            end
        
            rho = sum(y1 .* y2) / (s1 * s2);
        end

        function updateTraj(app)
            cla(app.AxTraj2D); cla(app.AxTraj3D);
            mk = app.markerStyle();
            [idxE, idxC] = app.downsampleIdx();

            % 2D trajectory: ETD lat vs long; CSV Pos_H vs Pos_V
            hold(app.AxTraj2D,'off'); leg = {};
            if app.HasETD && app.ShowETDCheck.Value
                x = app.maybeSmooth(app.ETD.lat(idxE));
                y = app.maybeSmooth(app.ETD.lng(idxE));
                plot(app.AxTraj2D, x, y, '-', 'LineWidth', 1.2, 'Marker', mk); hold(app.AxTraj2D,'on');
                leg{end+1}='ETD lat-long';
            end
            if app.HasCSV && app.ShowCSVCheck.Value && ismember('Pos_H', app.CSV.Properties.VariableNames) && ismember('Pos_V', app.CSV.Properties.VariableNames)
                x = app.maybeSmooth(double(app.CSV.Pos_H(idxC)));
                y = app.maybeSmooth(double(app.CSV.Pos_V(idxC)));
                plot(app.AxTraj2D, x, y, '--', 'LineWidth', 1.2, 'Marker', mk); hold(app.AxTraj2D,'on');
                leg{end+1}='CSV Pos\_H-Pos\_V';
            end
            grid(app.AxTraj2D,'on');
            xlabel(app.AxTraj2D,'X (mm)'); ylabel(app.AxTraj2D,'Y (mm)');
            title(app.AxTraj2D,'2D trajectory');
            if ~isempty(leg), legend(app.AxTraj2D, leg, 'Location','best'); end
            axis(app.AxTraj2D,'equal');

            % 3D trajectory: ETD lat-long-vert (CSV only if you have a 3rd axis; else skip)
            hold(app.AxTraj3D,'off'); leg = {};
            if app.HasETD && app.ShowETDCheck.Value
                x = app.maybeSmooth(app.ETD.lat(idxE));
                y = app.maybeSmooth(app.ETD.lng(idxE));
                z = app.maybeSmooth(app.ETD.vert(idxE));
                plot3(app.AxTraj3D, x, y, z, '-', 'LineWidth', 1.2, 'Marker', mk); hold(app.AxTraj3D,'on');
                leg{end+1}='ETD (lat,long,vert)';
            end
            grid(app.AxTraj3D,'on');
            xlabel(app.AxTraj3D,'lateral'); ylabel(app.AxTraj3D,'longitudinal'); zlabel(app.AxTraj3D,'vertical');
            title(app.AxTraj3D,'3D trajectory (ETD)');
            if ~isempty(leg), legend(app.AxTraj3D, leg, 'Location','best'); end
            view(app.AxTraj3D, 3);
        end

        function updateMatrix(app)
            cla(app.AxMatrixElem); cla(app.AxMatrixHeat);
            if ~(app.HasETD && app.ShowETDCheck.Value)
                title(app.AxMatrixElem,'Load/enable ETD JSON'); title(app.AxMatrixHeat,'');
                return;
            end

            [idxE, ~] = app.downsampleIdx();
            mk = app.markerStyle();

            sel = app.MatrixDrop.Value; % "M(1,4)"
            k = app.matrixLabelToIndex(sel);
            colName = sprintf('M%02d',k);

            t = app.ETD.t(idxE);
            y = app.maybeSmooth(app.ETD.(colName)(idxE));
            plot(app.AxMatrixElem, t, y, 'Marker', mk);
            grid(app.AxMatrixElem,'on');
            xlabel(app.AxMatrixElem,'Time (s)'); ylabel(app.AxMatrixElem, colName);
            title(app.AxMatrixElem, ['ETD shiftAsMatrix element: ' sel]);

            % Mean heatmap
            Mmean = nan(4,4);
            for kk=1:16
                cn = sprintf('M%02d',kk);
                Mmean(kk) = mean(app.ETD.(cn), 'omitnan');
            end
            Mmean = reshape(Mmean,4,4);
            imagesc(app.AxMatrixHeat, Mmean);
            axis(app.AxMatrixHeat,'image');
            colorbar(app.AxMatrixHeat);
            title(app.AxMatrixHeat,'Mean shiftAsMatrix (ETD)');
            xticks(app.AxMatrixHeat,1:4); yticks(app.AxMatrixHeat,1:4);
            xlabel(app.AxMatrixHeat,'col'); ylabel(app.AxMatrixHeat,'row');
        end

        function k = matrixLabelToIndex(app, label)
            tok = regexp(label,'M\((\d),(\d)\)','tokens','once');
            if isempty(tok), k = 4; return; end
            r = str2double(tok{1});
            c = str2double(tok{2});
            k = (r-1)*4 + c;
        end

        function updateStats(app)
            lines = {};
            lines{end+1} = '=== Combined Viewer Stats ===';
            lines{end+1} = '';

            lines{end+1} = ['ETD loaded: ' app.boolStr(app.HasETD) '   | shown: ' app.boolStr(app.ShowETDCheck.Value)];
            if app.HasETD
                lines{end+1} = sprintf('  ETD duration: %.3f s, samples: %d', app.ETD.t(end)-app.ETD.t(1), height(app.ETD));
                lines{end+1} = sprintf('  ETD rmse3D mean: %.4f', mean(app.ETD.rmse3D,'omitnan'));
            end
            lines{end+1} = '';

            lines{end+1} = ['CSV loaded: ' app.boolStr(app.HasCSV) '   | shown: ' app.boolStr(app.ShowCSVCheck.Value)];
            if app.HasCSV
                lines{end+1} = sprintf('  CSV duration: %.3f s, samples: %d', app.CSV.Time_Sec(end)-app.CSV.Time_Sec(1), height(app.CSV));
            end
            lines{end+1} = '';
            lines{end+1} = sprintf('CSV time offset (s): %.3f  (added to CSV time)', app.TimeOffsetEdit.Value);
            lines{end+1} = app.DelayResultLabel.Text;
            lines{end+1} = '';

            % Compare metric
            if app.HasETD && app.HasCSV
                [etdSig, csvSig] = app.getCompareSignals();
                if ismember(etdSig, app.ETD.Properties.VariableNames) && ismember(csvSig, app.CSV.Properties.VariableNames)
                    tE = app.ETD.t;
                    yE = double(app.ETD.(etdSig));
                    tC = app.CSV.Time_Sec + app.TimeOffsetEdit.Value;
                    yC = double(app.CSV.(csvSig));
                    [rho, nUsed] = app.quickCorrelation(tE,yE,tC,yC);
                    lines{end+1} = sprintf('Compare corr(%s, %s): %.3f (n=%d)', etdSig, csvSig, rho, nUsed);
                end
            end

            app.StatsText.Value = lines;
        end

        function s = boolStr(app, b)
            if b, s='true'; else, s='false'; end
        end

        function [etdSig, csvSig] = getCompareSignals(app)
            % Dropdown values: "ETD:lng  <->  CSV:Pos_H" etc
            v = app.MapDrop.Value;
            % format: "ETD longitudinal (lng)  <->  CSV Pos_H"
            if contains(v,'lng') && contains(v,'Pos_H')
                etdSig='lng'; csvSig='Pos_H';
            elseif contains(v,'lng') && contains(v,'Pos_V')
                etdSig='lng'; csvSig='Pos_V';
            elseif contains(v,'vert') && contains(v,'Pos_V')
                etdSig='vert'; csvSig='Pos_V';
            elseif contains(v,'lat') && contains(v,'Pos_H')
                etdSig='lat'; csvSig='Pos_H';
            else
                % default
                etdSig='lng'; csvSig='Pos_H';
            end
        end

        function populateMappingDropdown(app)
            app.MapDrop.Items = {
                'ETD longitudinal (lng)  <->  CSV Pos_H'
                'ETD longitudinal (lng)  <->  CSV Pos_V'
                'ETD vertical (vert)     <->  CSV Pos_V'
                'ETD lateral (lat)       <->  CSV Pos_H'
            };
            app.MapDrop.Value = app.MapDrop.Items{1};
        end

        function populateMatrixDropdown(app)
            items = cell(16,1);
            k=1;
            for r=1:4
                for c=1:4
                    items{k} = sprintf('M(%d,%d)',r,c);
                    k=k+1;
                end
            end
            app.MatrixDrop.Items = items;
            app.MatrixDrop.Value = 'M(1,4)';
        end

        % -------------------- Export --------------------
        function onExportPNGs(app)
            outDir = uigetdir(pwd, 'Select output folder for PNG exports');
            if isequal(outDir,0), return; end
            try
                exportgraphics(app.AxRMSE,      fullfile(outDir,'Overview_RMSE.png'), 'Resolution', 150);
                exportgraphics(app.AxTracking,  fullfile(outDir,'Overview_Tracking.png'), 'Resolution', 150);
                exportgraphics(app.AxTrans,     fullfile(outDir,'Compare_Translations.png'), 'Resolution', 150);
                exportgraphics(app.AxRot,       fullfile(outDir,'Compare_Rotations.png'), 'Resolution', 150);
                exportgraphics(app.AxCompare,   fullfile(outDir,'Compare_Signal.png'), 'Resolution', 150);
                exportgraphics(app.AxTemp,      fullfile(outDir,'Compare_Temperature.png'), 'Resolution', 150);
                exportgraphics(app.AxTraj2D,    fullfile(outDir,'Trajectory_2D.png'), 'Resolution', 150);
                exportgraphics(app.AxTraj3D,    fullfile(outDir,'Trajectory_3D.png'), 'Resolution', 150);
                exportgraphics(app.AxMatrixElem,fullfile(outDir,'Matrix_Element.png'), 'Resolution', 150);
                exportgraphics(app.AxMatrixHeat,fullfile(outDir,'Matrix_Mean.png'), 'Resolution', 150);
                uialert(app.UIFigure, ['Exported PNGs to: ' outDir], 'Export OK');
            catch ME
                uialert(app.UIFigure, ['PNG export failed: ' ME.message], 'Export error');
            end
        end

        function onExportCSV(app)
            % Exports a merged/aligned table (simple outer join on time grid is overkill;
            % we export ETD and CSV separately as two sheets -> but asked "CSV", so we write two files)
            [f,p] = uiputfile({'*.csv','CSV (*.csv)'}, 'Save export (will create *_ETD.csv and *_CSV.csv)');
            if isequal(f,0), return; end
            base = fullfile(p, erase(f,'.csv'));
            try
                if app.HasETD
                    writetable(app.ETD, [base '_ETD.csv']);
                end
                if app.HasCSV
                    T = app.CSV;
                    T.Time_Sec_Aligned = T.Time_Sec + app.TimeOffsetEdit.Value;
                    writetable(T, [base '_CSV.csv']);
                end
                uialert(app.UIFigure, ['Saved: ' base '_ETD.csv  and/or  ' base '_CSV.csv'], 'Export OK');
            catch ME
                uialert(app.UIFigure, ['CSV export failed: ' ME.message], 'Export error');
            end
        end

        % -------------------- UI --------------------
        function createComponents(app)

           
            app.UIFigure = uifigure('Visible','off');
            app.UIFigure.Name = 'ETD Combined JSON + CSV Viewer';
            app.UIFigure.Position = [80 80 1350 820];

            app.MainGrid = uigridlayout(app.UIFigure,[2 2]);
            app.MainGrid.RowHeight = {46,'1x'};
            app.MainGrid.ColumnWidth = {320,'1x'};
            app.MainGrid.Padding = [8 8 8 8];
            app.MainGrid.RowSpacing = 8;
            app.MainGrid.ColumnSpacing = 8;

            % Top bar
            app.TopBar = uigridlayout(app.MainGrid,[1 7]);
            app.TopBar.Layout.Row = 1;
            app.TopBar.Layout.Column = [1 2];
            app.TopBar.ColumnWidth = {110,110,'1x','1x',120,120,100};
            app.TopBar.RowHeight = {'1x'};
            app.TopBar.Padding = [0 0 0 0];

            app.LoadJSONButton = uibutton(app.TopBar,'push','Text','Load JSON');
            app.LoadJSONButton.Layout.Column = 1;
            app.LoadJSONButton.ButtonPushedFcn = @(~,~)app.onLoadJSON();

            app.LoadCSVButton = uibutton(app.TopBar,'push','Text','Load CSV');
            app.LoadCSVButton.Layout.Column = 2;
            app.LoadCSVButton.ButtonPushedFcn = @(~,~)app.onLoadCSV();

            app.JSONLabel = uilabel(app.TopBar,'Text','JSON: none','Interpreter','none');
            app.JSONLabel.Layout.Column = 3;

            app.CSVLabel = uilabel(app.TopBar,'Text','CSV: none','Interpreter','none');
            app.CSVLabel.Layout.Column = 4;

            app.ExportPNGsButton = uibutton(app.TopBar,'push','Text','Export PNGs');
            app.ExportPNGsButton.Layout.Column = 5;
            app.ExportPNGsButton.ButtonPushedFcn = @(~,~)app.onExportPNGs();

            app.ExportCSVButton = uibutton(app.TopBar,'push','Text','Export CSVs');
            app.ExportCSVButton.Layout.Column = 6;
            app.ExportCSVButton.ButtonPushedFcn = @(~,~)app.onExportCSV();

            app.RefreshButton = uibutton(app.TopBar,'push','Text','Refresh');
            app.RefreshButton.Layout.Column = 7;
            app.RefreshButton.ButtonPushedFcn = @(~,~)app.onRefresh();

            % Left panel (controls)
            app.LeftPanel = uipanel(app.MainGrid,'Title','Controls');
            app.LeftPanel.Layout.Row = 2;
            app.LeftPanel.Layout.Column = 1;

            app.LeftGrid = uigridlayout(app.LeftPanel,[18 2]);
            app.LeftGrid.RowHeight = {22,22,22,22,22,22,22,22,22,22,22,22,22,22,22,22,22,'1x'};
            app.LeftGrid.ColumnWidth = {'1x','1x'};
            app.LeftGrid.Padding = [8 8 8 8];
            app.LeftGrid.RowSpacing = 6;
            app.LeftGrid.ColumnSpacing = 8;

            app.ShowETDCheck = uicheckbox(app.LeftGrid,'Text','Show ETD (JSON)');
            app.ShowETDCheck.Layout.Row = 1; app.ShowETDCheck.Layout.Column = [1 2];
            app.ShowETDCheck.ValueChangedFcn = @(~,~)app.updateAll();

            app.ShowCSVCheck = uicheckbox(app.LeftGrid,'Text','Show CSV');
            app.ShowCSVCheck.Layout.Row = 2; app.ShowCSVCheck.Layout.Column = [1 2];
            app.ShowCSVCheck.ValueChangedFcn = @(~,~)app.updateAll();

            app.SmoothCheck = uicheckbox(app.LeftGrid,'Text','Smoothing (movmean)');
            app.SmoothCheck.Layout.Row = 3; app.SmoothCheck.Layout.Column = [1 2];
            app.SmoothCheck.ValueChangedFcn = @(~,~)app.updateAll();

            app.SmoothWinLabel = uilabel(app.LeftGrid,'Text','Smooth window (pts)');
            app.SmoothWinLabel.Layout.Row = 4; app.SmoothWinLabel.Layout.Column = 1;
            app.SmoothWinEdit = uieditfield(app.LeftGrid,'numeric','Limits',[1 Inf],'RoundFractionalValues','on');
            app.SmoothWinEdit.Layout.Row = 4; app.SmoothWinEdit.Layout.Column = 2;
            app.SmoothWinEdit.ValueChangedFcn = @(~,~)app.updateAll();

            app.DownsampleLabel = uilabel(app.LeftGrid,'Text','Downsample (Nth)');
            app.DownsampleLabel.Layout.Row = 5; app.DownsampleLabel.Layout.Column = 1;
            app.DownsampleEdit = uieditfield(app.LeftGrid,'numeric','Limits',[1 Inf],'RoundFractionalValues','on');
            app.DownsampleEdit.Layout.Row = 5; app.DownsampleEdit.Layout.Column = 2;
            app.DownsampleEdit.ValueChangedFcn = @(~,~)app.updateAll();

            app.MarkersCheck = uicheckbox(app.LeftGrid,'Text','Show markers');
            app.MarkersCheck.Layout.Row = 6; app.MarkersCheck.Layout.Column = [1 2];
            app.MarkersCheck.ValueChangedFcn = @(~,~)app.updateAll();

            app.TimeAlignLabel = uilabel(app.LeftGrid,'Text','CSV time offset (s)');
            app.TimeAlignLabel.Layout.Row = 7; app.TimeAlignLabel.Layout.Column = 1;
            app.TimeOffsetEdit = uieditfield(app.LeftGrid,'numeric');
            app.TimeOffsetEdit.Layout.Row = 7; app.TimeOffsetEdit.Layout.Column = 2;
            app.TimeOffsetEdit.ValueChangedFcn = @(~,~)app.updateAll();

            app.AutoDelayButton = uibutton(app.LeftGrid,'push','Text','Auto delay (xcorr)');
            app.AutoDelayButton.Layout.Row = 8; app.AutoDelayButton.Layout.Column = 1;
            app.AutoDelayButton.ButtonPushedFcn = @(~,~)app.onAutoDelay();

            app.SyncPeaksButton = uibutton(app.LeftGrid,'push','Text','Sync 5mm Peaks');
            app.SyncPeaksButton.Layout.Row = 8; app.SyncPeaksButton.Layout.Column = 2;
            app.SyncPeaksButton.ButtonPushedFcn = @(~,~)app.onSyncPeaks();

            app.DelayResultLabel = uilabel(app.LeftGrid,'Text','Auto delay: (not computed)','Interpreter','none');
            app.DelayResultLabel.Layout.Row = 9; app.DelayResultLabel.Layout.Column = [1 2];

            app.MapLabel = uilabel(app.LeftGrid,'Text','Compare mapping');
            app.MapLabel.Layout.Row = 10; app.MapLabel.Layout.Column = 1;
            app.MapDrop = uidropdown(app.LeftGrid);
            app.MapDrop.Layout.Row = 10; app.MapDrop.Layout.Column = 2;
            app.MapDrop.ValueChangedFcn = @(~,~)app.updateAll();

            app.MatrixLabel = uilabel(app.LeftGrid,'Text','ETD Matrix element');
            app.MatrixLabel.Layout.Row = 11; app.MatrixLabel.Layout.Column = 1;
            app.MatrixDrop = uidropdown(app.LeftGrid);
            app.MatrixDrop.Layout.Row = 11; app.MatrixDrop.Layout.Column = 2;
            app.MatrixDrop.ValueChangedFcn = @(~,~)app.updateAll();

            % Tabs right
            app.Tabs = uitabgroup(app.MainGrid);
            app.Tabs.Layout.Row = 2;
            app.Tabs.Layout.Column = 2;

            app.TabOverview = uitab(app.Tabs,'Title','Overview');
            app.TabCompare  = uitab(app.Tabs,'Title','Compare');
            app.Tab3D       = uitab(app.Tabs,'Title','Trajectory');
            app.TabMatrix   = uitab(app.Tabs,'Title','Matrix');
            app.TabStats    = uitab(app.Tabs,'Title','Stats');

            % Overview axes layout
            gO = uigridlayout(app.TabOverview,[2 1]);
            gO.RowHeight = {'1x','0.8x'}; gO.Padding=[8 8 8 8];
            app.AxRMSE = uiaxes(gO); app.AxRMSE.Layout.Row=1;
            app.AxTracking = uiaxes(gO); app.AxTracking.Layout.Row=2;

            % Compare layout
            gC = uigridlayout(app.TabCompare,[2 2]);
            gC.RowHeight = {'1x','1x'}; gC.ColumnWidth={'1x','1x'}; gC.Padding=[8 8 8 8];
            app.AxTrans = uiaxes(gC); app.AxTrans.Layout.Row=1; app.AxTrans.Layout.Column=1;
            app.AxRot   = uiaxes(gC); app.AxRot.Layout.Row=1; app.AxRot.Layout.Column=2;
            app.AxCompare = uiaxes(gC); app.AxCompare.Layout.Row=2; app.AxCompare.Layout.Column=1;
            app.AxTemp    = uiaxes(gC); app.AxTemp.Layout.Row=2; app.AxTemp.Layout.Column=2;

            % Trajectory layout
            gT = uigridlayout(app.Tab3D,[1 2]);
            gT.ColumnWidth={'1x','1x'}; gT.Padding=[8 8 8 8];
            app.AxTraj2D = uiaxes(gT); app.AxTraj2D.Layout.Column=1;
            app.AxTraj3D = uiaxes(gT); app.AxTraj3D.Layout.Column=2;

            % Matrix layout
            gM = uigridlayout(app.TabMatrix,[2 1]);
            gM.RowHeight={'1x','1x'}; gM.Padding=[8 8 8 8];
            app.AxMatrixElem = uiaxes(gM); app.AxMatrixElem.Layout.Row=1;
            app.AxMatrixHeat = uiaxes(gM); app.AxMatrixHeat.Layout.Row=2;

            % Stats
            gS = uigridlayout(app.TabStats,[1 1]); gS.Padding=[8 8 8 8];
            app.StatsText = uitextarea(gS); app.StatsText.Editable='off';

            app.UIFigure.Visible = 'on';
        end

    
    end
end