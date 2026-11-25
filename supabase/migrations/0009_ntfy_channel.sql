-- Phone notifications through ntfy (free app for Android/iOS; https://ntfy.sh or a self-hosted ntfy server).
-- A resident subscribes to a private topic in the ntfy app and saves the same topic name in My alerts.
alter table alert_subscriptions add column if not exists ntfy_topic text;
alter table emergency_notifications drop constraint if exists emergency_notifications_notification_channel_check;
alter table emergency_notifications add constraint emergency_notifications_notification_channel_check
  check (notification_channel in ('in_app', 'push', 'sms', 'email', 'ntfy'));
