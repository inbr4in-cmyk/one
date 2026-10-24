import 'dart:convert';
import 'dart:math';

import 'package:crypto/crypto.dart';
import 'package:flutter/foundation.dart';
import 'package:local_auth/local_auth.dart';

import '../api/secret_store.dart';
import 'settings.dart';

/// Optional 4-digit PIN with biometric unlock, asked on cold start and after the auto-lock delay.
class LockController extends ChangeNotifier {
  LockController(this._secrets, this._settings, {this._auth});

  static const pinKey = 'oe.pin';
  static const maxFailures = 5;

  final SecretStore _secrets;
  final Settings _settings;
  final LocalAuthentication? _auth;
  String? _pin; // "salt:sha256"
  bool _locked = false;
  int failures = 0;
  DateTime? _pausedAt;

  /// Called after [maxFailures] wrong PINs: the session is ended and a new WhatsApp code is needed.
  VoidCallback? onTooManyFailures;

  bool get pinSet => _pin != null;
  bool get locked => _locked && pinSet;
  bool get biometricsOn => pinSet && _settings.biometrics;

  Future<void> load() async {
    _pin = await _secrets.read(pinKey);
  }

  /// Simple PINs are refused (design 13a): 1234, 0000, repeats, runs and years.
  static bool weak(String pin) {
    if (pin.length != 4 || int.tryParse(pin) == null) return true;
    if (pin.split('').toSet().length == 1) return true;
    const runs = '0123456789012';
    if (runs.contains(pin) || runs.split('').reversed.join().contains(pin)) return true;
    final y = int.parse(pin);
    return y >= 1950 && y <= 2030;
  }

  static String _hash(String salt, String pin) => sha256.convert(utf8.encode('$salt:$pin')).toString();

  Future<void> setPin(String pin) async {
    final r = Random.secure();
    final salt = base64Url.encode(List.generate(16, (_) => r.nextInt(256)));
    _pin = '$salt:${_hash(salt, pin)}';
    await _secrets.write(pinKey, _pin);
    failures = 0;
    _locked = false;
    notifyListeners();
  }

  Future<void> clear() async {
    _pin = null;
    _locked = false;
    failures = 0;
    await _secrets.write(pinKey, null);
    notifyListeners();
  }

  /// Checks the PIN; after [maxFailures] wrong tries calls [onTooManyFailures].
  Future<bool> verify(String pin) async {
    final p = _pin;
    if (p == null) return true;
    final i = p.indexOf(':');
    final ok = _hash(p.substring(0, i), pin) == p.substring(i + 1);
    if (ok) {
      failures = 0;
      _locked = false;
      notifyListeners();
      return true;
    }
    failures++;
    if (failures >= maxFailures) {
      failures = 0;
      onTooManyFailures?.call();
    }
    notifyListeners();
    return false;
  }

  void lockNow() {
    if (!pinSet) return;
    _locked = true;
    notifyListeners();
  }

  void paused() => _pausedAt = DateTime.now();

  void resumed() {
    final at = _pausedAt;
    _pausedAt = null;
    if (at == null || !pinSet) return;
    if (DateTime.now().difference(at) >= Duration(minutes: _settings.autolockMinutes)) lockNow();
  }

  Future<bool> biometricsAvailable() async {
    if (kIsWeb || _auth == null) return false;
    try {
      return await _auth.isDeviceSupported() && await _auth.canCheckBiometrics;
    } catch (_) {
      return false;
    }
  }

  /// System biometric prompt (Face ID / BiometricPrompt). A refusal changes nothing.
  Future<bool> authenticate(String reason) async {
    if (kIsWeb || _auth == null) return false;
    try {
      final ok = await _auth.authenticate(localizedReason: reason, biometricOnly: true);
      if (ok) {
        failures = 0;
        _locked = false;
        notifyListeners();
      }
      return ok;
    } catch (_) {
      return false;
    }
  }
}
