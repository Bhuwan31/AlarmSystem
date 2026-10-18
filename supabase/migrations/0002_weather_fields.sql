-- Extra weather fields for heat-risk and pressure layers
alter table weather_grid add column if not exists apparent_temp_c double precision;
alter table weather_grid add column if not exists pressure_hpa double precision;
alter table weather_grid add column if not exists tmax_3d_c double precision;
