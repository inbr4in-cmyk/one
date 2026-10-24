import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';

/// Per-device preferences (not secrets): theme, language, auto-lock delay, one-time hints.
class Settings extends ChangeNotifier {
  Settings(this._p)
      : _theme = ThemeMode.values.firstWhere((m) => m.name == _p.getString('theme'), orElse: () => ThemeMode.system),
        _locale = _p.getString('locale') ?? 'ru';

  final SharedPreferences _p;
  ThemeMode _theme;
  String _locale;

  ThemeMode get theme => _theme;
  String get locale => _locale;
  Locale get flutterLocale => Locale(_locale);

  set theme(ThemeMode m) {
    _theme = m;
    _p.setString('theme', m.name);
    notifyListeners();
  }

  set locale(String l) {
    if (l != 'ru' && l != 'kk') return;
    _locale = l;
    _p.setString('locale', l);
    notifyListeners();
  }

  /// Minutes in background before the PIN is asked again (0 = right away).
  int get autolockMinutes => _p.getInt('autolock') ?? 5;
  set autolockMinutes(int v) {
    _p.setInt('autolock', v);
    notifyListeners();
  }

  bool get biometrics => _p.getBool('bio') ?? false;
  set biometrics(bool v) {
    _p.setBool('bio', v);
    notifyListeners();
  }

  bool get chatRulesSeen => _p.getBool('chatRules') ?? false;
  set chatRulesSeen(bool v) => _p.setBool('chatRules', v);

  int? get childId => _p.getInt('child');
  set childId(int? v) => v == null ? _p.remove('child') : _p.setInt('child', v);

  /// Forget everything tied to the signed-in person (keeps theme and language).
  Future<void> clearAccount() async {
    for (final k in ['bio', 'child', 'chatRules']) {
      await _p.remove(k);
    }
  }
}
