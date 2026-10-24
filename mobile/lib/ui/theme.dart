import 'package:flutter/cupertino.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';

import '../config.dart';

/// Design tokens from docs/design/mobile.html (`:root` and the dark override).
@immutable
class OeColors extends ThemeExtension<OeColors> {
  const OeColors({
    required this.paper, required this.surface, required this.line, required this.ink, required this.muted,
    required this.navy100, required this.navy50, required this.red, required this.red100, required this.ok,
    required this.warn, required this.info, required this.primary, required this.onPrimary, required this.brandInk,
    required this.tint, required this.logoE, required this.hero, required this.hero2, required this.onHero2,
    required this.chip, required this.fill, required this.outline, required this.m3nav, required this.ok100,
    required this.warn100, required this.info100, required this.coin, required this.coin100, required this.scrim,
  });

  final Color paper, surface, line, ink, muted, navy100, navy50, red, red100, ok, warn, info, primary, onPrimary;
  final Color brandInk, tint, logoE, hero, hero2, onHero2, chip, fill, outline, m3nav, ok100, warn100, info100;
  final Color coin, coin100, scrim;
  static const white = Color(0xFFFFFFFF);
  static const wa = Color(0xFF1FAF54);
  static const kaspi = Color(0xFFF14635);

  static const light = OeColors(
    paper: Color(0xFFFAF6F3), surface: Color(0xFFFFFFFF), line: Color(0xFFE3E6EE), ink: Color(0xFF0F1A33),
    muted: Color(0xFF5B6782), navy100: Color(0xFFE6ECF7), navy50: Color(0xFFF3F6FB), red: Color(0xFFBB1027),
    red100: Color(0xFFFBE7EA), ok: Color(0xFF1E8E5A), warn: Color(0xFFC98A06), info: Color(0xFF1A6FD1),
    primary: Color(0xFF01225F), onPrimary: Color(0xFFFFFFFF), brandInk: Color(0xFF01225F), tint: Color(0xFF1A3F8A),
    logoE: Color(0xFF01225F), hero: Color(0xFF01225F), hero2: Color(0xFF0B2E73), onHero2: Color(0xFFB9C6E2),
    chip: Color(0xFFF3F6FB), fill: Color(0x0F0F1A33), outline: Color(0xFF8A93A8), m3nav: Color(0xFFF2EEEA),
    ok100: Color(0xFFE3F3EA), warn100: Color(0xFFFBF1DA), info100: Color(0xFFE4EEFA), coin: Color(0xFFD99A12),
    coin100: Color(0xFFFCF1D6), scrim: Color(0x6B0A1630),
  );

  static const dark = OeColors(
    paper: Color(0xFF0A1630), surface: Color(0xFF111F3D), line: Color(0xFF22325A), ink: Color(0xFFEAF0FB),
    muted: Color(0xFF9AA8C7), navy100: Color(0x80182951), navy50: Color(0xFF0F1C38), red: Color(0xFFE0354B),
    red100: Color(0xFF3A1622), ok: Color(0xFF3DBE80), warn: Color(0xFFE3A92B), info: Color(0xFF5B9BEA),
    primary: Color(0xFF2F5BB5), onPrimary: Color(0xFFFFFFFF), brandInk: Color(0xFFEAF0FB), tint: Color(0xFF8FB0F0),
    logoE: Color(0xFF5B83D6), hero: Color(0xFF16306A), hero2: Color(0xFF1D3B80), onHero2: Color(0xFFAFC0E4),
    chip: Color(0xFF16264A), fill: Color(0x14EAF0FB), outline: Color(0xFF6B7A9E), m3nav: Color(0xFF0F1C38),
    ok100: Color(0xFF12392B), warn100: Color(0xFF3A2E10), info100: Color(0xFF132D52), coin: Color(0xFFE8B23A),
    coin100: Color(0xFF3A2E10), scrim: Color(0x8C000000),
  );

  @override
  OeColors copyWith() => this;

  @override
  OeColors lerp(OeColors? other, double t) => t < .5 ? this : (other ?? this);
}

const kDisplay = 'Unbounded';
const kText = 'GolosText';
const _fallback = [kText];

