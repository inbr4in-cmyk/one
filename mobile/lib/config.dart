/// Build-time settings. Pass with `--dart-define=OE_API_BASE=https://…`.
class AppConfig {
  AppConfig._();

  /// Origin of the One English server; the API lives under `/api`.
  static const apiBase = String.fromEnvironment('OE_API_BASE', defaultValue: 'https://app.oneenglish.kz');

  /// `ios` or `android` forces the visual style (used for web previews and screenshots).
  static const platformOverride = String.fromEnvironment('OE_PLATFORM');

  /// The school works in Asia/Almaty (UTC+5, no DST): times are shown in school time on every device.
  static const schoolUtcOffset = Duration(hours: 5);

  /// School contact shown on the login screen.
  static const schoolWhatsApp = '+7 700 100 20 18';
}