/// Visual idiom: iOS (Cupertino touches) or Android (Material 3), as in the two variants of the design.
class OeStyle {
  OeStyle._();
  static bool get ios {
    if (AppConfig.platformOverride == 'ios') return true;
    if (AppConfig.platformOverride == 'android') return false;
    if (kIsWeb) return false;
    return defaultTargetPlatform == TargetPlatform.iOS || defaultTargetPlatform == TargetPlatform.macOS;
  }

  static double get cardRadius => ios ? 20 : 16;
  static double get btnRadius => ios ? 14 : 999;
}

extension OeContext on BuildContext {
  OeColors get oe => Theme.of(this).extension<OeColors>()!;
  bool get reduceMotion => MediaQuery.maybeDisableAnimationsOf(this) ?? false;
  Duration motion([int ms = 200]) => reduceMotion ? Duration.zero : Duration(milliseconds: ms);
}

TextStyle display(double size, {Color? color, FontWeight weight = FontWeight.w600, double? height}) => TextStyle(
    fontFamily: kDisplay, fontFamilyFallback: _fallback, fontSize: size, fontWeight: weight, color: color,
    height: height ?? 1.15, letterSpacing: -.01 * size);

ThemeData buildTheme(Brightness b) {
  final c = b == Brightness.dark ? OeColors.dark : OeColors.light;
  final scheme = ColorScheme(
    brightness: b,
    primary: c.primary, onPrimary: c.onPrimary,
    secondary: c.tint, onSecondary: c.onPrimary,
    error: c.red, onError: OeColors.white,
    surface: c.surface, onSurface: c.ink,
    surfaceContainerHighest: c.m3nav, outline: c.outline, outlineVariant: c.line,
    primaryContainer: c.navy100, onPrimaryContainer: c.brandInk,
  );
  final base = ThemeData(
    useMaterial3: true,
    brightness: b,
    colorScheme: scheme,
    scaffoldBackgroundColor: c.paper,
    fontFamily: kText,
    extensions: [c],
    dividerColor: c.line,
    splashFactory: OeStyle.ios ? NoSplash.splashFactory : InkSparkle.splashFactory,
    cupertinoOverrideTheme: CupertinoThemeData(primaryColor: c.tint, brightness: b),
    pageTransitionsTheme: const PageTransitionsTheme(builders: {
      TargetPlatform.android: FadeForwardsPageTransitionsBuilder(),
      TargetPlatform.iOS: CupertinoPageTransitionsBuilder(),
      TargetPlatform.linux: FadeForwardsPageTransitionsBuilder(),
    }),
    snackBarTheme: SnackBarThemeData(
      behavior: SnackBarBehavior.floating,
      backgroundColor: c.ink,
      contentTextStyle: TextStyle(fontFamily: kText, color: c.paper, fontSize: 14),
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(14)),
    ),
    inputDecorationTheme: InputDecorationTheme(
      filled: true,
      fillColor: c.surface,
      contentPadding: const EdgeInsets.symmetric(horizontal: 14, vertical: 14),
      hintStyle: TextStyle(color: c.muted),
      border: OutlineInputBorder(borderRadius: BorderRadius.circular(OeStyle.ios ? 14 : 4), borderSide: BorderSide(color: c.line)),
      enabledBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(OeStyle.ios ? 14 : 4), borderSide: BorderSide(color: c.line)),
      focusedBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(OeStyle.ios ? 14 : 4), borderSide: BorderSide(color: c.primary, width: 2)),
    ),
    textSelectionTheme: TextSelectionThemeData(cursorColor: c.tint),
    switchTheme: SwitchThemeData(
      thumbColor: WidgetStateProperty.resolveWith((s) => s.contains(WidgetState.selected) ? c.onPrimary : c.outline),
      trackColor: WidgetStateProperty.resolveWith((s) => s.contains(WidgetState.selected) ? c.primary : c.surface),
    ),
  );
  return base.copyWith(
    textTheme: base.textTheme.apply(bodyColor: c.ink, displayColor: c.ink, fontFamily: kText, fontFamilyFallback: _fallback),
  );
}
